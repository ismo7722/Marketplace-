"""Facebook scraper errors — clean handling in logs and monitoring."""


class FacebookLoginRequiredError(RuntimeError):
    """Session missing or expired — user runs login-facebook.bat on their PC."""


LOGIN_REQUIRED_LOG = (
    "Facebook logged out — run login-facebook.bat on your PC, log in, "
    "then press Stop and Start on the dashboard."
)
