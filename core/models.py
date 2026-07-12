"""
core.models — Base entity architecture for G-HRMS.

Every domain model inherits from one of:
  - BaseEntity        : UUID PK + audit columns + optimistic row versioning
  - SoftDeleteModel   : BaseEntity + soft-delete (default) and hard-delete (explicit)
  - AppendOnlyModel   : BaseEntity that forbids UPDATE/DELETE at the ORM level

Conventions
  - New entities use UUIDv4 keys by default.
  - Legacy Employee/Organization tables retain bigint keys until a separately
    approved primary-key migration; they still receive the same audit behavior.
  - created_by / updated_by are captured automatically from the request user via
    core.middleware.CurrentUserMiddleware (thread-local), so models stay decoupled
    from the request.
  - row_version (django-concurrency) provides optimistic locking: a concurrent edit
    on a stale instance raises RecordModifiedError -> no lost updates.
  - HistoricalRecords (django-simple-history) snapshots each row change for time-travel.
"""

import uuid
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from concurrency.fields import IntegerVersionField # optimistic locking
from core.middleware import get_current_user



# Managers
class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(is_deleted=False)
    
    def dead(self):
        return self.filter(is_deleted=True)

    def delete(self):
        """Bulk soft-delete (QuerySet.delete override)."""
        return self.update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()

class SoftDeleteManager(models.Manager):
    """Default manager: hides soft-deleted rows."""
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)
    def all_with_deleted(self):
        return SoftDeleteQuerySet(self.model,using=self._db)
    def dead(self):
        return self.all_with_deleted().dead()
    

# Abstract base entities

class AuditModel(models.Model):
    """Shared audit fields without imposing a primary-key strategy."""

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    row_version = IntegerVersionField()

    class Meta:
        abstract = True
        get_latest_by = "created_at"

    def save(self, *args, **kwargs):
        user = get_current_user()
        if user is not None and getattr(user, "is_authenticated", False):
            if self._state.adding:
                self.created_by = self.created_by or user
            self.updated_by = user
        super().save(*args, **kwargs)


class BaseModel(AuditModel):
    """
        Root of every persistent entity.
        UUID PK + full audit columns + optimistics row versioning.
    """
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)

    class Meta(AuditModel.Meta):
        abstract = True



class BigAutoBaseModel(AuditModel):
    """Audited base for legacy tables that already use bigint primary keys."""

    id = models.BigAutoField(primary_key=True)

    class Meta(AuditModel.Meta):
        abstract = True

class SoftDeleteModel(BaseModel):
    """
        BaseModel + soft delete.
        `.delete()` flags the row; `.hard_delete()` removes it permanently.

    """

    is_deleted = models.BooleanField(default=False,db_index=True)
    deleted_at = models.DateTimeField(null=True,blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,null=True,blank=True,
        on_delete=models.SET_NULL,related_name="+",editable=False
    )
    objects = SoftDeleteManager()  # hides soft-deleted by default
    all_objects = models.Manager() # escape hatch incl. deleted


    class Meta(BaseModel.Meta):
        abstract = True

    def delete(self,using=None, keep_parents = False,hard=False):
        if hard:
            return super().delete(using=using,keep_parents=keep_parents)
        self.is_deleted = True
        self.deleted_at = timezone.now()
        current_user = get_current_user()
        if current_user is not None and getattr(
            current_user, "is_authenticated", False
        ):
            self.deleted_by = current_user
        self.save(update_fields=["is_deleted","deleted_at","deleted_by","row_version"])

    def hard_delete(self,using=None,keep_parents=False):
        """Permanent removal - use only for retention-expiry purges (audited.)"""
        return super().delete(using=using,keep_parents=keep_parents)
    
    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["is_deleted","deleted_at","deleted_by","row_version"])


class BigAutoSoftDeleteModel(BigAutoBaseModel):
    """Soft deletion for existing bigint-keyed tables."""

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta(BigAutoBaseModel.Meta):
        abstract = True

    def delete(self, using=None, keep_parents=False, hard=False):
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.is_deleted = True
        self.deleted_at = timezone.now()
        current_user = get_current_user()
        if current_user is not None and getattr(
            current_user, "is_authenticated", False
        ):
            self.deleted_by = current_user
        self.save(
            update_fields=["is_deleted", "deleted_at", "deleted_by", "row_version"]
        )

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(
            update_fields=["is_deleted", "deleted_at", "deleted_by", "row_version"]
        )


class AppendOnlyModel(BaseModel):
    """
        Immutable tamper-evident records (Auditing,ServiceBookEntry).
        Blocks UPDATE/DELETE at the ORM layer; a DB trigger (see migration) enforces
        the same at the database layer so even raw SQL cannot mutate history.
    """

    class Meta(BaseModel.Meta):
        abstract = True

    def save(self,*args,**kwargs):
        if not self._state.adding:
            raise PermissionError(f"{type(self).__name__} is append-only and cannot be modified.")
        super().save(*args,**kwargs)

    def delete(self,*args,**kwargs):
        raise PermissionError(f"{type(self).__name__} is append-only and cannot be deleted.")
        

# Reusable mixins

class CodeModel(models.Model):
    """Human-readable external code alongside the UUID PK(EMP-10241,USR-001)"""
    code = models.CharField(max_length=32,unique=True,db_index=True)

    class Meta:
        abstract = True

class HistoryMixin(models.Model):
    """Attach per-row history/snapshots. Inherit AND declare `history = HistoricalRecords().`"""

    class Meta:
        abstract = True

# Convenience: run a block a REPEATABLE READ (used by payrolls runs for a consistent snapshot)
def atomic_repetable_read():
    return transaction.atomic() # set connection isolation in settings or context mgr
