"""Short-lived server-side stash for the Microsoft Graph profile photo
fetched during SSO sign-in.

The photo used to be stored directly in session["sso_photo"] as a base64
data: URL. Flask's session here is a plain client-side cookie (signed,
not server-backed) -- browsers cap a single cookie around ~4KB, and a
real Graph profile photo blows past that easily. When it does, the
browser silently drops the oversized Set-Cookie entirely, so the *next*
request loses session["ms_user_id"] along with it and bounces back to
the login page -- even though the sign-in itself succeeded server-side.

Stashing the photo here instead (keyed by ms_user_id, same dual-mode
pattern as theme.py/sso_config.py) keeps the session cookie small no
matter how big the photo is. Consumed once via pop_photo() and then
cleared; a stash entry left over from an abandoned attempt is harmless
and just gets overwritten the next time that user signs in.
"""

import os

import storage

_KEY_PREFIX = "sso_photo:"


def _local_path(ms_user_id):
    if os.environ.get("VERCEL"):
        root = "/tmp"
    else:
        root = os.environ.get("DATA_ROOT") or r"C:\MDX-Digital-ID\Test"
    return os.path.join(root, f"sso_photo_{ms_user_id}.txt")


def stash_photo(ms_user_id, data_url):
    if not ms_user_id or not data_url:
        return
    if storage.db_configured():
        storage.set_setting(_KEY_PREFIX + ms_user_id, data_url)
        return
    path = _local_path(ms_user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data_url)


def get_photo(ms_user_id):
    """Non-destructive read -- mirrors the old session.get("sso_photo")
    used on the welcome hub, which a visitor may reload or revisit."""
    if not ms_user_id:
        return None
    if storage.db_configured():
        return storage.get_setting(_KEY_PREFIX + ms_user_id) or None
    path = _local_path(ms_user_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read() or None


def pop_photo(ms_user_id):
    """Destructive read -- mirrors the old session.pop("sso_photo") used
    when continuing into registration, which consumed it once."""
    value = get_photo(ms_user_id)
    if not ms_user_id or value is None:
        return value
    if storage.db_configured():
        storage.set_setting(_KEY_PREFIX + ms_user_id, "")
    else:
        path = _local_path(ms_user_id)
        if os.path.exists(path):
            os.remove(path)
    return value
