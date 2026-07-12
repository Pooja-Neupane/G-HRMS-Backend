from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Employee, OfficeTransfer, EmployeeStatusHistory


@receiver(pre_save, sender=Employee)
def cache_old_employee_data(sender, instance, **kwargs):
    """
    Before saving, fetch the existing record (if any)
    and attach its old organization and status for comparison.
    """
    if getattr(instance, "_skip_employee_tracking", False) or not instance.pk:
        return  # new employee, nothing to compare
    try:
        old_instance = Employee.objects.get(pk=instance.pk)
        instance._old_working_org = old_instance.working_organization
        instance._old_status = old_instance.status
    except Employee.DoesNotExist:
        pass


@receiver(post_save, sender=Employee)
def track_employee_creation_and_changes(sender, instance, created, **kwargs):
    """
    After saving, handle recruitment, transfer, and status history logging.
    """

    if getattr(instance, "_skip_employee_tracking", False):
        return

    # --- Case 1: New employee created ---
    if created:
        if instance.working_organization:
            OfficeTransfer.objects.create(
                employee=instance,
                to_organization=instance.working_organization,
                status="RECRUITED",
                remarks="Initial appointment record (auto-recorded)",
                initiated_by=None,
                verified_by=None,
            )
        return

    # --- Case 2: Office change ---
    old_org = getattr(instance, "_old_working_org", None)
    if old_org and old_org != instance.working_organization:
        OfficeTransfer.objects.create(
            employee=instance,
            to_organization=instance.working_organization,
            status="TRANSFERRED",
            remarks="Auto-recorded via signal (office changed)",
            initiated_by=None,
            verified_by=None,
        )

    # --- Case 3: Status change ---
    old_status = getattr(instance, "_old_status", None)
    if old_status and old_status != instance.status:
        EmployeeStatusHistory.objects.create(
            employee=instance,
            old_status=old_status,
            new_status=instance.status,
            remarks="Auto-recorded via signal (status changed)",
        )
