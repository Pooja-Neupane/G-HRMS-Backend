import json
import logging

from django.test import SimpleTestCase

from core.logging import JsonFormatter, RequestContextFilter


class StructuredLoggingTests(SimpleTestCase):
    def test_context_filter_supplies_request_id(self):
        record = logging.LogRecord(
            "ghrms.test", logging.INFO, __file__, 1, "event", (), None
        )

        RequestContextFilter().filter(record)

        self.assertEqual(record.request_id, "-")

    def test_json_formatter_includes_structured_fields(self):
        record = logging.LogRecord(
            "ghrms.request", logging.INFO, __file__, 1, "request.completed", (), None
        )
        record.request_id = "request-12345678"
        record.http_method = "GET"
        record.path = "/api/employees/"
        record.status_code = 200

        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["message"], "request.completed")
        self.assertEqual(payload["request_id"], "request-12345678")
        self.assertEqual(payload["status_code"], 200)

