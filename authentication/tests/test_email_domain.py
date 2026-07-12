from unittest.mock import patch

import dns.resolver
from dns.exception import Timeout
from django.test import SimpleTestCase, override_settings

from authentication.email_domain import email_domain_is_deliverable
from authentication.serializers import SignupSerializer


def _resolve(*, mx=None, a=None, aaaa=None, nxdomain=False, error=None):
    """Build a fake dns resolve() keyed by record type."""

    mapping = {"MX": mx, "A": a, "AAAA": aaaa}

    def fake_resolve(self, domain, record_type):
        if error is not None:
            raise error
        if nxdomain:
            raise dns.resolver.NXDOMAIN()
        records = mapping.get(record_type)
        if records:
            return records
        raise dns.resolver.NoAnswer()

    return fake_resolve


class EmailDomainResolverTests(SimpleTestCase):
    def _run(self, **kwargs):
        with patch.object(
            dns.resolver.Resolver, "resolve", _resolve(**kwargs)
        ):
            return email_domain_is_deliverable("user@example.com", timeout=1.0)

    def test_domain_with_mx_is_deliverable(self):
        self.assertTrue(self._run(mx=["mx1.example.com"]))

    def test_domain_without_mx_but_with_a_record_is_deliverable(self):
        self.assertTrue(self._run(a=["203.0.113.10"]))

    def test_nonexistent_domain_is_rejected(self):
        self.assertFalse(self._run(nxdomain=True))

    def test_domain_with_no_mail_records_is_rejected(self):
        self.assertFalse(self._run())

    def test_dns_timeout_fails_open(self):
        self.assertTrue(self._run(error=Timeout()))

    def test_missing_domain_part_is_rejected(self):
        # No domain after "@": rejected without any DNS lookup.
        self.assertFalse(email_domain_is_deliverable("user@"))


@override_settings(
    AUTH_SIGNUP_VERIFY_EMAIL_DOMAIN=True,
    AUTH_SIGNUP_EMAIL_DNS_TIMEOUT=1.0,
)
class SignupSerializerDomainCheckTests(SimpleTestCase):
    def _data(self, **overrides):
        data = {
            "username": "newcomer",
            "email": "newcomer@example.com",
            "password": "StrongPassword@123",
            "password_confirm": "StrongPassword@123",
        }
        data.update(overrides)
        return data

    def setUp(self):
        # Keep the real .model (the password validators build a real unsaved
        # User from it); only stub the database-backed uniqueness lookups.
        repo = SignupSerializer.user_repository
        for attr in ("exists_by_username", "exists_by_email"):
            patcher = patch.object(repo, attr, return_value=False)
            patcher.start()
            self.addCleanup(patcher.stop)

    @patch("authentication.serializers.email_domain_is_deliverable")
    def test_undeliverable_domain_is_rejected(self, deliverable):
        deliverable.return_value = False

        serializer = SignupSerializer(data=self._data())

        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)

    @patch("authentication.serializers.email_domain_is_deliverable")
    def test_deliverable_domain_passes(self, deliverable):
        deliverable.return_value = True

        serializer = SignupSerializer(data=self._data())

        self.assertTrue(serializer.is_valid(), serializer.errors)
