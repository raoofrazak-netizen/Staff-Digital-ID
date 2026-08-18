"""Admin portal: Microsoft SSO configuration + Staff Digital ID management.

A single shared administrator login (ADMIN_USERNAME / ADMIN_PASSWORD in
.env) gates every route here -- there's no separate admin-user table, which
matches this app's existing minimal-auth footprint (Google Wallet
credentials are likewise just a file path in .env, not a managed secret
store). Every route below requires an authenticated admin session.
"""

import hmac
import json
import os
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, session

import sso_config
import auth_microsoft
import theme
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
    import app as app_module  # local import avoids a circular import with app.py

    error = None
    source = request.form.get("source")

    if request.method == "POST":
        username = request.form.get("username", "")
        if not (os.environ.get("ADMIN_USERNAME") and os.environ.get("ADMIN_PASSWORD")):
            error = "Admin login isn't configured yet -- set ADMIN_USERNAME and ADMIN_PASSWORD in .env."
        elif _check_credentials(username, request.form.get("password", "")):
            session["is_admin"] = True
            session["admin_username"] = username
            session["flash_toast"] = "Signed in successfully"
            app_module.log_event("admin_login", username, "Admin signed in")
            return redirect(request.args.get("next") or url_for("admin.dashboard"))
        else:
            error = "Invalid administrator username or password."

    if source == "main":
        return render_template("login.html", sso_configured=sso_config.is_enabled(), sso_error=None, admin_error=error)
    return render_template("admin_login.html", error=error)


@admin_bp.route("/logout")
def logout():
    session.pop("is_admin", None)
    session.pop("admin_username", None)
    session["flash_toast"] = "Signed out successfully"
    return redirect(url_for("index"))


@admin_bp.route("/")
@admin_required
def dashboard():
    sso_configured = sso_config.is_configured()
    sso_enabled = sso_config.is_enabled()
    wallets_configured = wallet.is_configured() or wallet_apple.is_configured()
    card_meta = {
        "sso": {
            "chip_class": "ok" if sso_enabled else ("off" if not sso_configured else "bad"),
            "chip_text": "Enabled" if sso_enabled else ("Not Configured" if not sso_configured else "Configured, Disabled"),
            "description": "Tenant ID, Client ID, Client Secret, and Redirect URI for staff Microsoft sign-in.",
            "href": url_for("admin.sso_settings"), "cta": "Configure SSO",
        },
        "wallets": {
            "chip_class": "ok" if wallets_configured else "off",
            "chip_text": "Configured" if wallets_configured else "Not Configured",
            "description": "Apple Wallet and Google Wallet pass-issuing status and connectivity checks.",
            "href": url_for("admin.wallets"), "cta": "View Wallet Status",
        },
        "staff": {
            "chip_class": "ok", "chip_text": "Management",
            "description": "Search staff records, activate/deactivate IDs, and regenerate QR codes.",
            "href": url_for("admin.staff"), "cta": "Manage Staff IDs",
        },
        "activity": {
            "chip_class": "ok", "chip_text": "Audit Trail",
            "description": "Admin logins, staff Microsoft sign-ins, and Digital ID create/update history.",
            "href": url_for("admin.activity"), "cta": "View Activity Log",
        },
        "design": {
            "chip_class": "ok", "chip_text": "Customize",
            "description": "Colors, fonts, spacing, and which tabs/cards/nav links are shown -- no code required.",
            "href": url_for("admin.design_settings"), "cta": "Open Design Settings",
        },
    }
    return render_template(
        "admin_dashboard.html",
        card_meta=card_meta,
        flash_toast=session.pop("flash_toast", None),
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
    portal_url = (os.environ.get("PORTAL_BASE_URL") or "http://127.0.0.1:5000").rstrip("/")
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


@admin_bp.route("/activity")
@admin_required
def activity():
    import app as app_module

    entries = app_module.list_activity_log(300)
    return render_template("admin_activity.html", entries=entries)


@admin_bp.route("/staff")
@admin_required
def staff():
    import app as app_module  # local import: avoids a circular import at module load time

    query = (request.args.get("q") or "").strip()
    records = app_module.list_digital_ids(query or None)
    return render_template(
        "admin_staff.html", records=records, query=query,
        flash_toast=session.pop("flash_toast", None),
    )


@admin_bp.route("/staff/<token>/status", methods=["POST"])
@admin_required
def set_status(token):
    import app as app_module

    new_status = request.form.get("status")
    if new_status in ("Active", "Suspended", "Deactivated", "Expired"):
        app_module.update_digital_id_status(token, new_status)
        app_module.log_event(
            "digital_id_status_changed",
            session.get("admin_username", "admin"),
            f"Status changed to {new_status} for token {token}",
        )
        session["flash_toast"] = f"Status updated to {new_status}"
    return redirect(request.referrer or url_for("admin.staff"))


@admin_bp.route("/staff/<token>/regenerate-qr", methods=["POST"])
@admin_required
def regenerate_qr(token):
    import app as app_module

    app_module.regenerate_digital_id_qr(token)
    app_module.log_event(
        "digital_id_qr_regenerated",
        session.get("admin_username", "admin"),
        f"QR code regenerated for token {token}",
    )
    session["flash_toast"] = "QR code regenerated"
    return redirect(request.referrer or url_for("admin.staff"))


def _parse_reorder_list(raw_json, fallback):
    """raw_json is a JSON array of {id, label, enabled} built client-side by
    the drag-reorder widget. Falls back to the existing list if missing/
    malformed so a broken submit can't wipe the config."""
    if not raw_json:
        return fallback
    try:
        items = json.loads(raw_json)
    except ValueError:
        return fallback
    if not isinstance(items, list):
        return fallback
    cleaned = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        cleaned.append({
            "id": item["id"],
            "label": (item.get("label") or "").strip() or item["id"],
            "enabled": bool(item.get("enabled")),
        })
    return cleaned or fallback


def _parse_registration_fields(raw_json, fallback):
    """Same shape as _parse_reorder_list, plus "frozen" (locked against
    staff editing) -- and "required" is never sent by the client widget
    (it's a fixed schema property, not admin-editable), so it's always
    carried over from the matching fallback item by id."""
    fallback_by_id = {item["id"]: item for item in fallback}
    if not raw_json:
        return fallback
    try:
        items = json.loads(raw_json)
    except ValueError:
        return fallback
    if not isinstance(items, list):
        return fallback
    cleaned = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        existing = fallback_by_id.get(item["id"], {})
        cleaned.append({
            "id": item["id"],
            "label": (item.get("label") or "").strip() or item["id"],
            "enabled": bool(item.get("enabled")),
            "frozen": bool(item.get("frozen")),
            "required": bool(existing.get("required")),
        })
    return cleaned or fallback


@admin_bp.route("/design", methods=["GET", "POST"])
@admin_required
def design_settings():
    draft = theme.get_draft()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "reset":
            theme.reset_draft_to_default()
            session["flash_toast"] = "Design draft reset to default"
            return redirect(url_for("admin.design_settings"))

        if action == "publish":
            theme.publish()
            session["flash_toast"] = "Design changes published -- now live for everyone"
            return redirect(url_for("admin.design_settings"))

        # action == "save" (or anything else) -- persist the draft only.
        new_draft = {
            "colors": {
                "canvas": request.form.get("canvas") or draft["colors"]["canvas"],
                "canvas_light": request.form.get("canvas_light") or draft["colors"]["canvas_light"],
                "text_primary": request.form.get("text_primary") or draft["colors"]["text_primary"],
                "mdx_red": request.form.get("mdx_red") or draft["colors"]["mdx_red"],
                "mdx_indigo": request.form.get("mdx_indigo") or draft["colors"]["mdx_indigo"],
            },
            "font_body": request.form.get("font_body") or draft["font_body"],
            "density": request.form.get("density") or draft["density"],
            "nav_links": _parse_reorder_list(request.form.get("nav_links_json"), draft["nav_links"]),
            "portal_tabs": _parse_reorder_list(request.form.get("portal_tabs_json"), draft["portal_tabs"]),
            "dashboard_cards": _parse_reorder_list(request.form.get("dashboard_cards_json"), draft["dashboard_cards"]),
            "registration_fields": _parse_registration_fields(request.form.get("registration_fields_json"), draft["registration_fields"]),
        }
        theme.save_draft(new_draft)
        session["flash_toast"] = "Design draft saved"
        return redirect(url_for("admin.design_settings"))

    return render_template(
        "admin_design.html",
        draft=draft,
        font_stacks=theme.FONT_STACKS,
        brand_swatches=theme.BRAND_SWATCHES,
        flash_toast=session.pop("flash_toast", None),
    )
