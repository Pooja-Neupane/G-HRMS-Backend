"""ORM persistence boundary for employee document workflows"""

from documents.models import EmployeeDocument

class EmployeeDocumentRepository:
    model = EmployeeDocument

    def queryset(self):
        return self.model.objects.select_related(
            "employee",
            "category",
        )
    
    def get_by_id(self,document_id):
        return self.queryset().filter(pk=document_id).first()
    
    def get_for_update(self,document_id):
        """Lock one logical document inside transaction.atomic()."""
        return(
            self.model.objects
            .select_for_update()
            .select_related("employee","category")
            .get(pk=document_id)
        )

    def get_active_for_category_for_update(self, *, employee_id, category_id):
        """Lock the employee's active document in a category, if one exists."""
        return (
            self.model.objects
            .select_for_update()
            .filter(
                employee_id=employee_id,
                category_id=category_id,
                lifecycle_status=EmployeeDocument.LifecycleStatus.ACTIVE,
            )
            .first()
        )

    @staticmethod
    def save(document):
        document.save()
        return document
