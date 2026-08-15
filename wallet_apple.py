"""Apple Wallet (PassKit) Generic Pass integration.

Builds a signed .pkpass bundle: pass.json + card art, a SHA-1 manifest of
every file in the bundle, and a PKCS#7 detached signature over that
manifest produced with the university's Pass Type ID certificate (issued
by Apple, chained to Apple's WWDR intermediate certificate).

Like wallet.py (Google), every function here degrades gracefully: if the
certificate/key/team/pass-type env vars aren't set, is_configured()
returns False and callers render a "not configured" state instead of
raising.
"""

import hashlib
import io
import json
import os
import zipfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7

PASS_TYPE_SUFFIX = "staff-digital-id"


def _env(name, default=None):
    value = os.environ.get(name, default)
    return value.strip() if isinstance(value, str) else value


def is_configured():
    return all([
        _env("APPLE_TEAM_IDENTIFIER"),
        _env("APPLE_PASS_TYPE_IDENTIFIER"),
        _env("APPLE_PASS_CERTIFICATE_FILE") and os.path.exists(_env("APPLE_PASS_CERTIFICATE_FILE")),
        _env("APPLE_PASS_KEY_FILE") and os.path.exists(_env("APPLE_PASS_KEY_FILE")),
        _env("APPLE_WWDR_CERTIFICATE_FILE") and os.path.exists(_env("APPLE_WWDR_CERTIFICATE_FILE")),
    ])


def _load_signing_materials():
    with open(_env("APPLE_PASS_CERTIFICATE_FILE"), "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read())
    with open(_env("APPLE_PASS_KEY_FILE"), "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=_env("APPLE_PASS_KEY_PASSWORD", "").encode() or None)
    with open(_env("APPLE_WWDR_CERTIFICATE_FILE"), "rb") as f:
        wwdr = x509.load_pem_x509_certificate(f.read())
    return cert, key, wwdr


def test_connection():
    """There's no Apple 'connectivity' API to ping -- the equivalent check
    here is: do the configured certificate/key files actually parse, and
    is the signing certificate still within its validity window."""
    if not is_configured():
        return False, "Team Identifier, Pass Type Identifier, and all three certificate/key files must be set first."
    try:
        cert, _key, _wwdr = _load_signing_materials()
    except Exception as exc:
        return False, f"Could not load Apple Pass certificates/key: {exc}"

    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    if now > cert.not_valid_after_utc:
        return False, f"Pass Type certificate expired on {cert.not_valid_after_utc.date()}."
    return True, f"Pass Type certificate valid until {cert.not_valid_after_utc.date()}."


def _pass_json(*, staff_id, full_name, job_title, department, employment_status, verify_url, status):
    cfg_pass_type = _env("APPLE_PASS_TYPE_IDENTIFIER")
    cfg_team = _env("APPLE_TEAM_IDENTIFIER")
    return {
        "formatVersion": 1,
        "passTypeIdentifier": cfg_pass_type,
        "teamIdentifier": cfg_team,
        "serialNumber": staff_id,
        "organizationName": "Middlesex University Dubai",
        "description": "Middlesex University Dubai Staff Digital ID",
        "logoText": "Staff Digital ID",
        "backgroundColor": "rgb(13,35,64)",
        "foregroundColor": "rgb(255,255,255)",
        "labelColor": "rgb(227,6,19)",
        "generic": {
            "primaryFields": [
                {"key": "name", "label": "STAFF NAME", "value": full_name},
            ],
            "secondaryFields": [
                {"key": "staffId", "label": "STAFF ID", "value": staff_id},
                {"key": "department", "label": "DEPARTMENT", "value": department or ""},
            ],
            "auxiliaryFields": [
                {"key": "jobTitle", "label": "JOB TITLE", "value": job_title or ""},
                {"key": "status", "label": "STATUS", "value": status or employment_status or ""},
            ],
        },
        "barcodes": [
            {"message": verify_url, "format": "PKBarcodeFormatQR", "messageEncoding": "iso-8859-1"},
        ],
    }


def build_pkpass_bytes(*, staff_id, full_name, job_title, department, employment_status, verify_url, status="Active"):
    """Returns the raw bytes of a signed .pkpass file, or None if Apple
    Wallet isn't configured."""
    if not is_configured():
        return None

    pass_json = _pass_json(
        staff_id=staff_id, full_name=full_name, job_title=job_title,
        department=department, employment_status=employment_status,
        verify_url=verify_url, status=status,
    )

    bundle_files = {"pass.json": json.dumps(pass_json).encode("utf-8")}

    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "images", "mdx-shield.png")
    if os.path.exists(icon_path):
        with open(icon_path, "rb") as f:
            icon_bytes = f.read()
        bundle_files["icon.png"] = icon_bytes
        bundle_files["logo.png"] = icon_bytes

    manifest = {name: hashlib.sha1(data).hexdigest() for name, data in bundle_files.items()}
    manifest_bytes = json.dumps(manifest).encode("utf-8")

    cert, key, wwdr = _load_signing_materials()
    signature = pkcs7.PKCS7SignatureBuilder().set_data(manifest_bytes).add_signer(
        cert, key, hashes.SHA256()
    ).add_certificate(wwdr).sign(
        serialization.Encoding.DER,
        [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary],
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in bundle_files.items():
            zf.writestr(name, data)
        zf.writestr("manifest.json", manifest_bytes)
        zf.writestr("signature", signature)
    return buf.getvalue()
