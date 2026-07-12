from django.test import RequestFactory, SimpleTestCase
from rest_framework.exceptions import NotFound, ValidationError

from core.exceptions import api_exception_handler
from core.errors import ApplicationError


class ApiExceptionHandlerTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/api/employees/")
        self.request.request_id = "request-12345678"
        self.context = {"request": self.request}

    def test_validation_error_preserves_field_codes(self):
        response = api_exception_handler(
            ValidationError({"email": ["This field is required."]}),
            self.context,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "validation_error")
        self.assertEqual(
            response.data["error"]["details"]["email"][0],
            {"message": "This field is required.", "code": "invalid"},
        )
        self.assertEqual(response.data["request_id"], "request-12345678")

    def test_not_found_uses_standard_envelope(self):
        response = api_exception_handler(NotFound(), self.context)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"]["code"], "not_found")
        self.assertIsNone(response.data["error"]["details"])

    def test_unhandled_exception_is_logged_and_sanitized(self):
        try:
            raise RuntimeError("private implementation detail")
        except RuntimeError as exc:
            with self.assertLogs("ghrms.api", level="ERROR"):
                response = api_exception_handler(exc, self.context)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["error"]["code"], "internal_server_error")
        self.assertNotIn("private implementation detail", str(response.data))

    def test_application_error_uses_declared_contract(self):
        error = ApplicationError(
            "The operation is not allowed.",
            details={"reason": "business_rule"},
        )

        response = api_exception_handler(error, self.context)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "application_error")
        self.assertEqual(
            response.data["error"]["message"],
            "The operation is not allowed.",
        )
        self.assertEqual(
            response.data["error"]["details"],
            {"reason": "business_rule"},
        )
        self.assertEqual(response.data["request_id"], "request-12345678")

