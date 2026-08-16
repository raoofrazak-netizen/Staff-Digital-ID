"""Persistent storage for staff records and generated files.

Vercel serverless functions don't share a filesystem between invocations (or
even between requests to the same "instance"), so the original Excel +
local-file storage this app used can't work there -- a photo/QR/record
written during one request is gone by the next. This module adds a second,
real-storage backend (Postgres for records, Vercel Blob for photos/QR
images) and is used instead of the local files whenever a database is
configured. When it isn't (e.g. the LAN-hosted deployment), app.py falls
back to the original openpyxl + local-file behavior untouched.
"""

import os

import psycopg2
from vercel.blob import get as blob_get, put as blob_put

# The third-party `vercel_blob` PyPI package hardcodes the upload `access`
# header to "public" (its own source even says private isn't supported) and
# rejected every upload to this project's Private store. Using Vercel's own
# official `vercel` package instead (pip: "vercel", import: "vercel.blob"),
# which has first-class access="private" support.

_DB_ENV_VARS = ("POSTGRES_URL", "DATABASE_URL", "POSTGRES_PRISMA_URL", "POSTGRES_URL_NON_POOLING")

DIRECTORY_COLUMNS_SQL = ["staff_id", "first_name", "last_name", "email", "department", "job_title", "gender", "employment_status"]
DIRECTORY_DISPLAY = ["Staff ID", "First Name", "Last Name", "Email", "Department", "Job Title", "Gender", "Employment Status"]

DIGITAL_ID_COLUMNS_SQL = [
    "token", "track_id", "staff_id", "first_name", "last_name", "email", "mobile_number",
    "department", "job_title", "gender", "employment_status",
    "photo_url", "qr_url", "created_at", "status", "ms_user_id",
    "category", "uk_it_user_id", "local_login", "misis",
]
DIGITAL_ID_DISPLAY = [
    "Token", "Track ID", "Staff ID", "First Name", "Last Name", "Email", "Mobile Number",
    "Department", "Job Title", "Gender", "Employment Status",
    "Photo Filename", "QR Filename", "Created At", "Status", "Microsoft User ID",
    "Category", "UK IT User ID", "Local Login", "MISIS",
]


def _db_url():
    for name in _DB_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value
    return None


def db_configured():
    return _db_url() is not None


def blob_configured():
    return bool(os.environ.get("BLOB_READ_WRITE_TOKEN"))


def get_connection():
    return psycopg2.connect(_db_url())


def init_db(sample_directory_rows):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS staff_directory (
                    staff_id TEXT PRIMARY KEY,
                    first_name TEXT, last_name TEXT, email TEXT,
                    department TEXT, job_title TEXT, gender TEXT, employment_status TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS digital_ids (
                    token TEXT PRIMARY KEY,
                    track_id TEXT UNIQUE NOT NULL,
                    staff_id TEXT NOT NULL,
                    first_name TEXT, last_name TEXT, email TEXT, mobile_number TEXT,
                    department TEXT, job_title TEXT, gender TEXT, employment_status TEXT,
                    photo_url TEXT, qr_url TEXT, created_at TEXT, status TEXT,
                    ms_user_id TEXT
                )
            """)
            # Additive, idempotent -- safe to run against a table created
            # before the Microsoft SSO column existed.
            cur.execute("ALTER TABLE digital_ids ADD COLUMN IF NOT EXISTS ms_user_id TEXT")
            cur.execute("ALTER TABLE digital_ids ADD COLUMN IF NOT EXISTS category TEXT")
            cur.execute("ALTER TABLE digital_ids ADD COLUMN IF NOT EXISTS uk_it_user_id TEXT")
            cur.execute("ALTER TABLE digital_ids ADD COLUMN IF NOT EXISTS local_login TEXT")
            cur.execute("ALTER TABLE digital_ids ADD COLUMN IF NOT EXISTS misis TEXT")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sso_settings (
                    id INTEGER PRIMARY KEY,
                    tenant_id TEXT, client_id TEXT, client_secret_encrypted TEXT,
                    redirect_uri TEXT, enabled BOOLEAN DEFAULT FALSE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    id SERIAL PRIMARY KEY,
                    event_type TEXT NOT NULL, actor TEXT, detail TEXT, created_at TEXT
                )
            """)
            cur.execute("SELECT COUNT(*) FROM staff_directory")
            if cur.fetchone()[0] == 0:
                for row in sample_directory_rows:
                    cur.execute(
                        "INSERT INTO staff_directory ({}) VALUES ({})".format(
                            ", ".join(DIRECTORY_COLUMNS_SQL), ", ".join(["%s"] * len(DIRECTORY_COLUMNS_SQL))
                        ),
                        row,
                    )
        conn.commit()
    finally:
        conn.close()


def _row_to_dict(row, display_cols):
    return dict(zip(display_cols, row)) if row else None


def find_directory_record_by_staff_id(staff_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT {} FROM staff_directory WHERE lower(staff_id) = lower(%s)".format(", ".join(DIRECTORY_COLUMNS_SQL)),
                (staff_id,),
            )
            return _row_to_dict(cur.fetchone(), DIRECTORY_DISPLAY)
    finally:
        conn.close()


def find_active_digital_id_by_staff(staff_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT {} FROM digital_ids WHERE lower(staff_id) = lower(%s) AND status = 'Active' LIMIT 1".format(
                    ", ".join(DIGITAL_ID_COLUMNS_SQL)
                ),
                (staff_id,),
            )
            return _row_to_dict(cur.fetchone(), DIGITAL_ID_DISPLAY)
    finally:
        conn.close()


def find_digital_id_by_token(token):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT {} FROM digital_ids WHERE token = %s".format(", ".join(DIGITAL_ID_COLUMNS_SQL)),
                (token,),
            )
            return _row_to_dict(cur.fetchone(), DIGITAL_ID_DISPLAY)
    finally:
        conn.close()


def find_digital_id_by_track(track_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT {} FROM digital_ids WHERE lower(track_id) = lower(%s)".format(", ".join(DIGITAL_ID_COLUMNS_SQL)),
                (track_id,),
            )
            return _row_to_dict(cur.fetchone(), DIGITAL_ID_DISPLAY)
    finally:
        conn.close()


def list_digital_ids(search=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if search:
                needle = f"%{search.strip().lower()}%"
                cur.execute(
                    "SELECT {} FROM digital_ids WHERE lower(staff_id) LIKE %s "
                    "OR lower(first_name || ' ' || last_name) LIKE %s "
                    "OR lower(email) LIKE %s ORDER BY created_at DESC".format(", ".join(DIGITAL_ID_COLUMNS_SQL)),
                    (needle, needle, needle),
                )
            else:
                cur.execute(
                    "SELECT {} FROM digital_ids ORDER BY created_at DESC".format(", ".join(DIGITAL_ID_COLUMNS_SQL))
                )
            return [dict(zip(DIGITAL_ID_DISPLAY, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def update_digital_id_fields(token, fields):
    """fields: dict of SQL column names (from DIGITAL_ID_COLUMNS_SQL) -> new values."""
    if not fields:
        return
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            set_clause = ", ".join(f"{col} = %s" for col in fields)
            cur.execute(f"UPDATE digital_ids SET {set_clause} WHERE token = %s", (*fields.values(), token))
        conn.commit()
    finally:
        conn.close()


def update_digital_id_status(token, status):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE digital_ids SET status = %s WHERE token = %s", (status, token))
        conn.commit()
    finally:
        conn.close()


def append_digital_id(record):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            values = [record[display] for display in DIGITAL_ID_DISPLAY]
            cur.execute(
                "INSERT INTO digital_ids ({}) VALUES ({})".format(
                    ", ".join(DIGITAL_ID_COLUMNS_SQL), ", ".join(["%s"] * len(DIGITAL_ID_COLUMNS_SQL))
                ),
                values,
            )
        conn.commit()
    finally:
        conn.close()


def find_digital_id_by_ms_user_id(ms_user_id):
    if not ms_user_id:
        return None
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT {} FROM digital_ids WHERE ms_user_id = %s LIMIT 1".format(", ".join(DIGITAL_ID_COLUMNS_SQL)),
                (ms_user_id,),
            )
            return _row_to_dict(cur.fetchone(), DIGITAL_ID_DISPLAY)
    finally:
        conn.close()


def get_sso_settings():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id, client_id, client_secret_encrypted, redirect_uri, enabled "
                "FROM sso_settings WHERE id = 1"
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "tenant_id": row[0], "client_id": row[1],
                "client_secret_encrypted": row[2], "redirect_uri": row[3],
                "enabled": row[4],
            }
    finally:
        conn.close()


def save_sso_settings(tenant_id, client_id, client_secret_encrypted, redirect_uri, enabled):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO sso_settings (id, tenant_id, client_id, client_secret_encrypted, redirect_uri, enabled)
                VALUES (1, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    client_id = EXCLUDED.client_id,
                    client_secret_encrypted = EXCLUDED.client_secret_encrypted,
                    redirect_uri = EXCLUDED.redirect_uri,
                    enabled = EXCLUDED.enabled
            """, (tenant_id, client_id, client_secret_encrypted, redirect_uri, enabled))
        conn.commit()
    finally:
        conn.close()


def log_event(event_type, actor, detail, created_at):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO activity_log (event_type, actor, detail, created_at) VALUES (%s, %s, %s, %s)",
                (event_type, actor, detail, created_at),
            )
        conn.commit()
    finally:
        conn.close()


def list_activity_log(limit=200):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT event_type, actor, detail, created_at FROM activity_log ORDER BY id DESC LIMIT %s",
                (limit,),
            )
            return [
                {"Event": row[0], "Actor": row[1], "Detail": row[2], "Created At": row[3]}
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def upload_photo(data, token):
    result = blob_put(f"photos/{token}.jpg", data, access="private", content_type="image/jpeg")
    return result.url


def upload_qr(data, token):
    result = blob_put(f"qrcodes/qr_{token}.png", data, access="private", content_type="image/png")
    return result.url


def download_blob(url):
    """Fetches a private blob's bytes -- token is read from
    BLOB_READ_WRITE_TOKEN automatically, same as the upload side."""
    result = blob_get(url, access="private")
    return result.content
