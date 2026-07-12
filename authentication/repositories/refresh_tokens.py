"""Persistence operations for refresh-token records."""

from datetime import datetime
from uuid import UUID

from account.models import RefreshToken

class RefreshTokenRepository:
    """Isolate refresh-token queries and persistence operations."""
    model = RefreshToken

    def find_by_hash(self,token_hash:str):
        return self.model.objects.filter(token_hash=token_hash).first()
    
    def find_for_update_by_hash(self,token_hash:str):
        """Return and lock a refresh token.
           This must be called inside transaction.atomic().
        """

        return (
            self.model.objects
            .select_for_update()
            .select_related("user")
            .filter(token_hash=token_hash)
            .first()
        )
    
    def create(
        self,
        *,
        user,
        token_hash:str,
        expires_at:datetime,
        family_id: UUID | None = None,
        parent = None,
        device_info : str = "",
        ip_address: str | None = None,
    ):
        values = {
            "user":user,
            "token_hash":token_hash,
            "expires_at":expires_at,
            "parent":parent,
            "device_info":device_info,
            "ip_address":ip_address,
            
        }

        if family_id is not None:
            values["family_id"] = family_id
        return self.model.objects.create(**values)
    
    @staticmethod
    def revoke(token,*,rotated_at:datetime):
        token.is_revoked = True
        token.rotated_at = rotated_at
        token.save(
            update_fields = [
                "is_revoked",
                "rotated_at",
                "row_version",
            ]
        )
        return token
    
    def revoke_family(self,family_id:UUID, *, rotated_at: datetime) -> int:
        """Revoke every active token in one family. Returns the number of updated database rows."""
        return self.model.objects.filter(
            family_id = family_id,
            is_revoked = False,
        ).update(
            is_revoked = True,
            rotated_at = rotated_at
        )

    def revoke_all_for_user(self, user, *, rotated_at: datetime) -> int:
        """Revoke every active token for a user (e.g. when suspending them).

        Returns the number of updated rows.
        """
        return self.model.objects.filter(
            user=user,
            is_revoked=False,
        ).update(
            is_revoked=True,
            rotated_at=rotated_at,
        )