"""Staff-facing Microsoft SSO sign-in: /auth/microsoft/login kicks off the
Microsoft Entra ID OAuth2/OIDC Authorization Code flow, and
/api/auth/azure/callback completes it -- verifying the token came from the
configured tenant, pulling the staff member's profile (and photo) from
Microsoft Graph, and then either sending an already-registered staff
member straight to their existing Digital ID, or into the registration
form with their known fields pre-filled.

Errors redirect back to "/" with the message stashed in the session
(rather than rendering index.html directly from here) so index()'s own
route keeps sole responsibility for assembling that template's full
context (departments/statuses/genders/etc).
"""

import secrets

from flask import Blueprint, redirect, request, session, url_for

import auth_microsoft
import sso_config

sso_bp = Blueprint("sso", __name__)


def _fail(message):
    session["sso_error"] = message
    return redirect(url_for("index"))


@sso_bp.route("/auth/microsoft/login")
def microsoft_login():
    if not sso_config.is_enabled():
        return _fail("Microsoft Sign-In isn't enabled on this portal yet.")

    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    try:
        auth_url = auth_microsoft.build_authorize_url(state)
    except auth_microsoft.SSONotConfigured as exc:
        return _fail(str(exc))
    return redirect(auth_url)


@sso_bp.route("/api/auth/azure/callback")
def microsoft_callback():
    import app as app_module  # local import avoids a circular import with app.py

    if request.args.get("error"):
        message = request.args.get("error_description") or request.args.get("error")
        return _fail(f"Microsoft sign-in failed: {message}")

    expected_state = session.pop("oauth_state", None)
    if not expected_state or request.args.get("state") != expected_state:
        return _fail("Sign-in session expired or is invalid. Please try again.")

    code = request.args.get("code")
    if not code:
        return _fail("Microsoft did not return a sign-in code.")

    try:
        result = auth_microsoft.acquire_token_by_auth_code(code)
    except auth_microsoft.SSONotConfigured as exc:
        return _fail(str(exc))

    if "error" in result:
        message = result.get("error_description") or result.get("error")
        return _fail(f"Microsoft sign-in failed: {message}")

    id_claims = result.get("id_token_claims") or {}
    if not auth_microsoft.verify_tenant(id_claims):
        return _fail("This Microsoft account doesn't belong to the university's approved organization.")

    try:
        profile = auth_microsoft.fetch_profile(result["access_token"])
    except Exception:
        return _fail("Could not retrieve your profile from Microsoft Graph.")

    try:
        photo_data_url = auth_microsoft.fetch_profile_photo_data_url(result["access_token"])
    except Exception:
        photo_data_url = None

    app_module.log_event(
        "staff_sso_login",
        profile.get("email") or profile.get("username") or profile.get("ms_user_id"),
        f"Signed in via Microsoft ({profile.get('full_name') or profile.get('first_name') or ''})".strip(),
    )

    # Every sign-in lands on the welcome hub -- it looks up whether this
    # Microsoft account (or, failing that, matching Staff ID) already has
    # an active Digital ID and adapts what it shows accordingly. The
    # profile/photo are kept in the session (not the URL) since the photo
    # may be a data: URL too large for a query string, and /portal reads
    # them back out if the visitor continues into registration from there.
    session["ms_user_id"] = profile["ms_user_id"]
    session["sso_prefill"] = profile
    session["sso_photo"] = photo_data_url
    return redirect(url_for("account"))


@sso_bp.route("/auth/logout")
def microsoft_logout():
    session.pop("ms_user_id", None)
    session.pop("sso_prefill", None)
    session.pop("sso_photo", None)
    session["flash_toast"] = "Signed out successfully"
    return redirect(url_for("index"))
