"""Microsoft Entra ID (Azure AD) sign-in and Microsoft Graph profile lookup.

Uses MSAL's confidential-client Authorization Code flow (OAuth 2.0 /
OpenID Connect against the Microsoft identity platform). Every call here
reads its Tenant ID / Client ID / Client Secret / Redirect URI from
sso_config.get_effective_config() at call time, so an admin can update
settings without restarting the app.
"""

import requests
import msal

import sso_config

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = ["User.Read"]


class SSONotConfigured(Exception):
    pass


def _msal_app():
    cfg = sso_config.get_effective_config()
    if not sso_config.is_configured():
        raise SSONotConfigured("Microsoft SSO is not fully configured.")
    try:
        # MSAL eagerly fetches the tenant's OIDC discovery document here --
        # a bad Tenant ID (or a network hiccup reaching Microsoft) surfaces
        # as a bare ValueError, which we normalize to SSONotConfigured so
        # every caller can handle "can't sign in right now" with one except.
        return msal.ConfidentialClientApplication(
            client_id=cfg["client_id"],
            client_credential=cfg["client_secret"],
            authority=sso_config.authority(),
        )
    except ValueError as exc:
        raise SSONotConfigured(f"Could not reach Microsoft Entra ID for this Tenant ID: {exc}") from exc


def build_authorize_url(state):
    app = _msal_app()
    cfg = sso_config.get_effective_config()
    return app.get_authorization_request_url(
        SCOPES,
        state=state,
        redirect_uri=cfg["redirect_uri"],
    )


def acquire_token_by_auth_code(code):
    """Exchanges an authorization code for tokens. Returns the MSAL result
    dict (has "access_token"/"id_token_claims" on success, "error"/
    "error_description" on failure -- never raises for a bad code, only
    for a config problem)."""
    app = _msal_app()
    cfg = sso_config.get_effective_config()
    return app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=cfg["redirect_uri"],
    )


def verify_tenant(id_token_claims):
    """Confirms the signed-in user's token was actually issued by the
    configured tenant -- the "tid" claim -- rather than trusting whatever
    tenant Microsoft's login page happened to authenticate against."""
    cfg = sso_config.get_effective_config()
    return bool(id_token_claims) and id_token_claims.get("tid") == cfg["tenant_id"]


def fetch_profile(access_token):
    """Fetches /me from Microsoft Graph. Returns a dict of the fields this
    app cares about, with anything Graph didn't return left as None/"" so
    the caller can leave those form fields blank for manual entry."""
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(
        f"{GRAPH_BASE}/me"
        "?$select=id,givenName,surname,displayName,mail,userPrincipalName,"
        "employeeId,department,jobTitle,officeLocation,mobilePhone,businessPhones",
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    username = data.get("userPrincipalName") or ""
    # Local-part of the Azure AD sign-in name -- the closest thing this app
    # has to the physical badge's "UK IT User ID" / "Local Login" fields,
    # since Graph doesn't expose a separate on-prem AD username here.
    login_local_part = username.split("@")[0] if "@" in username else username

    return {
        "ms_user_id": data.get("id"),
        "first_name": data.get("givenName") or "",
        "last_name": data.get("surname") or "",
        "full_name": data.get("displayName") or "",
        "email": data.get("mail") or username or "",
        "username": username,
        "staff_id": data.get("employeeId") or "",
        "department": data.get("department") or "",
        "job_title": data.get("jobTitle") or "",
        "office_location": data.get("officeLocation") or "",
        "mobile_number": data.get("mobilePhone") or (data.get("businessPhones") or [None])[0] or "",
        "uk_it_user_id": login_local_part,
        "local_login": login_local_part,
    }


def fetch_profile_photo_data_url(access_token):
    """Returns a data: URL for the user's Graph profile photo, or None if
    they don't have one set (Graph returns 404 in that case -- not an error
    this app needs to surface, the registration form just falls back to a
    manual upload)."""
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(f"{GRAPH_BASE}/me/photo/$value", headers=headers, timeout=10)
    if resp.status_code != 200:
        return None
    content_type = resp.headers.get("Content-Type", "image/jpeg")
    import base64
    encoded = base64.b64encode(resp.content).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def test_connection():
    """Used by the admin 'Test Connection' button -- confirms the tenant's
    OIDC discovery document is reachable and the app registration's client
    credentials are accepted, without involving a real user sign-in."""
    if not sso_config.is_configured():
        return False, "Tenant ID, Client ID, Client Secret, and Redirect URI must all be set first."
    try:
        app = _msal_app()
    except SSONotConfigured as exc:
        return False, str(exc)

    try:
        resp = requests.get(f"{sso_config.authority()}/v2.0/.well-known/openid-configuration", timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return False, f"Could not reach Microsoft Entra ID for this Tenant ID: {exc}"

    try:
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    except Exception as exc:
        return False, f"Client credential check failed: {exc}"

    if "access_token" in result:
        return True, "Tenant reachable and Client ID/Secret accepted by Microsoft Entra ID."
    return False, result.get("error_description") or result.get("error") or "Unknown error validating credentials."
