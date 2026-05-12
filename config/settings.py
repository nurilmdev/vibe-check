import os
from dotenv import load_dotenv

load_dotenv()

def get(key: str, default=None, required: bool = False):
    value = os.getenv(key, default)
    if required and not value:
        raise EnvironmentError(f"[Config] Required environment variable '{key}' is not set. Check your .env file.")
    return value


# --- Atlassian Credentials ---
ATLASSIAN_EMAIL        = get("ATLASSIAN_EMAIL", required=True)
ATLASSIAN_PASSWORD     = get("ATLASSIAN_PASSWORD", required=True)
ATLASSIAN_TOTP_SECRET  = get("ATLASSIAN_TOTP_SECRET", default=None)

# --- URLs ---
ATLASSIAN_ADMIN_URL    = get("ATLASSIAN_ADMIN_URL", default="https://admin.atlassian.com")
ATLASSIAN_TOKEN_URL    = get("ATLASSIAN_TOKEN_URL", default="https://id.atlassian.com/manage-profile/security/api-tokens")

# --- Browser Settings ---
HEADLESS               = get("HEADLESS", default="false").lower() == "true"

PAGE_WITH_SESSION      = get("PAGE_WITH_SESSION", default="true").lower() == "true"

# --- Scheduler ---
TOKEN_RENEWAL_INTERVAL_DAYS = int(get("TOKEN_RENEWAL_INTERVAL_DAYS", default="30"))

# --- Treshold Expires ---
TOKEN_RENEWAL_THRESHOLD_DAYS = int(get("TOKEN_RENEWAL_THRESHOLD_DAYS", default="5"))

# --- Logging ---
LOG_LEVEL              = get("LOG_LEVEL", default="DEBUG")

API_KEY_GEMINI          = get("API_KEY_GEMINI")

# --- Database ---
DB_HOST     = get("DB_HOST", default="localhost")
DB_PORT     = int(get("DB_PORT", default="5432"))
DB_NAME     = get("DB_NAME", required=True)
DB_USER     = get("DB_USER", required=True)
DB_PASSWORD = get("DB_PASSWORD", required=True)
