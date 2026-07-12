"""
accounts.models — Identity, RBAC and token rotation.

users (login)  ──1:1?──  employees (HR record)   [link via User.employee]
roles ─< role_permissions >─ permissions
roles ─< role_module_access   (the Settings → Access Control matrix)
users ─< refresh_tokens (rotating, theft-evident) ; users ─< auth_events
"""

import uuid
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models, transaction
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core.models import BaseModel, SoftDeleteModel, AppendOnlyModel


# Roles & Permissions

class Role(SoftDeleteModel):
    name = models.CharField(max_length=64,unique=True)
    description = models.CharField(max_length=255,blank=True)
    is_system_role = models.BooleanField(default=False)
    requires_mfa = models.BooleanField(default=False)
    history = HistoricalRecords()

    def __str__(self):
        return self.name
    
class AccessPermission(BaseModel):
    """
    Granular "resource:action" permission, e.g. ("leave", "approve").
    Named AccessPermission to avoid confusion with django.contrib.auth.Permission.
    """
    resource = models.CharField(max_length=64)
    action = models.CharField(max_length=64)
    description = models.CharField(max_length=255,blank=True)

    class Meta(BaseModel.Meta):
        unique_together = [("resource","action")]

    @property
    def codename(self):
        return f"{self.resource}:{self.action}"
    

class RolePermission(BaseModel):
    role = models.ForeignKey(Role,on_delete=models.CASCADE,related_name="role_permissions")
    permission = models.ForeignKey(AccessPermission,on_delete=models.CASCADE,related_name="+")

    class Meta(BaseModel.Meta):
        unique_together = [("role","permission")]

class ModuleKey(models.TextChoices):
    DASHBOARD = "dashboard"
    EMPLOYEES = "employees"
    ORGANIZATION = "organization"
    ATTENDANCE = "attendance"
    LEAVE = "leave"
    PAYROLL = "payroll"
    PROMOTIONS = "promotions"
    DOCUMENTS = "documents"
    REPORTS = "reports"
    AUDIT = "audit"
    USERS = "users"
    SETTINGS = "settings"


class RoleModuleAccess(BaseModel):
    """Persisted Access-Control Matrinx (Settings-> Access Control)"""
    role = models.ForeignKey(Role,on_delete=models.CASCADE, related_name="module_access")
    module_key = models.CharField(max_length=32,choices=ModuleKey.choices)
    can_access = models.BooleanField(default=False)
    history = HistoricalRecords()


    class Meta(BaseModel.Meta):
        unique_together = [("role","module_key")]



class User(AbstractUser):
    """
    System login account. Distinct from employees.Employee (HR record).

    Keep AbstractUser here: the project already has an initial migration with
    Django's standard user fields, so this preserves admin/auth compatibility.
    """

    class Status(models.TextChoices):
        ACTIVE = "active"
        SUSPENDED = "suspended"
        INVITED = "invited"      

      
    class Role(models.TextChoices):
        SUPERADMIN = "SUPERADMIN", "SuperAdmin"
        CHIEF_MINISTER_ADMIN = "CHIEF_MINISTER_ADMIN", "ChiefMinisterAdmin"
        HR_PERSONNEL = "HR_PERSONNEL", "HRPersonnel"
        KITABKHANA = "KITABKHANA", "Kitabkhana"
        VIEWER = "VIEWER", "Viewer"

    role = models.CharField(max_length=50, choices=Role.choices, default=Role.VIEWER)
    status = models.CharField(max_length=12,choices=Status.choices,default=Status.INVITED)

    # MFA
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(max_length=255,blank=True) # encrypt at rest(pgcrypto/fernet)

    # Lockout / rotation policy
    failed_login_count = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True,blank=True)
    password_changed_at = models.DateTimeField(null=True,blank=True)
    last_login_at = models.DateTimeField(null=True,blank=True)

    # optionally link to Organization if HR users are tied to a ministry
    organization = models.ForeignKey(
        "organizations.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
    )

    objects = DjangoUserManager()
    history = HistoricalRecords(excluded_fields=["password", "mfa_secret"])

    def can_access_module(self, module_key) -> bool:
        if self.is_superuser or self.role == self.Role.SUPERADMIN:
            return True
        role = Role.objects.filter(name=self.role).first()
        if role is None:
            return False
        return RoleModuleAccess.objects.filter(
            role=role,
            module_key=module_key,
            can_access=True,
        ).exists()

    def has_perm_code(self, codename: str) -> bool:
        if self.is_superuser or self.role == self.Role.SUPERADMIN:
            return True
        resource, separator, action = codename.partition(":")
        if not separator:
            return False
        role = Role.objects.filter(name=self.role).first()
        if role is None:
            return False
        return RolePermission.objects.filter(
            role=role,
            permission__resource=resource,
            permission__action=action,
        ).exists()

    def is_hr_for(self, organization):
        """Helper: True if user is HR and tied to given organization (or same ministry)."""
        if self.role != self.Role.HR_PERSONNEL:
            return False
        if not self.organization or not organization:
            return False
        return self.organization.id == organization.id


class RefreshToken(BaseModel):
    """
    Rotating refresh tokens.

    Store only token_hash, never the raw refresh token. Reusing a revoked token
    revokes the whole token family so theft is detectable and containable.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="refresh_tokens")
    token_hash = models.CharField(max_length=128, unique=True, db_index=True)
    family_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    expires_at = models.DateTimeField()
    is_revoked = models.BooleanField(default=False)
    rotated_at = models.DateTimeField(null=True, blank=True)
    device_info = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["user", "is_revoked"])]

    @property
    def is_active(self) -> bool:
        return not self.is_revoked and self.expires_at > timezone.now()

    @transaction.atomic
    def rotate(self, new_token_hash, expires_at) -> "RefreshToken":
        if self.is_revoked:
            self.revoke_family()
            AuthEvent.objects.create(
                user=self.user,
                event_type=AuthEvent.Kind.TOKEN_REUSE,
                ip_address=self.ip_address,
            )
            raise PermissionError("Refresh token reuse detected; token family revoked.")

        self.is_revoked = True
        self.rotated_at = timezone.now()
        self.save(update_fields=["is_revoked", "rotated_at", "row_version"])
        return RefreshToken.objects.create(
            user=self.user,
            token_hash=new_token_hash,
            family_id=self.family_id,
            parent=self,
            expires_at=expires_at,
            device_info=self.device_info,
            ip_address=self.ip_address,
        )

    @transaction.atomic
    def revoke_family(self):
        RefreshToken.objects.filter(
            family_id=self.family_id,
            is_revoked=False,
        ).update(is_revoked=True, rotated_at=timezone.now())


class AuthEvent(AppendOnlyModel):
    """Immutable security log: logins, MFA failures, lockouts, password changes."""

    class Kind(models.TextChoices):
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        MFA_FAIL = "mfa_fail", "MFA failure"
        LOCKOUT = "lockout", "Lockout"
        PASSWORD_CHANGE = "password_change", "Password change"
        TOKEN_REUSE = "token_reuse", "Token reuse"

    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="auth_events")
    event_type = models.CharField(max_length=24, choices=Kind.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
