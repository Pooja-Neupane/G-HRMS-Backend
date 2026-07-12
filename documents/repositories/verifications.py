"""Persistence boundary for append-only document verification events."""

from documents.models import DocumentVerification

class DocumentVerificationRepository:
    model = DocumentVerification

    def queryset(self):
        return self.model.objects.select_related(
            "version__document__employee",
            "version__document__category",
            "reviewed_by",
        )
    
    def list_for_version(self,version_id):
        return self.queryset().filter(version_id=version_id)
    
    def get_latest_for_version(self,version_id):
        return self.list_for_version(version_id).first()
    

    @staticmethod
    def save(verification):
        verification.save()
        return verification