"""drf-spectacular schema extensions for the authentication app."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class PasetoAuthenticationScheme(OpenApiAuthenticationExtension):
    """Render the Authorize → Bearer box in Swagger UI for PASETO tokens."""

    target_class = "authentication.authentication.PasetoAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "PASETO",
            "description": (
                "Paste the `access_token` returned by `POST /api/auth/login/`. "
                "It is sent as `Authorization: Bearer <token>`. Tokens are "
                "short-lived; use `POST /api/auth/refresh/` to obtain a new one."
            ),
        }
