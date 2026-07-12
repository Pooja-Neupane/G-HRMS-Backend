from django.urls import path
from rest_framework.routers import SimpleRouter

from authentication.views import (
    CsrfTokenView,
    LoginView,
    LogoutView,
    RefreshView,
    SignupResendView,
    SignupVerifyView,
    SignupView,
    UserAdminViewSet,
)


app_name = "authentication"

router = SimpleRouter()
router.register(r"admin/users", UserAdminViewSet, basename="admin-user")

urlpatterns = [
    path("csrf/", CsrfTokenView.as_view(), name="csrf"),
    path("signup/", SignupView.as_view(), name="signup"),
    path("signup/verify/", SignupVerifyView.as_view(), name="signup-verify"),
    path("signup/resend/", SignupResendView.as_view(), name="signup-resend"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    *router.urls,
]
