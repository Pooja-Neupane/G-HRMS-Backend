from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'authentication'

    def ready(self):
        # Register the drf-spectacular security-scheme extension so the
        # Authorize (Bearer) control appears in Swagger UI.
        from authentication import schema  # noqa: F401
