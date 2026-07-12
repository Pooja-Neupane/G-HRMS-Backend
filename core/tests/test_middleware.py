from types import SimpleNamespace

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from core.middleware import (
    CurrentUserMiddleware,
    RequestContextMiddleware,
    get_client_ip,
    get_current_ip,
    get_current_user,
    get_request_id,
)


class RequestContextMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_valid_request_id_is_propagated_and_context_is_cleared(self):
        seen_request_id = None

        def get_response(request):
            nonlocal seen_request_id
            seen_request_id = get_request_id()
            return HttpResponse(status=204)

        request = self.factory.get(
            "/api/employees/", HTTP_X_REQUEST_ID="client-request-123"
        )
        with self.assertLogs("ghrms.request", level="INFO") as captured:
            response = RequestContextMiddleware(get_response)(request)

        self.assertEqual(seen_request_id, "client-request-123")
        self.assertEqual(response["X-Request-ID"], "client-request-123")
        self.assertIsNone(get_request_id())
        self.assertEqual(captured.records[0].path, "/api/employees/")

    def test_invalid_request_id_is_replaced(self):
        request = self.factory.get("/api/employees/", HTTP_X_REQUEST_ID="bad id")
        with self.assertLogs("ghrms.request", level="INFO"):
            response = RequestContextMiddleware(lambda request: HttpResponse())(request)

        self.assertNotEqual(response["X-Request-ID"], "bad id")
        self.assertEqual(len(response["X-Request-ID"]), 32)

    @override_settings(TRUSTED_PROXY_IPS=("127.0.0.1",))
    def test_forwarded_ip_is_used_only_for_a_trusted_proxy(self):
        request = self.factory.get(
            "/api/employees/",
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.10, 127.0.0.1",
        )

        self.assertEqual(get_client_ip(request), "203.0.113.10")

    @override_settings(TRUSTED_PROXY_IPS=())
    def test_forwarded_ip_is_ignored_for_an_untrusted_peer(self):
        request = self.factory.get(
            "/api/employees/",
            REMOTE_ADDR="198.51.100.20",
            HTTP_X_FORWARDED_FOR="203.0.113.10",
        )

        self.assertEqual(get_client_ip(request), "198.51.100.20")


class CurrentUserMiddlewareTests(SimpleTestCase):
    def test_actor_context_is_available_and_then_cleared(self):
        actor = SimpleNamespace(pk="user-1", is_authenticated=True)
        request = RequestFactory().get(
            "/api/employees/", REMOTE_ADDR="198.51.100.20"
        )
        request.user = actor
        captured = {}

        def get_response(request):
            captured["user"] = get_current_user()
            captured["ip"] = get_current_ip()
            return HttpResponse()

        CurrentUserMiddleware(get_response)(request)

        self.assertIs(captured["user"], actor)
        self.assertEqual(captured["ip"], "198.51.100.20")
        self.assertIsNone(get_current_user())
        self.assertIsNone(get_current_ip())

