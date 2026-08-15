"""Admin portal: Microsoft SSO configuration + Staff Digital ID management.

A single shared administrator login (ADMIN_USERNAME / ADMIN_PASSWORD in
.env) gates every route here -- there's no separate admin-user table, which
matches this app's existing minimal-auth footprint (Google Wallet
credentials are likewise just a file path in .env, not a managed secret
store). Every route below requires an authenticated admin session.
"""

import hmac
import os
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, session

import sso_config
import auth_microsoft
import wallet
import wallet_apple

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _check_credentials(username, password):
    expected_user = os.environ.get("ADMIN_USERNAME", "")
    expected_pass = os.environ.get("ADMIN_PASSWORD", "")
    if not expected_user or not expected_pass:
        return False
    return (
        hmac.compare_digest(username or "", expected_user)
        and hmac.compare_digest(password or "", expected_pass)
    )


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if not (os.environ.get("ADMIN_USERNAME") and os.environ.get("ADMIN_PASSWORD")):
            error = "Admin login isn't configured yet -- set ADMIN_USERNAME and ADMIN_PASSWORD in .env."
        elif _check_credentials(request.form.get("username", ""), request.form.get("password", "")):
            session["is_admin"] = True
            return redirect(request.args.get("next") or url_for("admin.dashboard"))
        else:
            error = "Invalid administrator username or password."
    return render_template("admin_login.html", error=error)


@admin_bp.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin.login"))


@admin_bp.route("/")
@admin_required
def dashboard():
    return render_template(
        "admin_dashboard.html",
        sso_configured=sso_config.is_configured(),
        sso_enabled=sso_config.is_enabled(),
        google_configured=wallet.is_configured(),
        apple_configured=wallet_apple.is_configured(),
    )


@admin_bp.route("/sso", methods=["GET", "POST"])
@admin_required
def sso_settings():
    test_result = None
    if request.method == "POST":
        if request.form.get("action") == "test":
            ok, message = auth_microsoft.test_connection()
            test_result = {"ok": ok, "message": message}
        else:
            sso_config.save_config(
                tenant_id=request.form.get("tenant_id", ""),
                client_id=request.form.get("client_id", ""),
                client_secret=request.form.get("client_secret", ""),
                redirect_uri=request.form.get("redirect_uri", ""),
                enabled=request.form.get("enabled") == "on",
            )
            return redirect(url_for("admin.sso_settings", saved=1))

    cfg = sso_config.get_effective_config()
    portal_url = os.environ.get("PORTAL_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    return render_template(
        "admin_sso.html",
        cfg=cfg,
        masked_secret=sso_config.masked_secret(),
        suggested_redirect_uri=f"{portal_url}/api/auth/azure/callback",
        saved=request.args.get("saved") == "1",
        test_result=test_result,
    )


@admin_bp.route("/wallets")
@admin_required
def wallets():
    google_ok, google_msg = wallet.test_connection()
    apple_ok, apple_msg = wallet_apple.test_connection()
    return render_template(
        "admin_wallets.html",
        google_configured=wallet.is_configured(),
        google_ok=google_ok, google_msg=google_msg,
        apple_configured=wallet_apple.is_configured(),
        apple_ok=apple_ok, apple_msg=apple_msg,
    )


@admin_bp.route("/staff")
@admin_required
def staff():
    import app as app_module  # local import: avoids a circular import at module load time

    query = (request.args.get("q") or "").strip()
    records = app_module.list_digital_ids(query or None)
    return render_template("admin_staff.html", records=records, query=query)


@admin_bp.route("/staff/<token>/status", methods=["POST"])
@admin_required
def set_status(token):
    import app as app_module

    new_status = request.form.get("status")
    if new_status in ("Active", "Suspended", "Deactivated", "Expired"):
        app_module.update_digital_id_status(token, new_status)
    return redirect(request.referrer or url_for("admin.staff"))


@admin_bp.route("/staff/<token>/regenerate-qr", methods=["POST"])
@admin_required
def regenerate_qr(token):
    import app as app_module

    app_module.regenerate_digital_id_qr(token)
    return redirect(request.referrer or url_for("admin.staff"))
