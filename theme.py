"""Admin-editable site theme: colors, fonts, density, and which nav links /
portal tabs / dashboard cards are shown (and in what order).

Same dual-mode persistence pattern as sso_config.py: a Postgres key-value
row when a database is configured, else a local JSON file next to the
Excel "database" on a LAN deployment.

Two versions are kept -- "draft" (edited on /admin/design, safe to tinker
with) and "published" (what every visitor actually sees). Publishing just
copies draft -> published. An admin viewing any page with ?preview_theme=1
sees the draft instead, so changes can be checked live before going out to
all ~300 staff.
"""

import copy
import json
import os

import storage

DEFAULT_THEME = {
    "colors": {
        "canvas": "#2a1330",
        "canvas_light": "#3a1c40",
        "text_primary": "#ffffff",
        "mdx_red": "#e30a0a",
        "mdx_indigo": "#8b89c9",
    },
    "font_body": "archivo",
    "density": "comfortable",
    "nav_links": [
        {"id": "brand", "label": "Middlesex University Dubai", "enabled": True},
        {"id": "sign_out", "label": "Sign Out", "enabled": True},
    ],
    "portal_tabs": [
        {"id": "register", "label": "New Staff Registration", "enabled": True},
        {"id": "activate", "label": "Track ID Lookup", "enabled": True},
    ],
    "dashboard_cards": [
        {"id": "sso", "label": "Microsoft SSO", "enabled": True},
        {"id": "wallets", "label": "Digital Wallets", "enabled": True},
        {"id": "staff", "label": "Staff Digital IDs", "enabled": True},
        {"id": "activity", "label": "Activity Log", "enabled": True},
        {"id": "design", "label": "Design Settings", "enabled": True},
    ],
}

FONT_STACKS = {
    "archivo": "\"Archivo\", \"Dax\", \"Helvetica Neue\", Arial, sans-serif",
    "system": "-apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif",
    "serif": "Georgia, \"Times New Roman\", serif",
    "mono": "\"Courier New\", ui-monospace, monospace",
}

DENSITY_SCALE = {"compact": "0.82", "comfortable": "1", "spacious": "1.2"}

_KEYS = ("draft", "published")


def _local_path(version):
    if os.environ.get("VERCEL"):
        root = "/tmp"
    else:
        root = os.environ.get("DATA_ROOT") or r"C:\MDX-Digital-ID\Test"
    return os.path.join(root, f"theme_{version}.json")


def _merge_defaults(data):
    """Fills in any keys missing from an older/partial saved blob so new
    theme fields introduced later don't crash existing installs."""
    merged = copy.deepcopy(DEFAULT_THEME)
    if not isinstance(data, dict):
        return merged
    merged["colors"].update(data.get("colors") or {})
    merged["font_body"] = data.get("font_body") or merged["font_body"]
    merged["density"] = data.get("density") or merged["density"]
    for list_key in ("nav_links", "portal_tabs", "dashboard_cards"):
        items = data.get(list_key)
        if items:
            merged[list_key] = items
    return merged


def _load(version):
    assert version in _KEYS
    if storage.db_configured():
        raw = storage.get_setting(f"theme_{version}")
    else:
        path = _local_path(version)
        raw = None
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
    if not raw:
        return copy.deepcopy(DEFAULT_THEME)
    try:
        return _merge_defaults(json.loads(raw))
    except (ValueError, TypeError):
        return copy.deepcopy(DEFAULT_THEME)


def _save(version, data):
    assert version in _KEYS
    raw = json.dumps(data)
    if storage.db_configured():
        storage.set_setting(f"theme_{version}", raw)
        return
    path = _local_path(version)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(raw)


def get_draft():
    return _load("draft")


def get_published():
    return _load("published")


def save_draft(data):
    _save("draft", _merge_defaults(data))


def publish():
    _save("published", get_draft())


def reset_draft_to_default():
    _save("draft", copy.deepcopy(DEFAULT_THEME))


def active_theme(is_preview):
    return get_draft() if is_preview else get_published()


def enabled_items(theme, list_key):
    return [item for item in theme.get(list_key, []) if item.get("enabled", True)]


def css_overrides(theme):
    """A <style> body redefining just the tokens the admin can change --
    everything else in style.css keeps working off these same variable
    names, so this alone re-themes the whole site."""
    colors = theme.get("colors", {})
    font_stack = FONT_STACKS.get(theme.get("font_body"), FONT_STACKS["archivo"])
    density = DENSITY_SCALE.get(theme.get("density"), "1")
    lines = [":root {"]
    if colors.get("canvas"):
        lines.append(f"  --canvas: {colors['canvas']};")
    if colors.get("canvas_light"):
        lines.append(f"  --canvas-light: {colors['canvas_light']};")
    if colors.get("text_primary"):
        lines.append(f"  --text-primary: {colors['text_primary']};")
    if colors.get("mdx_red"):
        lines.append(f"  --mdx-red: {colors['mdx_red']};")
    if colors.get("mdx_indigo"):
        lines.append(f"  --mdx-indigo: {colors['mdx_indigo']};")
    lines.append(f"  --font-body: {font_stack};")
    lines.append(f"  --density-scale: {density};")
    lines.append("}")
    return "\n".join(lines)
