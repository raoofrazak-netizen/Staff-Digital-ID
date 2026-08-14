import io
import os
import secrets
from datetime import datetime

import openpyxl
import qrcode
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, abort, jsonify, send_file
from PIL import Image, UnidentifiedImageError

import wallet
from card_render import render_card_png

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

PORTAL_BASE_URL = os.environ.get("PORTAL_BASE_URL", "http://127.0.0.1:5000").rstrip("/")

# All generated data (Excel + QR codes + photos) lives outside the project
# folder so it survives redeploys and can be pointed at a shared location later.
DATA_ROOT = os.environ.get("DATA_ROOT", r"C:\MDX-Digital-ID\Test")
QR_DIR = os.path.join(DATA_ROOT, "/tmp/qrcodes")
PHOTO_DIR = os.path.join(DATA_ROOT, "/tmp/photos")
EXCEL_PATH = os.path.join(DATA_ROOT, "Staff_Digital_ID.xlsx")

os.makedirs(QR_DIR, exist_ok=True)
os.makedirs(PHOTO_DIR, exist_ok=True)

MAX_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_PHOTO_FORMATS = {"JPEG", "PNG", "WEBP"}
PHOTO_MAX_DIMENSION = 640

DEPARTMENTS = [
    "Information Technology, AI and Cybersecurity (ITAC)",
    "Administration",
    "Registry",
    "Library",
    "Human Resources",
    "Finance",
    "Marketing & Communications",
    "Academic - Business School",
    "Academic - Engineering",
    "Academic - Media",
]
EMPLOYMENT_STATUSES = ["Full-Time", "Part-Time", "Contract", "Visiting"]
GENDERS = ["Male", "Female"]

DIRECTORY_COLUMNS = [
    "Staff ID", "First Name", "Last Name", "Email",
    "Department", "Job Title", "Gender", "Employment Status",
]
DIGITAL_ID_COLUMNS = [
    "Token", "Track ID", "Staff ID", "First Name", "Last Name", "Email",
    "Department", "Job Title", "Gender", "Employment Status",
    "Photo Filename", "QR Filename", "Created At", "Status",
]

SAMPLE_DIRECTORY_ROWS = [
    ["MDX00001", "Sample", "Employee", "sample.employee@mdx.ac.ae",
     "Information Technology, AI and Cybersecurity (ITAC)", "IT Support Engineer", "Male", "Full-Time"],
    ["MDX00002", "Sample", "Faculty", "sample.faculty@mdx.ac.ae",
     "Academic - Business School", "Senior Lecturer", "Female", "Full-Time"],
]


def _sheet_has_data_rows(ws):
    return ws.max_row > 1


def init_excel():
    """Creates/migrates the workbook. Only resets a sheet's header if that
    sheet has no data rows yet, so real staff data is never wiped on restart."""
    if not os.path.exists(EXCEL_PATH):
        wb = openpyxl.Workbook()
        ws_dir = wb.active
        ws_dir.title = "Staff_Directory"
        ws_dir.append(DIRECTORY_COLUMNS)
        for row in SAMPLE_DIRECTORY_ROWS:
            ws_dir.append(row)
        ws_ids = wb.create_sheet("Digital_IDs")
        ws_ids.append(DIGITAL_ID_COLUMNS)
        wb.save(EXCEL_PATH)
        return

    wb = openpyxl.load_workbook(EXCEL_PATH)
    changed = False

    if "Staff_Directory" not in wb.sheetnames:
        ws = wb.create_sheet("Staff_Directory")
        ws.append(DIRECTORY_COLUMNS)
        for row in SAMPLE_DIRECTORY_ROWS:
            ws.append(row)
        changed = True
    else:
        ws = wb["Staff_Directory"]
        header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        if header != DIRECTORY_COLUMNS and not _sheet_has_data_rows(ws):
            wb.remove(ws)
            ws = wb.create_sheet("Staff_Directory")
            ws.append(DIRECTORY_COLUMNS)
            for row in SAMPLE_DIRECTORY_ROWS:
                ws.append(row)
            changed = True

    if "Digital_IDs" not in wb.sheetnames:
        ws = wb.create_sheet("Digital_IDs")
        ws.append(DIGITAL_ID_COLUMNS)
        changed = True
    else:
        ws = wb["Digital_IDs"]
        header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        if header != DIGITAL_ID_COLUMNS and not _sheet_has_data_rows(ws):
            wb.remove(ws)
            ws = wb.create_sheet("Digital_IDs")
            ws.append(DIGITAL_ID_COLUMNS)
            changed = True

    if "Sheet" in wb.sheetnames and not _sheet_has_data_rows(wb["Sheet"]) and wb["Sheet"]["A1"].value is None:
        wb.remove(wb["Sheet"])
        changed = True

    if changed:
        wb.save(EXCEL_PATH)


init_excel()


def _rows_as_dicts(ws, columns):
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            continue
        yield dict(zip(columns, row))


def find_directory_record_by_staff_id(staff_id):
    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb["Staff_Directory"]
    staff_id = (staff_id or "").strip().lower()
    for record in _rows_as_dicts(ws, DIRECTORY_COLUMNS):
        if str(record["Staff ID"]).strip().lower() == staff_id:
            return record
    return None


def find_active_digital_id_by_staff(staff_id):
    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb["Digital_IDs"]
    staff_id = (staff_id or "").strip().lower()
    for record in _rows_as_dicts(ws, DIGITAL_ID_COLUMNS):
        if str(record["Staff ID"]).strip().lower() == staff_id and record["Status"] == "Active":
            return record
    return None


def find_digital_id_by_token(token):
    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb["Digital_IDs"]
    for record in _rows_as_dicts(ws, DIGITAL_ID_COLUMNS):
        if record["Token"] == token:
            return record
    return None


def find_digital_id_by_track(track_id):
    track_id = (track_id or "").strip().lower()
    if not track_id:
        return None
    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb["Digital_IDs"]
    for record in _rows_as_dicts(ws, DIGITAL_ID_COLUMNS):
        if str(record.get("Track ID") or "").strip().lower() == track_id:
            return record
    return None


def generate_track_id():
    """Short, memorable reference code shown to the staff member — distinct
    from the long secure Token used inside the QR/verify URL."""
    while True:
        candidate = "MDX-" + secrets.token_hex(3).upper()
        if not find_digital_id_by_track(candidate):
            return candidate


def build_vcard(first_name, last_name, job_title, department, email):
    """vCard 3.0 payload for the staff-contact QR — a real, scannable
    business card, not a security/verification link."""
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN:{first_name} {last_name}".strip(),
        "ORG:Middlesex University Dubai",
    ]
    if job_title:
        lines.append(f"TITLE:{job_title}")
    if email:
        lines.append(f"EMAIL;TYPE=WORK:{email}")
    lines.append("URL:https://www.mdx.ac.ae")
    if department:
        lines.append(f"NOTE:Department - {department}")
    lines.append("END:VCARD")
    return "\r\n".join(lines)


def append_digital_id(record):
    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb["Digital_IDs"]
    ws.append([record[col] for col in DIGITAL_ID_COLUMNS])
    wb.save(EXCEL_PATH)


REQUIRED_FIELDS = [
    "first_name", "last_name", "staff_id", "email",
    "department", "job_title", "gender", "employment_status",
]


def _validate_and_save_photo(file_storage, token):
    """Validates format/size, downscales, and saves as a JPEG.
    Returns (filename, error_message) \u2014 exactly one will be set."""
    if not file_storage or not file_storage.filename:
        return None, "Staff photo is required."

    data = file_storage.read()
    if len(data) > MAX_PHOTO_BYTES:
        return None, "Photo is too large (max 5MB)."

    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
        image = Image.open(io.BytesIO(data))  # verify() consumes the parser; reopen to actually use it
    except UnidentifiedImageError:
        return None, "Unsupported file \u2014 please upload a JPEG, PNG, or WebP image."

    if image.format not in ALLOWED_PHOTO_FORMATS:
        return None, "Unsupported format \u2014 please upload a JPEG, PNG, or WebP image."

    image = image.convert("RGB")
    image.thumbnail((PHOTO_MAX_DIMENSION, PHOTO_MAX_DIMENSION))
    filename = f"{token}.jpg"
    image.save(os.path.join(PHOTO_DIR, filename), format="JPEG", quality=88)
    return filename, None


def _handle_submission():
    form = request.form
    values = {field: (form.get(field) or "").strip() for field in REQUIRED_FIELDS}

    missing = [f for f in REQUIRED_FIELDS if not values[f]]
    photo_file = request.files.get("photo")
    if not photo_file or not photo_file.filename:
        missing.append("photo")

    if missing:
        return render_template(
            "index.html",
            departments=DEPARTMENTS, employment_statuses=EMPLOYMENT_STATUSES, genders=GENDERS,
            error=f"Missing required field(s): {', '.join(missing)}",
            form=form,
        ), 400

    if find_active_digital_id_by_staff(values["staff_id"]):
        return render_template(
            "index.html",
            departments=DEPARTMENTS, employment_statuses=EMPLOYMENT_STATUSES, genders=GENDERS,
            error="A Digital ID already exists for this Staff ID. Use \u201cExisting Staff Activation\u201d instead.",
            form=form,
        ), 409

    token = secrets.token_urlsafe(24)
    track_id = generate_track_id()

    photo_filename, photo_error = _validate_and_save_photo(photo_file, token)
    if photo_error:
        return render_template(
            "index.html",
            departments=DEPARTMENTS, employment_statuses=EMPLOYMENT_STATUSES, genders=GENDERS,
            error=photo_error,
            form=form,
        ), 400

    vcard_payload = build_vcard(
        first_name=values["first_name"], last_name=values["last_name"],
        job_title=values["job_title"], department=values["department"],
        email=values["email"],
    )
    qr = qrcode.QRCode(version=1, box_size=10, border=3)
    qr.add_data(vcard_payload)
    qr.make(fit=True)
    # Black-on-white — every colour option gives lower contrast than this
    # for camera scanning, and reliability matters more than branding here.
    qr_img = qr.make_image(fill_color="#000000", back_color="#ffffff")
    qr_filename = f"qr_{token}.png"
    qr_img.save(os.path.join(QR_DIR, qr_filename))

    record = {
        "Token": token,
        "Track ID": track_id,
        "Staff ID": values["staff_id"],
        "First Name": values["first_name"],
        "Last Name": values["last_name"],
        "Email": values["email"],
        "Department": values["department"],
        "Job Title": values["job_title"],
        "Gender": values["gender"],
        "Employment Status": values["employment_status"],
        "Photo Filename": photo_filename,
        "QR Filename": qr_filename,
        "Created At": datetime.now().isoformat(timespec="seconds"),
        "Status": "Active",
    }
    append_digital_id(record)

    return redirect(url_for("success", token=token))


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    return render_template(
        "index.html",
        departments=DEPARTMENTS, employment_statuses=EMPLOYMENT_STATUSES, genders=GENDERS,
    )


@app.route("/register", methods=["POST"])
def register():
    return _handle_submission()


@app.route("/activate", methods=["POST"])
def activate():
    return _handle_submission()


@app.route("/api/track", methods=["POST"])
def api_track():
    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()

    if not query:
        return jsonify({"found": False, "error": "Enter a Track ID or Staff ID."}), 400

    digital = find_digital_id_by_track(query) or find_active_digital_id_by_staff(query)
    if digital:
        return jsonify({
            "found": True,
            "type": "digital_id",
            "record": digital,
            "photo_url": url_for("serve_photo", filename=digital["Photo Filename"]) if digital.get("Photo Filename") else None,
            "success_url": url_for("success", token=digital["Token"]),
        })

    directory = find_directory_record_by_staff_id(query)
    if directory:
        return jsonify({"found": True, "type": "directory", "record": directory})

    return jsonify({"found": False})


@app.route("/success/<token>")
def success(token):
    record = find_digital_id_by_token(token)
    if not record:
        abort(404)

    verify_url = f"{PORTAL_BASE_URL}/verify/{token}"
    wallet_url = wallet.build_save_url(
        staff_id=record["Staff ID"],
        full_name=f"{record['First Name']} {record['Last Name']}",
        job_title=record["Job Title"],
        department=record["Department"],
        employment_status=record["Employment Status"],
        verify_url=verify_url,
    )
    return render_template(
        "success.html",
        record=record, token=token,
        wallet_url=wallet_url, wallet_configured=wallet.is_configured(),
    )


@app.route("/verify/<token>")
def verify(token):
    record = find_digital_id_by_token(token)
    if not record:
        return render_template("verify.html", status="invalid")

    status = "valid" if record["Status"] == "Active" else "revoked"
    return render_template("verify.html", status=status, record=record)


@app.route("/qrcodes/<path:filename>")
def serve_qr(filename):
    return send_from_directory(QR_DIR, filename)


@app.route("/photos/<path:filename>")
def serve_photo(filename):
    return send_from_directory(PHOTO_DIR, filename)


@app.route("/download/<token>")
def download(token):
    record = find_digital_id_by_token(token)
    if not record:
        abort(404)

    photo_path = os.path.join(PHOTO_DIR, record["Photo Filename"]) if record.get("Photo Filename") else None
    qr_path = os.path.join(QR_DIR, record["QR Filename"]) if record.get("QR Filename") else None
    card = render_card_png(record, photo_path, qr_path)

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    buf.seek(0)
    filename = f"MDX-Digital-ID-{record['Staff ID']}.png"
    return send_file(buf, mimetype="image/png", as_attachment=True, download_name=filename)


def _lan_ip():
    """Best-effort LAN-facing IP for convenience — doesn't actually send
    any traffic, just asks the OS which local interface would be used to
    reach the internet."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


if __name__ == "__main__":
    lan_ip = _lan_ip()
    print(" * Local:   http://127.0.0.1:5000")
    if lan_ip:
        print(f" * Network: http://{lan_ip}:5000  (open this on a phone/device on the same Wi-Fi/LAN)")
    else:
        print(" * Network: could not detect a LAN IP — check `ipconfig` for your adapter's IPv4 address")
    print(" * If another device can't connect, allow inbound TCP port 5000 through Windows Firewall.")
    app.run(host="0.0.0.0", debug=True, port=5000)
