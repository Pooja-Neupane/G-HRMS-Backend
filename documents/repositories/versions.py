"""ORM persistence boundary for document file versions."""

from django.db.models import Max

from documents.models import DocumentVersion

class DocumentVersionRepository:
    model = DocumentVersion

    def queryset(self):
        return self.model.objects.select_related(
            "document__employee",
            "document__category",
            "uploaded_by",

        )
    
    def get_by_id(self,version_id):
        return self.queryset().filter(pk=version_id).first()
    
    def get_for_update(self,version_id):
        """Lock a version inside transaction.atomic()."""
        return (
            self.model.objects
            .select_for_update()
            .select_related(
                 "document__employee",
                  "document__category",
            ).get(pk=version_id)
        )
    
    def get_current_for_update(self,document_id):
        """Lock the current active version, when one exists."""
        return(
            self.model.all_objects
            .select_for_update()
            .filter(
                document_id=document_id,
                is_current = True,
                is_deleted = False,
            ).first()
        )
    
    def next_version_number(self,document_id):
        """Return the next number after every version, including deleted ones."""
        latest = (
            self.model.all_objects
            .filter(document_id=document_id)
            .aggregate(maximum=Max("version_number"))
        )
        return (latest["maximum"] or 0) + 1
    
    @staticmethod
    def save(version):
        version.save()
        return version
    
    @staticmethod
    def mark_not_current(version):
        version.is_current = False
        version.save(update_fields=["is_current","row_version"])
        return version

    