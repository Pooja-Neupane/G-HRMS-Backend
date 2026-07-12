"""Business errors raised by authentication services."""

from core.errors import ApplicationError


class AuthenticationError(ApplicationError):
    """Base class for authentication failures."""

    code = "authentication_failed"
    message = "Authentication failed."
    status_code = 401


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"
    message = "Invalid username or password."


class AccountInactiveError(AuthenticationError):
    code = "account_inactive"
    message = "This account is not active."
    status_code = 403


class AccountLockedError(AuthenticationError):
    code = "account_locked"
    message = "This account is temporarily locked."
    status_code = 403


class InvalidRefreshTokenError(AuthenticationError):
    code = "invalid_refresh_token"
    message = "The refresh token is invalid or expired."


class TokenReuseDetectedError(AuthenticationError):
    code = "token_reuse_detected"
    message = "Token reuse was detected. The session has been revoked."


class MfaRequiredError(AuthenticationError):
    code = "mfa_required"
    message = "Multi-factor authentication is required."
    status_code = 403


class MfaVerificationError(AuthenticationError):
    code = "mfa_verification_failed"
    message = "The verification code is invalid."


class InvalidAccessTokenError(AuthenticationError):
    code = "invalid_access_token"
    message = "The access token is invalid or expired."


class RegistrationError(ApplicationError):
    """Base class for account-registration failures."""

    code = "registration_failed"
    message = "The account could not be registered."
    status_code = 409


class UsernameAlreadyExistsError(RegistrationError):
    code = "username_taken"
    message = "This username is already taken."


class EmailAlreadyExistsError(RegistrationError):
    code = "email_taken"
    message = "This email is already registered."


class UserNotFoundError(ApplicationError):
    code = "user_not_found"
    message = "No user was found with the given identifier."
    status_code = 404


class InvalidStatusTransitionError(ApplicationError):
    code = "invalid_status_transition"
    message = "This account status change is not allowed."
    status_code = 409


class SelfStatusChangeError(ApplicationError):
    code = "self_status_change_forbidden"
    message = "You cannot change your own account status."
    status_code = 403


class SignupOtpError(ApplicationError):
    """Base class for signup OTP-verification failures."""

    code = "signup_verification_failed"
    message = "Signup verification failed."
    status_code = 400


class PendingRegistrationNotFoundError(SignupOtpError):
    code = "pending_registration_not_found"
    message = (
        "No pending registration was found, or it has expired. "
        "Please sign up again."
    )
    status_code = 404


class InvalidOtpError(SignupOtpError):
    code = "invalid_otp"
    message = "The verification code is invalid."
    status_code = 400


class TooManyOtpAttemptsError(SignupOtpError):
    code = "too_many_otp_attempts"
    message = "Too many incorrect attempts. Please sign up again."
    status_code = 429


class OtpResendThrottledError(SignupOtpError):
    code = "otp_resend_throttled"
    message = "Please wait before requesting another verification code."
    status_code = 429
