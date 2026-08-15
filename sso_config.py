"""Microsoft Entra ID (Azure AD) SSO configuration.

Settings can come from two places, in priority order:
  1. Admin-configured values saved through /admin/sso (stored in Postgres
     when a database is configured, else a local encrypted JSON file next
     to the Excel "database" -- same dual-mode pattern as storage.py).
  2. AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET /
     AZURE_REDIRECT_URI environment variables, as documented in .env.example.

The Client Secret is never stored or returned in plaintext outside this
module: it's encrypted at rest with a Fernet key derived from SECRET_KEY,
and the admin UI only ever sees a masked version of an already-saved secret.
"""

import base64
import hashlib
import json
import os

from cryptography.fernet import Fernet, InvalidToken

import storage


def _fernet():
    secret = os.environ.get("SECRET_KEY", "dev-only-change-me").encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def _encrypt(value):
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(token):
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        # SECRET_KEY changed since this was saved -- treat as "not set"
        # rather than crashing the whole settings page.
        return None


def _local_config_path():
    if os.environ.get("VERCEL"):
        root = "/tmp"
    else:
        root = os.environ.get("DATA_ROOT") or r"C:\MDX-Digital-ID\Test"
    return os.path.join(root, "sso_settings.json")


def _load_stored():
    """Returns the raw stored row (still-encrypted secret) or None."""
    if storage.db_configured():
        return storage.get_sso_settings()
    path = _local_config_path()
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_stored(tenant_id, client_id, client_secret_encrypted, redirect_uri, enabled):
    if storage.db_configured():
        storage.save_sso_settings(tenant_id, client_id, client_secret_encrypted, redirect_uri, enabled)
        return
    path = _local_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "tenant_id": tenant_id,
            "client_id": client_id,
            "client_secret_encrypted": client_secret_encrypted,
            "redirect_uri": redirect_uri,
            "enabled": enabled,
        }, f)


def get_effective_config():
    """Merged, decrypted config -- admin-saved values win, env vars fill gaps."""
    stored = _load_stored() or {}
    tenant_id = stored.get("tenant_id") or os.environ.get("AZURE_TENANT_ID", "")
    client_id = stored.get("client_id") or os.environ.get("AZURE_CLIENT_ID", "")
    client_secret = _decrypt(stored.get("client_secret_encrypted")) or os.environ.get("AZURE_CLIENT_SECRET", "")
    redirect_uri = stored.get("redirect_uri") or os.environ.get("AZURE_REDIRECT_URI", "")
    if "enabled" in stored:
        enabled = bool(stored.get("enabled"))
    else:
        enabled = bool(tenant_id and client_id and client_secret and redirect_uri)
    return {
        "tenant_id": tenant_id.strip(),
        "client_id": client_id.strip(),
        "client_secret": client_secret,
        "redirect_uri": redirect_uri.strip(),
        "enabled": enabled,
    }


def is_configured():
    cfg = get_effective_config()
    return bool(cfg["tenant_id"] and cfg["client_id"] and cfg["client_secret"] and cfg["redirect_uri"])


def is_enabled():
    cfg = get_effective_config()
    return cfg["enabled"] and is_configured()


def masked_secret():
    cfg = get_effective_config()
    secret = cfg["client_secret"]
    if not secret:
        return ""
    tail = secret[-4:] if len(secret) >= 4 else secret
    return "•" * 16 + tail


def save_config(tenant_id, client_id, client_secret, redirect_uri, enabled):
    """client_secret may be blank/None to mean 'keep the existing secret'."""
    tenant_id = (tenant_id or "").strip()
    client_id = (client_id or "").strip()
    redirect_uri = (redirect_uri or "").strip()

    if client_secret:
        secret_encrypted = _encrypt(client_secret.strip())
    else:
        existing = _load_stored() or {}
        secret_encrypted = existing.get("client_secret_encrypted")

    _save_stored(tenant_id, client_id, secret_encrypted, redirect_uri, bool(enabled))


def authority():
    cfg = get_effective_config()
    return f"https://login.microsoftonline.com/{cfg['tenant_id']}"
