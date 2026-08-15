"""Google Wallet Generic Pass integration.

Builds a signed "Add to Google Wallet" save URL by describing the pass class
and object inline inside the JWT payload (Google's documented issuing pattern
for brand-new objects) rather than pre-creating the class via a separate REST
call. Returns None whenever the required .env config is missing so the caller
can render a "not configured" state instead of failing.
"""

import json
import os
import time

import jwt
import requests


def _env(name, default=None):
    value = os.environ.get(name, default)
    return value.strip() if isinstance(value, str) else value


def is_configured():
    key_file = _env("GOOGLE_WALLET_SERVICE_ACCOUNT_FILE")
    return bool(
        _env("GOOGLE_WALLET_ISSUER_ID")
        and key_file
        and os.path.exists(key_file)
    )


def _load_service_account():
    with open(_env("GOOGLE_WALLET_SERVICE_ACCOUNT_FILE"), "r", encoding="utf-8") as f:
        return json.load(f)


def build_save_url(*, staff_id, full_name, job_title, department,
                    employment_status, verify_url):
    """Returns a https://pay.google.com/gp/v/save/<jwt> URL, or None if unconfigured."""
    if not is_configured():
        return None

    issuer_id = _env("GOOGLE_WALLET_ISSUER_ID")
    class_suffix = _env("GOOGLE_WALLET_CLASS_SUFFIX", "mdx_staff_digital_id")
    class_id = f"{issuer_id}.{class_suffix}"
    object_id = f"{issuer_id}.{staff_id}"

    portal_url = _env("PORTAL_BASE_URL", "http://127.0.0.1:5000")
    logo_url = _env("GOOGLE_WALLET_LOGO_URL") or f"{portal_url}/static/images/mdx-logo.png"
    hero_url = _env("GOOGLE_WALLET_HERO_IMAGE_URL")

    generic_class = {"id": class_id}

    generic_object = {
        "id": object_id,
        "classId": class_id,
        "genericType": "GENERIC_TYPE_UNSPECIFIED",
        "hexBackgroundColor": "#0d2340",
        "logo": {
            "sourceUri": {"uri": logo_url},
            "contentDescription": {
                "defaultValue": {"language": "en", "value": "Middlesex University Dubai"}
            },
        },
        "cardTitle": {
            "defaultValue": {"language": "en", "value": "Middlesex University Dubai"}
        },
        "header": {"defaultValue": {"language": "en", "value": full_name}},
        "subheader": {"defaultValue": {"language": "en", "value": job_title or ""}},
        "textModulesData": [
            {"id": "department", "header": "DEPARTMENT", "body": department or ""},
            {"id": "staffId", "header": "STAFF ID", "body": staff_id},
            {"id": "employmentStatus", "header": "STATUS", "body": employment_status or ""},
        ],
        "barcode": {
            "type": "QR_CODE",
            "value": verify_url,
            "alternateText": staff_id,
        },
        "linksModuleData": {
            "uris": [
                {
                    "uri": portal_url,
                    "description": "View University Digital ID Portal",
                    "id": "portal_link",
                }
            ]
        },
    }
    if hero_url:
        generic_object["heroImage"] = {"sourceUri": {"uri": hero_url}}

    service_account = _load_service_account()
    claims = {
        "iss": service_account["client_email"],
        "aud": "google",
        "origins": [],
        "typ": "savetowallet",
        "iat": int(time.time()),
        "payload": {
            "genericClasses": [generic_class],
            "genericObjects": [generic_object],
        },
    }

    token = jwt.encode(claims, service_account["private_key"], algorithm="RS256")
    return f"https://pay.google.com/gp/v/save/{token}"


def test_connection():
    """Used by the admin 'Test Connection' button -- confirms the service
    account key is valid and Google actually accepts it, without needing a
    real staff member's save flow."""
    if not is_configured():
        return False, "Issuer ID and a valid service account key file must be set first."
    try:
        service_account = _load_service_account()
    except Exception as exc:
        return False, f"Could not load service account file: {exc}"

    now = int(time.time())
    claims = {
        "iss": service_account["client_email"],
        "scope": "https://www.googleapis.com/auth/wallet_object.issuer",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }
    assertion = jwt.encode(claims, service_account["private_key"], algorithm="RS256")
    try:
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
            timeout=10,
        )
    except requests.RequestException as exc:
        return False, f"Could not reach Google's token endpoint: {exc}"

    if resp.status_code == 200 and "access_token" in resp.json():
        return True, "Service account credentials accepted by Google Wallet."
    return False, f"Google rejected the service account credentials (status {resp.status_code})."
