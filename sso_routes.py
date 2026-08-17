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
from urllib.parse import quote

from flask import Blueprint, redirect, request, session, url_for

import auth_microsoft
import sso_config
import sso_photo_cache

sso_bp = Blueprint("sso", __name__)


def _fail(message, identity=None):
    # Stashed in both the session AND the redirect URL -- some corporate
    # networks/browsers drop the session cookie across the Microsoft
    # redirect round-trip, which previously made failures bounce back to
    # the login page with no visible error at all. The query param is a
    # robust fallback that doesn't depend on the cookie surviving.
    session["sso_error"] = message
    session.permanent = True
    # Logged so failed attempts are visible in Admin > Activity Log --
    # previously only successful sign-ins were recorded, so a user reporting
    # "it just doesn't work" left no server-side trace to diagnose from.
    import app as app_module
    app_module.log_event("staff_sso_failed", identity or "unknown", message)
    return redirect(url_for("index", sso_error=message))


@sso_bp.route("/auth/microsoft/login")
def microsoft_login():
    if not sso_config.is_enabled():
        return _fail("Microsoft Sign-In isn't enabled on this portal yet.")

    state = secrets.token_urlsafe(24)
    session.permanent = True
    session["oauth_state"] = state
    try:
        auth_url = auth_microsoft.build_authorize_url(state)
    except auth_microsoft.SSONotConfigured as exc:
        return _fail(str(exc))
    return redirect(auth_url)


@sso_bp.route("/api/auth/azure/callback")
def microsoft_callback():
    import app as app_module  # local import avoids a circular import with app.py

    # Recorded unconditionally, before any check can fail -- if a user's
    # attempt never shows up here at all, the browser never made it back to
    # us (blocked/redirected elsewhere by Azure, a network proxy, etc.)
    # rather than failing one of the checks below.
    app_module.log_event(
        "staff_sso_callback_hit",
        "unknown",
        f"error={request.args.get('error') or '-'} has_state={'state' in request.args} has_code={'code' in request.args}",
    )

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
    except Exception as exc:
        # acquire_token_by_auth_code is documented to return error info in
        # the result dict rather than raise -- but MSAL can still throw for
        # things outside that contract (a malformed/expired code, a token
        # signature/claims validation failure, a transient network error).
        # Previously unhandled, this crashed with a bare 500 and no log
        # entry at all, which read as the sign-in silently doing nothing.
        return _fail(f"Microsoft sign-in failed unexpectedly during token exchange: {exc}")

    if "error" in result:
        message = result.get("error_description") or result.get("error")
        return _fail(f"Microsoft sign-in failed: {message}")

    id_claims = result.get("id_token_claims") or {}
    claimed_identity = id_claims.get("preferred_username") or id_claims.get("email") or id_claims.get("upn")
    try:
        tenant_ok = auth_microsoft.verify_tenant(id_claims)
    except Exception as exc:
        return _fail(f"Could not verify sign-in tenant: {exc}", identity=claimed_identity)
    if not tenant_ok:
        return _fail(
            f"This Microsoft account doesn't belong to the university's approved organization (tid={id_claims.get('tid') or '-'}).",
            identity=claimed_identity,
        )

    try:
        profile = auth_microsoft.fetch_profile(result["access_token"])
    except Exception as exc:
        return _fail(f"Could not retrieve your profile from Microsoft Graph: {exc}", identity=claimed_identity)

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
    # profile stays in the session, but the photo is stashed server-side
    # (see sso_photo_cache) rather than in the cookie -- a real Graph photo
    # is easily tens of KB, which blows past the ~4KB per-cookie limit and
    # gets silently dropped by the browser, taking ms_user_id down with it.
    session["ms_user_id"] = profile["ms_user_id"]
    session["sso_prefill"] = profile
    sso_photo_cache.stash_photo(profile["ms_user_id"], photo_data_url)
    return redirect(url_for("account"))


@sso_bp.route("/auth/logout")
def microsoft_logout():
    session.pop("ms_user_id", None)
    session.pop("sso_prefill", None)
    session.pop("sso_photo", None)
    session["flash_toast"] = "Signed out successfully"

    # Clearing our own session isn't enough -- the browser still holds an
    # active Microsoft sign-in session, so "Sign in with Microsoft" would
    # silently re-authenticate with no credential prompt at all. Routing
    # through Microsoft's own logout endpoint first ends that session too,
    # so the next sign-in actually asks for credentials again.
    if sso_config.is_configured():
        post_logout = quote(url_for("index", _external=True), safe="")
        return redirect(f"{sso_config.authority()}/oauth2/v2.0/logout?post_logout_redirect_uri={post_logout}")
    return redirect(url_for("index"))
