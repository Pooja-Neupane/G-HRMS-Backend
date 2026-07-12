from django.core.management.base import BaseCommand
from employees.models import Employee, Organization, Position
from faker import Faker


class Command(BaseCommand):
    help = "Seed the database with sample employees"

    def handle(self, *args, **options):
        fake = Faker()
        for _ in range(50):
            Employee.objects.create(
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                citizenship_number=fake.random_number(digits=7),
                ka_sa_num=fake.unique.bothify(text="KS#######"),
                email=fake.unique.email(),
                working_organization=Organization.objects.order_by("?").first(),
                current_position_date_ad=fake.date_between(
                    start_date="-5y", end_date="today"
                ),
                position=Position.objects.order_by("?").first(),
                status="in_service",
                dob_ad=fake.date_of_birth(minimum_age=22, maximum_age=60),
                jobstartdate_ad=fake.date_between(start_date="-10y", end_date="today"),
            )
        self.stdout.write(self.style.SUCCESS("50 Employees created successfully!"))
