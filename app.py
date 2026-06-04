import os
import uuid
import json
import csv
import re
from datetime import datetime
import hmac
import secrets
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from html import unescape
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session, flash, abort
from flask_socketio import SocketIO, emit
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from PIL import Image, ExifTags
import sqlite3
import hashlib
import math
from functools import wraps
import shutil
import zipfile
from io import BytesIO, StringIO

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
APP_NAME = 'RootLedger'
ASSET_VERSION = datetime.utcnow().strftime('%Y%m%d%H%M%S')
RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL', '')
DEFAULT_PRIMARY_HOST = urlparse(RENDER_EXTERNAL_URL).netloc or 'rootledger-osaw.onrender.com'
PRIMARY_HOST = os.environ.get('PRIMARY_HOST', DEFAULT_PRIMARY_HOST)
IS_PRODUCTION = os.environ.get('RENDER') == 'true' or os.environ.get('FLASK_ENV') == 'production'
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or ('dev-secret' if not IS_PRODUCTION else secrets.token_urlsafe(64))
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max limit
app.config['DATABASE'] = os.environ.get('DATABASE_PATH', os.path.join('instance', 'database.db'))
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = IS_PRODUCTION
app.config['FORCE_HTTPS'] = os.environ.get('FORCE_HTTPS', '1' if IS_PRODUCTION else '0') == '1'
app.config['APP_NAME'] = APP_NAME

@app.context_processor
def inject_asset_version():
    return {'asset_version': ASSET_VERSION}

KENYA_SEARCH_VIEWBOX = '33.5,-4.9,41.9,5.3'
LOCAL_PLACE_INDEX = [
    {
        'name': 'Mathenge Technical Training Institute, Othaya, Nyeri County, Kenya',
        'lat': -0.5084917,
        'lng': 36.8919167,
        'aliases': ['mathenge tti', 'mathenge technical', 'mathenge technical training institute', 'mtti']
    },
    {
        'name': 'Nyeri National Polytechnic, Nyeri, Kenya',
        'lat': -0.4209,
        'lng': 36.9513,
        'aliases': ['nyeri polytechnic', 'nyeri politechnic', 'nyeri national polytechnic', 'nyeri poly']
    },
    {
        'name': 'Othaya, Nyeri County, Kenya',
        'lat': -0.5466,
        'lng': 36.9434,
        'aliases': ['othaya']
    },
    {
        'name': 'Ndunyu, Othaya, Nyeri County, Kenya',
        'lat': -0.5488,
        'lng': 36.9348,
        'aliases': ['ndunyu', 'ndunyu othaya', 'ndunyu nyeri']
    },
    {
        'name': 'Kwa Michael, Othaya, Nyeri County, Kenya',
        'lat': -0.5358,
        'lng': 36.9286,
        'aliases': ['kwa michael', 'kwa maichal', 'kwa maichael', 'kwa michaels']
    },
    {
        'name': 'Dedan Kimathi University of Technology, Nyeri, Kenya',
        'lat': -0.3976,
        'lng': 36.9602,
        'aliases': ['dekut', 'dedan kimathi university', 'kimathi university']
    },
    {
        'name': 'Karatina University, Karatina, Nyeri County, Kenya',
        'lat': -0.4848,
        'lng': 37.1251,
        'aliases': ['karatina university', 'karu']
    },
    {
        'name': 'Karatina, Nyeri County, Kenya',
        'lat': -0.4815,
        'lng': 37.1274,
        'aliases': ['karatina']
    },
    {
        'name': 'Mukurwe-ini, Nyeri County, Kenya',
        'lat': -0.5605,
        'lng': 37.0476,
        'aliases': ['mukurweini', 'mukurwe ini', 'mukurwe-ini']
    },
    {
        'name': 'Tetu, Nyeri County, Kenya',
        'lat': -0.4242,
        'lng': 36.7856,
        'aliases': ['tetu']
    },
    {
        'name': 'Kamakwa, Nyeri, Kenya',
        'lat': -0.4161,
        'lng': 36.9325,
        'aliases': ['kamakwa']
    },
    {
        'name': 'Kingongo, Nyeri, Kenya',
        'lat': -0.4218,
        'lng': 36.9249,
        'aliases': ['kingongo']
    },
    {
        'name': 'Chaka, Nyeri County, Kenya',
        'lat': -0.3844,
        'lng': 37.0242,
        'aliases': ['chaka']
    },
    {
        'name': 'Giakanja, Nyeri County, Kenya',
        'lat': -0.4443,
        'lng': 36.9897,
        'aliases': ['giakanja']
    },
    {
        'name': 'Ihururu, Nyeri County, Kenya',
        'lat': -0.4939,
        'lng': 36.8373,
        'aliases': ['ihururu']
    },
    {
        'name': 'Mahiga, Othaya, Nyeri County, Kenya',
        'lat': -0.5669,
        'lng': 36.9021,
        'aliases': ['mahiga']
    },
    {
        'name': 'Kiamwathi, Othaya, Nyeri County, Kenya',
        'lat': -0.5274,
        'lng': 36.9188,
        'aliases': ['kiamwathi']
    },
    {
        'name': 'Kagonye, Othaya, Nyeri County, Kenya',
        'lat': -0.5221,
        'lng': 36.9568,
        'aliases': ['kagonye']
    },
    {
        'name': 'Chinga, Othaya, Nyeri County, Kenya',
        'lat': -0.5899,
        'lng': 36.9359,
        'aliases': ['chinga']
    },
    {
        'name': 'Witima, Othaya, Nyeri County, Kenya',
        'lat': -0.5591,
        'lng': 36.9618,
        'aliases': ['witima']
    },
    {
        'name': 'Kihome, Othaya, Nyeri County, Kenya',
        'lat': -0.5813,
        'lng': 36.8798,
        'aliases': ['kihome']
    },
    {
        'name': 'Iriaini, Othaya, Nyeri County, Kenya',
        'lat': -0.5419,
        'lng': 36.8844,
        'aliases': ['iriaini']
    }
]

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('instance', exist_ok=True)
os.makedirs('backups', exist_ok=True)

def allowed_origins():
    origins = {
        f'https://{PRIMARY_HOST}',
        'http://localhost:5000',
        'http://127.0.0.1:5000'
    }
    if RENDER_EXTERNAL_URL:
        origins.add(RENDER_EXTERNAL_URL.rstrip('/'))

    configured = os.environ.get('ALLOWED_ORIGINS')
    if configured:
        origins.update(origin.strip().rstrip('/') for origin in configured.split(',') if origin.strip())
    return sorted(origins)


# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins=allowed_origins(), async_mode="threading")


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 260000)
    return f'pbkdf2_sha256${salt}${digest.hex()}'


def verify_password(password, stored_hash):
    if not stored_hash:
        return False
    if stored_hash.startswith('pbkdf2_sha256$'):
        _, salt, digest = stored_hash.split('$', 2)
        return hmac.compare_digest(hash_password(password, salt), stored_hash)
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored_hash)


def csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return token


@app.context_processor
def inject_globals():
    return {
        'app_name': APP_NAME,
        'csrf_token': csrf_token
    }


@app.before_request
def enforce_https_and_csrf():
    if app.config['FORCE_HTTPS'] and not request.is_secure:
        return redirect(request.url.replace('http://', 'https://', 1), code=301)

    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        sent_token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
        if not sent_token or not hmac.compare_digest(sent_token, session.get('_csrf_token', '')):
            abort(400)


@app.after_request
def set_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(self), geolocation=(self), microphone=()')
    response.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.socket.io https://unpkg.com https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com https://unpkg.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com data:; "
        "img-src 'self' data: blob: https://*.tile.openstreetmap.org https://server.arcgisonline.com https://unpkg.com https://images.unsplash.com; "
        "connect-src 'self' https://api.open-meteo.com wss:;"
    )
    if request.is_secure:
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return response
# --- Database Setup ---
def init_db():
    """Initialize SQLite database with all tables"""
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    
    # Participants table
    c.execute('''CREATE TABLE IF NOT EXISTS participants (
        id TEXT PRIMARY KEY,
        record_number TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL,
        tree_species TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        planting_zone TEXT NOT NULL,
        photo_path TEXT,
        latitude REAL,
        longitude REAL,
        timestamp TEXT NOT NULL,
        status TEXT DEFAULT 'Pending',
        is_vip INTEGER DEFAULT 0,
        co2_saved_kg REAL DEFAULT 0,
        event_id TEXT
    )''')

    existing_columns = {row[1] for row in c.execute("PRAGMA table_info(participants)").fetchall()}
    participant_migrations = {
        'location_accuracy': 'REAL',
        'location_source': 'TEXT',
        'browser_data': 'TEXT',
        'photo_source': 'TEXT DEFAULT "camera"',
        'rejection_scope': 'TEXT',
        'rejection_note': 'TEXT',
        'student_count': 'INTEGER DEFAULT 1',
        'manual_location_name': 'TEXT',
        'manual_location_provider': 'TEXT',
        'planter_names': 'TEXT',
        'group_label': 'TEXT'
    }
    for column, definition in participant_migrations.items():
        if column not in existing_columns:
            c.execute(f"ALTER TABLE participants ADD COLUMN {column} {definition}")

    c.execute('''CREATE TABLE IF NOT EXISTS participant_photos (
        id TEXT PRIMARY KEY,
        participant_id TEXT NOT NULL,
        photo_path TEXT NOT NULL,
        sort_order INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(participant_id) REFERENCES participants(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS tree_volunteers (
        id TEXT PRIMARY KEY,
        participant_id TEXT NOT NULL,
        volunteer_name TEXT NOT NULL,
        contact TEXT,
        message TEXT,
        status TEXT DEFAULT 'Pending',
        acknowledged_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(participant_id) REFERENCES participants(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        participant_id TEXT NOT NULL,
        volunteer_id TEXT,
        type TEXT NOT NULL,
        message TEXT NOT NULL,
        read_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(participant_id) REFERENCES participants(id),
        FOREIGN KEY(volunteer_id) REFERENCES tree_volunteers(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS tree_messages (
        id TEXT PRIMARY KEY,
        participant_id TEXT NOT NULL,
        volunteer_id TEXT,
        sender_type TEXT NOT NULL,
        sender_name TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(participant_id) REFERENCES participants(id),
        FOREIGN KEY(volunteer_id) REFERENCES tree_volunteers(id)
    )''')
    
    # Events table
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        date TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        total_trees INTEGER DEFAULT 0,
        total_participants INTEGER DEFAULT 0
    )''')
    
    # Admins table
    c.execute('''CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )''')
    
    # Create/update admin from environment. The old admin123 fallback is local-only.
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
    admin_password = os.environ.get('ADMIN_PASSWORD')
    if admin_password:
        admin_hash = hash_password(admin_password)
        c.execute("INSERT OR REPLACE INTO admins (id, username, password_hash) VALUES ((SELECT id FROM admins WHERE username = ?), ?, ?)",
                  (admin_username, admin_username, admin_hash))
    elif not IS_PRODUCTION:
        admin_hash = hash_password('admin123')
        c.execute("INSERT OR IGNORE INTO admins (username, password_hash) VALUES (?, ?)",
                  ('admin', admin_hash))
    
    # Create default event
    c.execute("INSERT OR IGNORE INTO events (id, name, date, status) VALUES (?, ?, ?, ?)",
              ('EVENT-2026-001', 'Mazingira Day 2026', datetime.now().strftime('%Y-%m-%d'), 'active'))
    
    conn.commit()
    conn.close()

# Initialize database
init_db()

# --- Helper Functions ---
def generate_record_number():
    """Generate RL-2026-000247 style ID"""
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM participants")
    count = c.fetchone()[0]
    conn.close()
    year = datetime.now().year
    return f"RL-{year}-{str(count + 1).zfill(6)}"

def generate_event_id():
    """Generate EVENT-2026-001 style ID"""
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM events")
    count = c.fetchone()[0]
    conn.close()
    year = datetime.now().year
    return f"EVENT-{year}-{str(count + 1).zfill(3)}"

def process_image(file):
    """Save and compress image"""
    extension = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError('Unsupported image type')

    filename = secure_filename(f"{uuid.uuid4()}.jpg")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    # Open and compress image
    img = Image.open(file)
    img.verify()
    file.seek(0)
    img = Image.open(file)
    img.thumbnail((1024, 1024))
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    img.save(filepath, format='JPEG', optimize=True, quality=85)
    
    return filename

def process_images(files):
    """Save all supplied planting photos and return static-relative paths."""
    photo_paths = []
    for file in files:
        if not file or not file.filename:
            continue
        extension = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValueError('Unsupported image type')
        photo_paths.append(f"uploads/{process_image(file)}")
    return photo_paths

def extract_exif_gps(file):
    """Extract GPS coordinates from image EXIF data when the camera supplied it."""
    try:
        file.seek(0)
        img = Image.open(file)
        exif = img.getexif()
        gps_ifd = getattr(ExifTags.IFD, 'GPSInfo', 34853)
        gps = exif.get_ifd(gps_ifd) if hasattr(exif, 'get_ifd') else exif.get(34853)
        file.seek(0)
        if not gps:
            return None

        def decimal(values, ref):
            degrees, minutes, seconds = values
            result = float(degrees) + (float(minutes) / 60) + (float(seconds) / 3600)
            return -result if ref in ('S', 'W') else result

        lat_values = gps.get(2)
        lat_ref = gps.get(1)
        lng_values = gps.get(4)
        lng_ref = gps.get(3)
        if not all([lat_values, lat_ref, lng_values, lng_ref]):
            return None
        return decimal(lat_values, lat_ref), decimal(lng_values, lng_ref)
    except Exception:
        try:
            file.seek(0)
        except Exception:
            pass
        return None

def parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def static_photo_url(photo_path):
    """Return a browser-safe static URL for stored participant photos."""
    if not photo_path:
        return ''
    normalized = str(photo_path).replace('\\', '/').lstrip('/')
    if normalized.startswith('static/'):
        normalized = normalized[len('static/'):]
    return url_for('static', filename=normalized)

def static_photo_urls(photo_paths):
    return [static_photo_url(path) for path in photo_paths if path]

def is_photo_rejected(record):
    return record and record.get('status') == 'Rejected' and record.get('rejection_scope') in {'photo', 'all'}

def visible_data_filter():
    return "(status != 'Rejected' OR rejection_scope = 'photo')"

def public_photo_path(record):
    return '' if is_photo_rejected(record) else (record.get('photo_path') or '')

def public_photo_paths(record):
    if is_photo_rejected(record):
        return []
    return record.get('photos') or []

def normalize_search_text(value):
    return ' '.join(str(value or '').lower().replace('-', ' ').replace('_', ' ').split())

def split_planter_names(value):
    names = []
    for part in str(value or '').replace('\r', '\n').replace(';', '\n').replace(',', '\n').split('\n'):
        name = part.strip()
        if name:
            names.append(name[:120])
    return names[:500]

def split_multi_value(value):
    values = []
    raw_values = value if isinstance(value, list) else [value]
    for raw in raw_values:
        for part in str(raw or '').replace('\r', '\n').replace(';', '\n').replace(',', '\n').split('\n'):
            item = part.strip()
            if item and item.lower() != 'other':
                values.append(item[:80])
    deduped = []
    seen = set()
    for item in values:
        key = normalize_search_text(item)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:50]

def planter_names_text(names):
    return '\n'.join(split_planter_names(names)) if isinstance(names, str) else '\n'.join(names[:500])

def attach_planter_data(participant):
    names = split_planter_names(participant.get('planter_names'))
    participant['planter_names_list'] = names
    participant['planter_display'] = ', '.join(names) if names else (participant.get('group_label') or participant.get('full_name') or '')
    return participant

def planter_activity_names(participant):
    count = max(int(participant.get('student_count') or 1), 1)
    names = split_planter_names(participant.get('planter_names'))
    if names:
        return names[:count]
    label = (participant.get('group_label') or '').strip()
    if label:
        return [label]
    return [(participant.get('full_name') or 'Volunteer').strip()]

def expanded_planter_activities(participant):
    names = planter_activity_names(participant)
    species = split_multi_value(participant.get('tree_species')) or ['Tree']
    quantity = max(int(participant.get('quantity') or 1), 1)
    count = max(int(participant.get('student_count') or len(names) or 1), 1)
    activity_count = max(count if len(names) > 1 else len(names), 1)
    photo_urls = participant.get('photo_urls') or []
    photos = participant.get('photos') or []
    activities = []
    for index in range(activity_count):
        name = names[index] if index < len(names) else f"Planter {index + 1}"
        activities.append({
            'name': name,
            'species': species[index % len(species)],
            'photo_url': photo_urls[index % len(photo_urls)] if photo_urls else participant.get('photo_url', ''),
            'photo': photos[index % len(photos)] if photos else participant.get('photo_path', ''),
            'tree_number': index + 1,
            'tree_share': 1,
            'group_label': participant.get('group_label') or ''
        })
    return activities

def current_visible_totals(cursor):
    visible_filter = visible_data_filter()
    cursor.execute(f"SELECT SUM(quantity) FROM participants WHERE {visible_filter}")
    total_trees = cursor.fetchone()[0] or 0
    cursor.execute(f"SELECT SUM(COALESCE(student_count, 1)) FROM participants WHERE {visible_filter}")
    total_participants = cursor.fetchone()[0] or 0
    cursor.execute(f"SELECT SUM(co2_saved_kg) FROM participants WHERE {visible_filter}")
    total_co2 = cursor.fetchone()[0] or 0
    return {
        'trees': total_trees,
        'participants': total_participants,
        'co2': round(total_co2, 2)
    }

def participant_payload(participant):
    """Build the realtime payload used by display clients."""
    participant = attach_planter_data(participant)
    return {
        'id': participant['id'],
        'full_name': participant['full_name'],
        'role': participant['role'],
        'tree_species': participant['tree_species'],
        'quantity': participant['quantity'],
        'student_count': participant.get('student_count') or 1,
        'planting_zone': participant['planting_zone'],
        'photo_path': participant.get('photo_path') or '',
        'photo_url': static_photo_url(participant.get('photo_path')),
        'photos': participant.get('photos') or [],
        'photo_urls': participant.get('photo_urls') or [],
        'lat': participant.get('latitude'),
        'lng': participant.get('longitude'),
        'manual_location_name': participant.get('manual_location_name'),
        'planter_names': participant.get('planter_names') or '',
        'planter_names_list': participant.get('planter_names_list') or [],
        'planter_display': participant.get('planter_display') or '',
        'group_label': participant.get('group_label') or '',
        'planter_activities': expanded_planter_activities(participant),
        'timestamp': participant['timestamp'],
        'is_vip': participant.get('is_vip') or 0,
        'co2_saved': participant.get('co2_saved_kg') or 0,
        'record_number': participant['record_number']
    }

def create_participant_record(data, photo_files=None, *, status='Pending', require_photo=True):
    photo_files = [file for file in (photo_files or []) if file and file.filename]
    full_name = (data.get('full_name') or '').strip()[:160]
    role = (data.get('role') or 'Participant').strip()[:120]
    tree_species = ', '.join(split_multi_value(data.get('tree_species'))).strip() or 'Tree'
    quantity = int(data.get('quantity') or 1)
    student_count = int(data.get('student_count') or 1)
    planting_zone = (data.get('planting_zone') or 'Unspecified area').strip()[:100]
    manual_location_name = (data.get('manual_location_name') or '').strip()[:200]
    manual_location_provider = (data.get('manual_location_provider') or '').strip()[:80]
    planter_names = planter_names_text(data.get('planter_names') or '')
    group_label = (data.get('group_label') or '').strip()[:160]
    latitude = parse_float(data.get('latitude') or data.get('lat'))
    longitude = parse_float(data.get('longitude') or data.get('lng'))
    location_accuracy = parse_float(data.get('location_accuracy') or data.get('accuracy'))
    photo_source = (data.get('photo_source') or 'admin').strip()[:40]
    browser_data = data.get('browser_data')

    if not full_name:
        raise ValueError('Participant name is required')
    if require_photo and not photo_files:
        raise ValueError('At least one photo is required')
    if quantity <= 0 or quantity > 1000:
        raise ValueError('Quantity must be between 1 and 1000')
    if student_count <= 0 or student_count > 500:
        raise ValueError('Planter count must be between 1 and 500')
    provided_planter_names = split_planter_names(planter_names)
    if len(provided_planter_names) > student_count:
        student_count = len(provided_planter_names)
    if len(photo_files) > 12:
        raise ValueError('Please upload 12 photos or fewer at once')

    photo_paths = process_images(photo_files)
    photo_path = photo_paths[0] if photo_paths else ''
    vip_roles = {
        'Principal', 'Deputy Principal', 'Dean', 'Head of Department',
        'Government Official', 'Environmental Officer', 'Trainer'
    }
    is_vip = 1 if role in vip_roles else 0
    record_number = generate_record_number()
    participant_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO participants (id, record_number, full_name, role, tree_species,
        quantity, planting_zone, photo_path, latitude, longitude, timestamp,
        status, is_vip, co2_saved_kg, event_id, location_accuracy,
        location_source, browser_data, photo_source, student_count,
        manual_location_name, manual_location_provider, planter_names, group_label)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        participant_id, record_number, full_name, role, tree_species, quantity,
        planting_zone, photo_path, latitude, longitude, now, status, is_vip,
        quantity * 21.0, 'EVENT-2026-001', location_accuracy,
        'admin' if latitude is not None and longitude is not None else 'admin-missing',
        browser_data, photo_source, student_count, manual_location_name,
        manual_location_provider, planter_names, group_label
    ))
    for index, extra_photo_path in enumerate(photo_paths):
        c.execute("""
            INSERT INTO participant_photos (id, participant_id, photo_path, sort_order, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (str(uuid.uuid4()), participant_id, extra_photo_path, index, now))
    conn.commit()
    c.execute("SELECT * FROM participants WHERE id = ?", (participant_id,))
    participant = attach_photo_gallery(c, dict(c.fetchone()))
    participant['photo_url'] = static_photo_url(participant.get('photo_path'))
    totals = current_visible_totals(c)
    conn.close()

    update_event_stats()
    payload = participant_payload(participant)
    payload['stats'] = totals
    socketio.emit('new_planting', payload)
    return participant

def imported_participant_draft(row):
    lookup = {normalize_search_text(key): value for key, value in row.items()}

    def first(*names, default=''):
        for name in names:
            value = lookup.get(normalize_search_text(name))
            if value not in (None, ''):
                return str(value).strip()
        return default

    planter_names = first('planter_names', 'names', 'members', 'participants')
    group_label = first('group_label', 'group', 'team', 'club')
    student_count = first('student_count', 'count', 'number of participants', 'planters', default='1')
    try:
        student_count = max(int(float(student_count)), len(split_planter_names(planter_names)), 1)
    except ValueError:
        student_count = max(len(split_planter_names(planter_names)), 1)

    return {
        'full_name': first('full_name', 'name', 'participant', 'participant name', default=group_label or 'Imported participant'),
        'role': first('role', 'department', 'class', 'category', default='Participant'),
        'tree_species': first('tree_species', 'species', 'tree', 'trees', default='Tree'),
        'quantity': first('quantity', 'trees planted', 'number of trees', default='1'),
        'student_count': student_count,
        'planting_zone': first('planting_zone', 'zone', 'location', 'area', default='Unspecified area'),
        'manual_location_name': first('manual_location_name', 'place', 'location name'),
        'latitude': first('latitude', 'lat'),
        'longitude': first('longitude', 'lng', 'lon'),
        'planter_names': planter_names,
        'group_label': group_label,
        'source_fields': row
    }

def parse_import_file(file):
    filename = (file.filename or '').lower()
    content = file.read().decode('utf-8-sig', errors='replace')
    if filename.endswith('.json'):
        payload = json.loads(content)
        rows = payload if isinstance(payload, list) else payload.get('participants', [])
        return [imported_participant_draft(row) for row in rows if isinstance(row, dict)]
    reader = csv.DictReader(StringIO(content))
    return [imported_participant_draft(row) for row in reader]

def inspect_public_form(form_url):
    parsed = urlparse(form_url)
    if parsed.scheme not in {'http', 'https'}:
        raise ValueError('Use a valid http or https form link')
    req = Request(form_url, headers={'User-Agent': f'{APP_NAME}/1.0 form-import'})
    with urlopen(req, timeout=12) as response:
        html = response.read(1_500_000).decode('utf-8', errors='replace')

    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
    title = unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', title_match.group(1))).strip()) if title_match else parsed.netloc
    labels = []
    for raw in re.findall(r'\[\s*"([^"]{2,160})"\s*,\s*null\s*,\s*\[\[', html):
        label = unescape(raw.replace('\\"', '"')).strip()
        if label and label not in labels:
            labels.append(label)
    if not labels:
        for raw in re.findall(r'<div[^>]+role="heading"[^>]*>(.*?)</div>', html, re.I | re.S):
            label = unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', raw)).strip())
            if label and label not in labels:
                labels.append(label)
    return {
        'title': title[:180],
        'fields': labels[:80],
        'drafts': [imported_participant_draft({field: '' for field in labels})] if labels else [],
        'note': 'A public form link exposes the questions, not private submitted responses. Upload a CSV/JSON response export to import actual participant rows.'
    }

def resolve_location(browser_lat, browser_lng, browser_accuracy, exif_location, manual_lat=None, manual_lng=None):
    """Prefer EXIF GPS when browser accuracy is poor; otherwise use browser GPS."""
    lat = parse_float(browser_lat)
    lng = parse_float(browser_lng)
    accuracy = parse_float(browser_accuracy)
    selected_lat = parse_float(manual_lat)
    selected_lng = parse_float(manual_lng)

    if selected_lat is not None and selected_lng is not None:
        return selected_lat, selected_lng, accuracy, 'manual'

    if exif_location and (lat is None or lng is None or accuracy is None or accuracy > 80):
        return exif_location[0], exif_location[1], accuracy, 'exif'
    if lat is not None and lng is not None:
        return lat, lng, accuracy, 'browser'
    if exif_location:
        return exif_location[0], exif_location[1], accuracy, 'exif'
    return None, None, accuracy, 'missing'

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def haversine_km(lat1, lng1, lat2, lng2):
    lat1 = parse_float(lat1)
    lng1 = parse_float(lng1)
    lat2 = parse_float(lat2)
    lng2 = parse_float(lng2)
    if None in {lat1, lng1, lat2, lng2}:
        return None
    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def care_status_label(volunteer_count):
    return 'Has caretaker' if int(volunteer_count or 0) else 'Needs care'

def participant_tree_summary(cursor, row, reference_lat=None, reference_lng=None):
    participant = dict(row)
    participant['photo_url'] = static_photo_url(participant.get('photo_path'))
    attach_photo_gallery(cursor, participant)
    cursor.execute("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status = 'Acknowledged' THEN 1 ELSE 0 END) AS acknowledged
        FROM tree_volunteers
        WHERE participant_id = ?
    """, (participant['id'],))
    counts = cursor.fetchone()
    participant['volunteer_count'] = counts['total'] or 0
    participant['acknowledged_count'] = counts['acknowledged'] or 0
    participant['care_status'] = care_status_label(participant['volunteer_count'])
    participant['distance_km'] = haversine_km(reference_lat, reference_lng, participant['latitude'], participant['longitude'])
    participant['location_label'] = participant.get('manual_location_name') or participant.get('planting_zone') or 'Planting area'
    return participant

def create_notification(cursor, participant_id, volunteer_id, notification_type, message):
    notification_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO notifications (id, participant_id, volunteer_id, type, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        notification_id,
        participant_id,
        volunteer_id,
        notification_type,
        message,
        datetime.now().isoformat()
    ))
    return notification_id

def get_tree_care_bundle(record_number):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM participants WHERE record_number = ?", (record_number,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    participant = participant_tree_summary(c, row)
    c.execute("""
        SELECT * FROM tree_volunteers
        WHERE participant_id = ?
        ORDER BY created_at DESC
    """, (participant['id'],))
    volunteers = [dict(item) for item in c.fetchall()]
    c.execute("""
        SELECT * FROM notifications
        WHERE participant_id = ?
        ORDER BY created_at DESC
    """, (participant['id'],))
    notifications = [dict(item) for item in c.fetchall()]
    c.execute("""
        SELECT * FROM tree_messages
        WHERE participant_id = ?
        ORDER BY created_at ASC
    """, (participant['id'],))
    messages = [dict(item) for item in c.fetchall()]
    conn.close()
    return {
        'participant': participant,
        'volunteers': volunteers,
        'notifications': notifications,
        'messages': messages
    }

def get_participant_photo_paths(cursor, participant_id):
    cursor.execute("""
        SELECT photo_path FROM participant_photos
        WHERE participant_id = ?
        ORDER BY sort_order ASC, created_at ASC
    """, (participant_id,))
    return [row['photo_path'] if isinstance(row, sqlite3.Row) else row[0] for row in cursor.fetchall()]

def attach_photo_gallery(cursor, participant):
    photo_paths = get_participant_photo_paths(cursor, participant['id'])
    if participant.get('photo_path') and participant['photo_path'] not in photo_paths:
        photo_paths.insert(0, participant['photo_path'])
    participant['photos'] = photo_paths
    participant['photo_urls'] = static_photo_urls(photo_paths)
    if is_photo_rejected(participant):
        participant['photo_url'] = ''
        participant['photo_urls'] = []
    return attach_planter_data(participant)

def add_geocode_result(results, seen, name, lat, lng, provider, importance=0):
    lat = parse_float(lat)
    lng = parse_float(lng)
    if not name or lat is None or lng is None:
        return
    key = (round(lat, 5), round(lng, 5), normalize_search_text(name)[:70])
    if key in seen:
        return
    seen.add(key)
    results.append({
        'name': name,
        'lat': lat,
        'lng': lng,
        'provider': provider,
        'importance': importance
    })

def local_place_matches(query):
    normalized_query = normalize_search_text(query)
    terms = [term for term in normalized_query.split() if term]
    matches = []
    for place in LOCAL_PLACE_INDEX:
        searchable = normalize_search_text(' '.join([place['name'], *place.get('aliases', [])]))
        if normalized_query in searchable or all(term in searchable for term in terms):
            matches.append(place)
    return matches

def fetch_json(url, provider):
    request_obj = Request(
        url,
        headers={
            'User-Agent': f'{APP_NAME}/1.0 ({PRIMARY_HOST})',
            'Accept': 'application/json'
        }
    )
    with urlopen(request_obj, timeout=7) as response:
        return json.loads(response.read().decode('utf-8')), provider

def nominatim_searches(query):
    query_variants = [
        query,
        f'{query}, Kenya',
        f'{query}, Nyeri, Kenya',
        f'{query}, Othaya, Nyeri, Kenya'
    ]
    seen_queries = set()
    urls = []
    for item in query_variants:
        normalized = normalize_search_text(item)
        if normalized in seen_queries:
            continue
        seen_queries.add(normalized)
        params = urlencode({
            'q': item,
            'format': 'jsonv2',
            'addressdetails': 1,
            'limit': 8,
            'countrycodes': 'ke',
            'bounded': 1,
            'viewbox': KENYA_SEARCH_VIEWBOX
        })
        urls.append(f'https://nominatim.openstreetmap.org/search?{params}')
    return urls

def photon_searches(query):
    query_variants = [query, f'{query} Kenya', f'{query} Nyeri Kenya', f'{query} Othaya Kenya']
    seen_queries = set()
    urls = []
    for item in query_variants:
        normalized = normalize_search_text(item)
        if normalized in seen_queries:
            continue
        seen_queries.add(normalized)
        params = urlencode({
            'q': item,
            'limit': 8,
            'lat': -0.42,
            'lon': 36.95
        })
        urls.append(f'https://photon.komoot.io/api/?{params}')
    return urls

def login_required(f):
    """Decorator for admin authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('Please login first', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---

@app.route('/')
def index():
    """Public landing page for planters, caretakers, and viewers."""
    return render_template('landing.html')

@app.route('/plant')
def plant_tree():
    """Participant Portal - Mobile"""
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit_planting():
    """Handle participant registration"""
    try:
        # Get form data
        full_name = (request.form.get('full_name') or '').strip()
        role = (request.form.get('role') or '').strip()
        selected_species = split_multi_value(request.form.getlist('tree_species'))
        custom_species = split_multi_value(request.form.get('custom_tree_species'))
        tree_species = ', '.join([*selected_species, *custom_species]).strip()
        quantity = int(request.form.get('quantity', 1))
        student_count = int(request.form.get('student_count', 1))
        selected_zone = (request.form.get('planting_zone') or '').strip()
        custom_zone = (request.form.get('custom_planting_zone') or '').strip()
        planting_zone = (custom_zone or ('' if selected_zone == 'Other' else selected_zone) or 'Unspecified area')[:100]
        planter_names = planter_names_text(request.form.get('planter_names') or '')
        group_label = (request.form.get('group_label') or '').strip()[:160]
        latitude = request.form.get('lat')
        longitude = request.form.get('lng')
        location_accuracy = request.form.get('accuracy')
        manual_latitude = request.form.get('manual_lat')
        manual_longitude = request.form.get('manual_lng')
        manual_location_name = (request.form.get('manual_location_name') or '').strip()
        manual_location_provider = (request.form.get('manual_location_provider') or '').strip()
        browser_data = request.form.get('browser_data')
        photo_source = request.form.get('photo_source', 'camera')
        photos = request.files.getlist('photos')
        if not photos:
            legacy_photo = request.files.get('photo')
            photos = [legacy_photo] if legacy_photo else []
        photos = [photo for photo in photos if photo and photo.filename]
        primary_photo = photos[0] if photos else None
        
        # Validation
        if not all([full_name, role, tree_species, primary_photo]):
            return render_template('index.html', error="Name, role, tree species, and planting photo are required")
        for photo in photos:
            photo_extension = photo.filename.rsplit('.', 1)[-1].lower() if '.' in photo.filename else ''
            if photo_extension not in ALLOWED_IMAGE_EXTENSIONS:
                return render_template('index.html', error="Please upload JPG, PNG, or WebP images only.")
        if quantity <= 0:
            return render_template('index.html', error="Quantity must be greater than zero")
        if quantity > 1000:
            return render_template('index.html', error="Quantity must be 1000 or less")
        if student_count <= 0:
            return render_template('index.html', error="Number of students must be greater than zero")
        if student_count > 500:
            return render_template('index.html', error="Number of students must be 500 or less")
        provided_planter_names = split_planter_names(planter_names)
        if len(provided_planter_names) > student_count:
            student_count = len(provided_planter_names)
        if student_count > 1 and not provided_planter_names and not group_label:
            return render_template('index.html', error="Add planter names or write the group name represented by this record.")
        if len(photos) > 12:
            return render_template('index.html', error="Please submit 12 photos or fewer at once.")

        exif_location = extract_exif_gps(primary_photo)
        final_lat, final_lng, final_accuracy, location_source = resolve_location(
            latitude, longitude, location_accuracy, exif_location, manual_latitude, manual_longitude
        )
        if final_lat is None or final_lng is None:
            return render_template(
                'index.html',
                error="Location was not captured. Please allow location access or choose the location manually."
            )
        
        # Process photos
        photo_paths = process_images(photos)
        photo_path = photo_paths[0]
        
        # Determine VIP status
        vip_roles = ['Principal', 'Deputy Principal', 'Dean', 'Head of Department', 
                     'Government Official', 'Environmental Officer', 'Trainer']
        is_vip = 1 if role in vip_roles else 0
        
        # Estimated annual absorption: 21kg CO2 per tree.
        co2_saved = quantity * 21.0
        
        # Generate record number
        record_number = generate_record_number()
        
        # Insert into database
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO participants (id, record_number, full_name, role, tree_species, 
            quantity, planting_zone, photo_path, latitude, longitude, timestamp, 
            status, is_vip, co2_saved_kg, event_id, location_accuracy,
            location_source, browser_data, photo_source, student_count,
            manual_location_name, manual_location_provider, planter_names, group_label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            record_number,
            full_name,
            role,
            tree_species,
            quantity,
            planting_zone,
            photo_path,
            final_lat,
            final_lng,
            datetime.now().isoformat(),
            'Pending',
            is_vip,
            co2_saved,
            'EVENT-2026-001',
            final_accuracy,
            location_source,
            browser_data,
            photo_source,
            student_count,
            manual_location_name,
            manual_location_provider,
            planter_names,
            group_label
        ))
        c.execute("SELECT id FROM participants WHERE record_number = ?", (record_number,))
        participant_id = c.fetchone()[0]
        for index, extra_photo_path in enumerate(photo_paths):
            c.execute("""
                INSERT INTO participant_photos (id, participant_id, photo_path, sort_order, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()),
                participant_id,
                extra_photo_path,
                index,
                datetime.now().isoformat()
            ))
        conn.commit()
        
        # Get the inserted record
        c.execute("SELECT * FROM participants WHERE record_number = ?", (record_number,))
        participant = attach_photo_gallery(c, dict(c.fetchone()))
        participant['photo_url'] = static_photo_url(participant.get('photo_path'))
        live_totals = current_visible_totals(c)
        conn.close()
        
        # Emit real-time update
        socketio.emit('new_planting', {
            'id': participant['id'],
            'full_name': full_name,
            'role': role,
            'tree_species': tree_species,
            'quantity': quantity,
            'student_count': student_count,
            'planting_zone': planting_zone,
            'photo_path': photo_path,
            'photo_url': static_photo_url(photo_path),
            'photos': participant['photos'],
            'photo_urls': participant['photo_urls'],
            'lat': participant['latitude'],
            'lng': participant['longitude'],
            'manual_location_name': participant.get('manual_location_name'),
            'planter_names': planter_names,
            'planter_names_list': participant['planter_names_list'],
            'planter_display': participant['planter_display'],
            'group_label': group_label,
            'planter_activities': expanded_planter_activities(participant),
            'timestamp': participant['timestamp'],
            'is_vip': is_vip,
            'co2_saved': co2_saved,
            'record_number': record_number,
            'stats': live_totals
        })
        
        # Update event stats
        update_event_stats()
        
        # Show success page
        return render_template('success.html', participant=participant)
        
    except Exception as e:
        print(f"Error: {e}")
        return render_template('index.html', error="Registration failed. Please try again.")

@app.route('/record/<record_number>')
def view_record(record_number):
    """Public record card page"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM participants WHERE record_number = ?", (record_number,))
    participant = c.fetchone()
    participant = attach_photo_gallery(c, dict(participant)) if participant else None
    conn.close()
    
    if not participant:
        return "Record not found", 404
    
    return render_template('record.html', participant=participant)

@app.route('/care')
def care_trees():
    """Public page for finding nearby trees that need a volunteer caretaker."""
    reference_lat = parse_float(request.args.get('lat'))
    reference_lng = parse_float(request.args.get('lng'))
    query = normalize_search_text(request.args.get('q'))

    conn = get_db_connection()
    c = conn.cursor()
    visible_filter = visible_data_filter()
    c.execute(f"""
        SELECT *
        FROM participants
        WHERE {visible_filter}
        ORDER BY timestamp DESC
        LIMIT 500
    """)
    trees = []
    for row in c.fetchall():
        tree = participant_tree_summary(c, row, reference_lat, reference_lng)
        haystack = normalize_search_text(
            f"{tree.get('full_name')} {tree.get('tree_species')} {tree.get('planting_zone')} "
            f"{tree.get('manual_location_name')} {tree.get('record_number')} {tree.get('role')}"
        )
        if query and query not in haystack:
            continue
        trees.append(tree)
    conn.close()

    if reference_lat is not None and reference_lng is not None:
        trees.sort(key=lambda item: item['distance_km'] if item['distance_km'] is not None else 999999)

    return render_template(
        'care.html',
        trees=trees,
        reference_lat=reference_lat,
        reference_lng=reference_lng,
        query=request.args.get('q', '')
    )

@app.route('/care/tree/<record_number>')
def care_tree_detail(record_number):
    """Tree care detail page with volunteer form, notifications, and chat."""
    bundle = get_tree_care_bundle(record_number)
    if not bundle:
        return "Tree record not found", 404
    return render_template('care_detail.html', **bundle)

@app.route('/care/tree/<record_number>/volunteer', methods=['POST'])
def volunteer_for_tree(record_number):
    """Register a public volunteer for a planted tree and notify the planter in-app."""
    name = (request.form.get('volunteer_name') or '').strip()[:120]
    contact = (request.form.get('contact') or '').strip()[:180]
    message = (request.form.get('message') or '').strip()[:700]
    if not name:
        flash('Add your name so the planter knows who volunteered.', 'error')
        return redirect(url_for('care_tree_detail', record_number=record_number))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(f"SELECT * FROM participants WHERE record_number = ? AND {visible_data_filter()}", (record_number,))
    participant = c.fetchone()
    if not participant:
        conn.close()
        return "Tree record not found", 404

    volunteer_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    c.execute("""
        INSERT INTO tree_volunteers (id, participant_id, volunteer_name, contact, message, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'Pending', ?)
    """, (volunteer_id, participant['id'], name, contact, message, now))
    create_notification(
        c,
        participant['id'],
        volunteer_id,
        'volunteer_created',
        f"{name} volunteered to take care of the {participant['tree_species']} tree record {record_number}."
    )
    if message:
        c.execute("""
            INSERT INTO tree_messages (id, participant_id, volunteer_id, sender_type, sender_name, message, created_at)
            VALUES (?, ?, ?, 'volunteer', ?, ?, ?)
        """, (str(uuid.uuid4()), participant['id'], volunteer_id, name, message, now))
    conn.commit()
    conn.close()

    socketio.emit('tree_volunteer_created', {
        'record_number': record_number,
        'volunteer_name': name,
        'tree_species': participant['tree_species']
    })
    flash('You are now listed as a volunteer caretaker. The planter has been notified.', 'success')
    return redirect(url_for('care_tree_detail', record_number=record_number))

@app.route('/care/tree/<record_number>/acknowledge/<volunteer_id>', methods=['POST'])
def acknowledge_volunteer(record_number, volunteer_id):
    """Let the planter thank or acknowledge a volunteer caretaker."""
    planter_name = (request.form.get('planter_name') or '').strip()[:120] or 'Planter'
    thank_message = (request.form.get('thank_message') or '').strip()[:700]
    action = (request.form.get('action') or 'acknowledge').strip().lower()
    status = 'Thanked' if action == 'thank' else 'Acknowledged'

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM participants WHERE record_number = ?", (record_number,))
    participant = c.fetchone()
    c.execute("SELECT * FROM tree_volunteers WHERE id = ?", (volunteer_id,))
    volunteer = c.fetchone()
    if not participant or not volunteer or volunteer['participant_id'] != participant['id']:
        conn.close()
        return "Volunteer record not found", 404

    now = datetime.now().isoformat()
    c.execute("""
        UPDATE tree_volunteers
        SET status = ?, acknowledged_at = ?
        WHERE id = ?
    """, (status, now, volunteer_id))
    create_notification(
        c,
        participant['id'],
        volunteer_id,
        'volunteer_acknowledged',
        f"{planter_name} {status.lower()} {volunteer['volunteer_name']} for caring for record {record_number}."
    )
    if thank_message:
        c.execute("""
            INSERT INTO tree_messages (id, participant_id, volunteer_id, sender_type, sender_name, message, created_at)
            VALUES (?, ?, ?, 'planter', ?, ?, ?)
        """, (str(uuid.uuid4()), participant['id'], volunteer_id, planter_name, thank_message, now))
    conn.commit()
    conn.close()
    flash('Volunteer updated and notified in the tree thread.', 'success')
    return redirect(url_for('care_tree_detail', record_number=record_number))

@app.route('/care/tree/<record_number>/message', methods=['POST'])
def add_tree_message(record_number):
    """Add a simple message to a tree care chat thread."""
    sender_name = (request.form.get('sender_name') or '').strip()[:120]
    sender_type = (request.form.get('sender_type') or 'volunteer').strip().lower()
    message = (request.form.get('message') or '').strip()[:1000]
    volunteer_id = (request.form.get('volunteer_id') or '').strip() or None
    if sender_type not in {'planter', 'volunteer', 'admin'}:
        sender_type = 'volunteer'
    if not sender_name or not message:
        flash('Add your name and message before sending.', 'error')
        return redirect(url_for('care_tree_detail', record_number=record_number))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(f"SELECT * FROM participants WHERE record_number = ? AND {visible_data_filter()}", (record_number,))
    participant = c.fetchone()
    if not participant:
        conn.close()
        return "Tree record not found", 404
    if volunteer_id:
        c.execute("SELECT id FROM tree_volunteers WHERE id = ? AND participant_id = ?", (volunteer_id, participant['id']))
        if not c.fetchone():
            volunteer_id = None
    c.execute("""
        INSERT INTO tree_messages (id, participant_id, volunteer_id, sender_type, sender_name, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (str(uuid.uuid4()), participant['id'], volunteer_id, sender_type, sender_name, message, datetime.now().isoformat()))
    create_notification(
        c,
        participant['id'],
        volunteer_id,
        'tree_message',
        f"{sender_name} added a message on tree record {record_number}."
    )
    conn.commit()
    conn.close()
    return redirect(url_for('care_tree_detail', record_number=record_number))

@app.route('/api/geocode')
def geocode_location():
    """Search Kenya locations with local aliases plus free OSM-backed providers."""
    query = (request.args.get('q') or '').strip()
    if len(query) < 2:
        return jsonify([])

    results = []
    seen = set()

    for place in local_place_matches(query):
        add_geocode_result(results, seen, place['name'], place['lat'], place['lng'], 'RootLedger local index', 2)

    for url in nominatim_searches(query):
        try:
            payload, provider = fetch_json(url, 'OpenStreetMap Nominatim')
            for item in payload:
                add_geocode_result(
                    results,
                    seen,
                    item.get('display_name', ''),
                    item.get('lat'),
                    item.get('lon'),
                    provider,
                    parse_float(item.get('importance')) or 0
                )
        except Exception:
            continue

    for url in photon_searches(query):
        try:
            payload, provider = fetch_json(url, 'Photon OpenStreetMap')
            for feature in payload.get('features', []):
                geometry = feature.get('geometry') or {}
                coordinates = geometry.get('coordinates') or []
                properties = feature.get('properties') or {}
                if len(coordinates) < 2 or properties.get('countrycode') != 'KE':
                    continue
                name_parts = [
                    properties.get('name'),
                    properties.get('street'),
                    properties.get('city') or properties.get('district') or properties.get('county'),
                    properties.get('state'),
                    'Kenya'
                ]
                name = ', '.join(part for part in name_parts if part)
                add_geocode_result(results, seen, name, coordinates[1], coordinates[0], provider, 0.5)
        except Exception:
            continue

    results.sort(key=lambda item: (-item.get('importance', 0), item['name'].lower()))
    return jsonify(results[:15])

@app.route('/display')
def live_display():
    """Live event display for TV/Projector"""
    return render_template('display.html')

@app.route('/hub')
@login_required
def operations_hub():
    """Admin operations hub"""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get stats
    c.execute("SELECT COUNT(*) FROM participants")
    total_participants = c.fetchone()[0]
    
    c.execute("SELECT SUM(quantity) FROM participants")
    total_trees = c.fetchone()[0] or 0
    
    c.execute("SELECT SUM(co2_saved_kg) FROM participants")
    total_co2 = c.fetchone()[0] or 0
    
    # Get recent participants
    c.execute("""
        SELECT * FROM participants 
        ORDER BY timestamp DESC LIMIT 10
    """)
    recent = [dict(row) for row in c.fetchall()]
    
    # Get department stats
    c.execute("""
        SELECT role, SUM(quantity) as total 
        FROM participants 
        GROUP BY role 
        ORDER BY total DESC
    """)
    dept_stats = [dict(row) for row in c.fetchall()]
    
    # Get pending verifications
    c.execute("SELECT COUNT(*) FROM participants WHERE status = 'Pending'")
    pending = c.fetchone()[0]

    c.execute("""
        SELECT tv.*, p.record_number, p.full_name, p.tree_species, p.planting_zone, p.manual_location_name
        FROM tree_volunteers tv
        JOIN participants p ON p.id = tv.participant_id
        ORDER BY tv.created_at DESC
        LIMIT 20
    """)
    care_volunteers = [dict(row) for row in c.fetchall()]

    c.execute("""
        SELECT n.*, p.record_number, p.full_name, p.tree_species
        FROM notifications n
        JOIN participants p ON p.id = n.participant_id
        ORDER BY n.created_at DESC
        LIMIT 20
    """)
    care_notifications = [dict(row) for row in c.fetchall()]

    c.execute("""
        SELECT tm.*, p.record_number, p.full_name, p.tree_species
        FROM tree_messages tm
        JOIN participants p ON p.id = tm.participant_id
        ORDER BY tm.created_at DESC
        LIMIT 20
    """)
    care_messages = [dict(row) for row in c.fetchall()]
    
    conn.close()
    
    return render_template('hub.html', 
                         total_participants=total_participants,
                         total_trees=total_trees,
                         total_co2=total_co2,
                         recent=recent,
                         dept_stats=dept_stats,
                         pending=pending,
                         care_volunteers=care_volunteers,
                         care_notifications=care_notifications,
                         care_messages=care_messages)

@app.route('/api/stats')
def get_stats():
    """API endpoint for real-time stats"""
    conn = get_db_connection()
    c = conn.cursor()
    
    visible_filter = visible_data_filter()

    c.execute(f"SELECT SUM(quantity) FROM participants WHERE {visible_filter}")
    total_trees = c.fetchone()[0] or 0
    
    c.execute(f"SELECT SUM(COALESCE(student_count, 1)) FROM participants WHERE {visible_filter}")
    total_participants = c.fetchone()[0] or 0
    
    c.execute(f"SELECT SUM(co2_saved_kg) FROM participants WHERE {visible_filter}")
    total_co2 = c.fetchone()[0] or 0
    
    c.execute(f"""
        SELECT role, SUM(quantity) as total 
        FROM participants
        WHERE {visible_filter}
        GROUP BY role 
        ORDER BY total DESC LIMIT 5
    """)
    leaderboard = [{'role': row[0], 'total': row[1]} for row in c.fetchall()]
    
    # Get recent activity
    c.execute(f"""
        SELECT id, full_name, role, tree_species, quantity, photo_path, is_vip,
               planting_zone, latitude, longitude, timestamp, record_number,
               student_count, manual_location_name, planter_names, group_label,
               status, rejection_scope
        FROM participants
        WHERE {visible_filter}
        ORDER BY timestamp DESC LIMIT 10
    """)
    recent = []
    for row in c.fetchall():
        photo_paths = get_participant_photo_paths(c, row[0])
        recent_item = {
            'name': row[1], 'role': row[2], 'species': row[3],
            'quantity': row[4], 'photo': row[5],
            'photo_url': static_photo_url(row[5]), 'vip': bool(row[6]),
            'zone': row[7], 'lat': row[8], 'lng': row[9],
            'timestamp': row[10], 'record_number': row[11],
            'student_count': row[12], 'manual_location_name': row[13],
            'planter_names': row[14], 'group_label': row[15],
            'status': row[16], 'rejection_scope': row[17],
            'photos': photo_paths,
            'photo_urls': static_photo_urls(photo_paths)
        }
        attach_planter_data(recent_item)
        if is_photo_rejected(recent_item):
            recent_item['photo'] = ''
            recent_item['photo_url'] = ''
            recent_item['photos'] = []
            recent_item['photo_urls'] = []
        recent_item['planter_activities'] = expanded_planter_activities(recent_item)
        recent.append(recent_item)
    
    conn.close()
    
    return jsonify({
        'trees': total_trees,
        'participants': total_participants,
        'co2': round(total_co2, 2),
        'leaderboard': leaderboard,
        'recent': recent
    })

@app.route('/api/map-records')
def get_map_records():
    """Return visible planting records for the GIS display map."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, record_number, full_name, role, tree_species, quantity,
               planting_zone, photo_path, latitude, longitude, timestamp,
               status, co2_saved_kg, student_count, manual_location_name,
               planter_names, group_label, rejection_scope
        FROM participants
        WHERE (status != 'Rejected' OR rejection_scope = 'photo')
          AND latitude IS NOT NULL
          AND longitude IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 5000
    """)
    records = []
    for row in c.fetchall():
        quantity = max(int(row['quantity'] or 1), 1)
        photo_paths = get_participant_photo_paths(c, row['id'])
        record = {
            'id': row['record_number'],
            'name': row['full_name'],
            'role': row['role'],
            'species': row['tree_species'],
            'quantity': quantity,
            'zone': row['planting_zone'],
            'photo': row['photo_path'],
            'photo_url': static_photo_url(row['photo_path']),
            'lat': row['latitude'],
            'lng': row['longitude'],
            'timestamp': row['timestamp'],
            'status': row['status'],
            'co2': row['co2_saved_kg'],
            'student_count': row['student_count'],
            'manual_location_name': row['manual_location_name'],
            'planter_names': row['planter_names'],
            'group_label': row['group_label'],
            'rejection_scope': row['rejection_scope'],
            'photos': photo_paths,
            'photo_urls': static_photo_urls(photo_paths)
        }
        attach_planter_data(record)
        if is_photo_rejected(record):
            record['photo'] = ''
            record['photo_url'] = ''
            record['photos'] = []
            record['photo_urls'] = []
        record['planter_activities'] = expanded_planter_activities(record)
        records.append(record)
    conn.close()
    return jsonify(records)

@app.route('/api/participants')
@login_required
def get_participants():
    """Return participant records for the operations hub."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM participants
        ORDER BY timestamp DESC
    """)
    participants = []
    for row in c.fetchall():
        participant = dict(row)
        participant['photo_url'] = static_photo_url(participant.get('photo_path'))
        attach_photo_gallery(c, participant)
        participants.append(participant)
    conn.close()
    return jsonify(participants)

@app.route('/api/participants', methods=['POST'])
@login_required
def admin_create_participant():
    """Create a participant directly from the admin hub."""
    try:
        participant = create_participant_record(
            request.form,
            request.files.getlist('photos'),
            status=request.form.get('status') or 'Verified',
            require_photo=False
        )
        return jsonify({'success': True, 'participant': participant})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

@app.route('/api/participants/bulk', methods=['POST'])
@login_required
def admin_create_participants_bulk():
    """Create participant records from reviewed import drafts."""
    payload = request.get_json(silent=True) or {}
    drafts = payload.get('participants') or []
    created = []
    errors = []
    for index, draft in enumerate(drafts):
        if not isinstance(draft, dict):
            errors.append({'row': index + 1, 'error': 'Invalid row'})
            continue
        try:
            participant = create_participant_record(draft, [], status='Verified', require_photo=False)
            created.append({
                'id': participant['id'],
                'record_number': participant['record_number'],
                'full_name': participant['full_name']
            })
        except Exception as exc:
            errors.append({'row': index + 1, 'error': str(exc)})
    return jsonify({'success': not errors, 'created': created, 'errors': errors})

@app.route('/api/import-participants', methods=['POST'])
@login_required
def import_participants():
    """Extract editable participant drafts from CSV/JSON exports or inspect public forms."""
    try:
        import_file = request.files.get('import_file')
        form_url = (request.form.get('form_url') or '').strip()
        if import_file and import_file.filename:
            return jsonify({
                'success': True,
                'source_type': 'file',
                'drafts': parse_import_file(import_file),
                'note': 'Review the extracted rows, correct missing details, then save them.'
            })
        if form_url:
            result = inspect_public_form(form_url)
            result.update({'success': True, 'source_type': 'form'})
            return jsonify(result)
        return jsonify({'success': False, 'error': 'Upload a CSV/JSON file or paste a form link'}), 400
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

@app.route('/api/participants', methods=['DELETE'])
@login_required
def delete_all_participants():
    """Delete every planting record and uploaded participant photo."""
    payload = request.get_json(silent=True) or {}
    if payload.get('confirm') != 'DELETE ALL RECORDS':
        return jsonify({
            'success': False,
            'error': 'Type DELETE ALL RECORDS to confirm'
        }), 400

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT photo_path FROM participants WHERE photo_path IS NOT NULL AND photo_path != ''")
    photo_paths = [row['photo_path'] for row in c.fetchall()]
    c.execute("SELECT photo_path FROM participant_photos WHERE photo_path IS NOT NULL AND photo_path != ''")
    photo_paths.extend(row['photo_path'] for row in c.fetchall())

    c.execute("DELETE FROM participant_photos")
    c.execute("DELETE FROM tree_messages")
    c.execute("DELETE FROM notifications")
    c.execute("DELETE FROM tree_volunteers")
    c.execute("DELETE FROM participants")
    c.execute("""
        UPDATE events
        SET total_trees = 0, total_participants = 0
        WHERE id = 'EVENT-2026-001'
    """)
    conn.commit()
    conn.close()

    upload_root = os.path.abspath(app.config['UPLOAD_FOLDER'])
    deleted_files = 0
    for photo_path in set(filter(None, photo_paths)):
        full_path = os.path.abspath(os.path.join(BASE_DIR, 'static', photo_path))
        try:
            if os.path.commonpath([upload_root, full_path]) == upload_root and os.path.exists(full_path):
                os.remove(full_path)
                deleted_files += 1
        except (OSError, ValueError):
            pass

    update_event_stats()
    socketio.emit('participants_cleared', {
        'deleted_files': deleted_files
    })
    return jsonify({'success': True, 'deleted_files': deleted_files})

@app.route('/api/tree-of-the-moment')
def tree_of_the_moment():
    """Return a real record for the display spotlight, preferring VIPs."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM participants
        WHERE (status != 'Rejected' OR rejection_scope = 'photo')
        ORDER BY is_vip DESC, timestamp DESC
        LIMIT 1
    """)
    row = c.fetchone()
    participant = dict(row) if row else {}
    if participant:
        attach_photo_gallery(c, participant)
        participant['photo_url'] = static_photo_url(participant.get('photo_path'))
    conn.close()
    return jsonify(participant)

@app.route('/api/verify/<participant_id>', methods=['POST'])
@login_required
def verify_participant(participant_id):
    """Verify a participant's planting record"""
    payload = request.get_json(silent=True) or {}
    status = payload.get('status', 'Verified')
    if status not in {'Pending', 'Verified', 'Rejected'}:
        return jsonify({'success': False, 'error': 'Invalid status'}), 400
    rejection_scope = payload.get('rejection_scope') if status == 'Rejected' else None
    if rejection_scope not in {None, 'photo', 'details', 'all'}:
        return jsonify({'success': False, 'error': 'Invalid rejection scope'}), 400
    rejection_note = payload.get('rejection_note') if status == 'Rejected' else None
    if rejection_note:
        rejection_note = str(rejection_note).strip()[:500]
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE participants
        SET status = ?, rejection_scope = ?, rejection_note = ?
        WHERE id = ?
    """, (status, rejection_scope, rejection_note, participant_id))
    c.execute("SELECT full_name, record_number FROM participants WHERE id = ?", (participant_id,))
    participant = c.fetchone()
    conn.commit()
    conn.close()
    
    update_event_stats()
    if participant:
        socketio.emit('participant_verified', {
            'id': participant_id,
            'full_name': participant[0],
            'record_number': participant[1],
            'status': status,
            'rejection_scope': rejection_scope
        })
    
    return jsonify({'success': True})

@app.route('/api/pin/<participant_id>', methods=['POST'])
@login_required
def pin_participant(participant_id):
    """Pin a participant to the official spotlight."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE participants SET is_vip = 1 WHERE id = ?", (participant_id,))
    c.execute("SELECT record_number, full_name FROM participants WHERE id = ?", (participant_id,))
    participant = c.fetchone()
    conn.commit()
    conn.close()
    if participant:
        socketio.emit('official_spotlight_updated', {
            'id': participant['record_number'],
            'full_name': participant['full_name'],
            'pinned': True
        })
    
    return jsonify({'success': True})

@app.route('/api/unpin/<participant_id>', methods=['POST'])
@login_required
def unpin_participant(participant_id):
    """Remove a participant from the official spotlight."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE participants SET is_vip = 0 WHERE id = ?", (participant_id,))
    c.execute("SELECT record_number, full_name FROM participants WHERE id = ?", (participant_id,))
    participant = c.fetchone()
    conn.commit()
    conn.close()
    if participant:
        socketio.emit('official_spotlight_updated', {
            'id': participant['record_number'],
            'full_name': participant['full_name'],
            'pinned': False
        })
    return jsonify({'success': True})

@app.route('/api/participants/<participant_id>', methods=['DELETE'])
@login_required
def delete_participant(participant_id):
    """Delete a participant and their photo records from the system."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT record_number, photo_path FROM participants WHERE id = ?", (participant_id,))
    participant = c.fetchone()
    if not participant:
        conn.close()
        return jsonify({'success': False, 'error': 'Participant not found'}), 404

    photo_paths = get_participant_photo_paths(c, participant_id)
    if participant['photo_path'] and participant['photo_path'] not in photo_paths:
        photo_paths.append(participant['photo_path'])

    c.execute("DELETE FROM participant_photos WHERE participant_id = ?", (participant_id,))
    c.execute("DELETE FROM tree_messages WHERE participant_id = ?", (participant_id,))
    c.execute("DELETE FROM notifications WHERE participant_id = ?", (participant_id,))
    c.execute("DELETE FROM tree_volunteers WHERE participant_id = ?", (participant_id,))
    c.execute("DELETE FROM participants WHERE id = ?", (participant_id,))
    conn.commit()
    conn.close()

    for photo_path in photo_paths:
        if not photo_path:
            continue
        full_path = os.path.abspath(os.path.join(BASE_DIR, 'static', photo_path))
        upload_root = os.path.abspath(app.config['UPLOAD_FOLDER'])
        if os.path.commonpath([upload_root, full_path]) == upload_root and os.path.exists(full_path):
            try:
                os.remove(full_path)
            except OSError:
                pass

    update_event_stats()
    socketio.emit('participant_deleted', {
        'id': participant_id,
        'record_number': participant['record_number']
    })
    return jsonify({'success': True})

@app.route('/api/participants/<participant_id>', methods=['PUT'])
@login_required
def update_participant(participant_id):
    """Edit participant details and optionally append more photos."""
    try:
        full_name = (request.form.get('full_name') or '').strip()[:160]
        role = (request.form.get('role') or '').strip()[:120]
        tree_species = ', '.join(split_multi_value(request.form.get('tree_species'))).strip()
        quantity = int(request.form.get('quantity') or 1)
        student_count = int(request.form.get('student_count') or 1)
        planting_zone = (request.form.get('planting_zone') or '').strip()[:100]
        manual_location_name = (request.form.get('manual_location_name') or '').strip()[:200]
        latitude = parse_float(request.form.get('latitude') or request.form.get('lat'))
        longitude = parse_float(request.form.get('longitude') or request.form.get('lng'))
        planter_names = planter_names_text(request.form.get('planter_names') or '')
        group_label = (request.form.get('group_label') or '').strip()[:160]
        status = request.form.get('status') or 'Verified'
        if status not in {'Pending', 'Verified', 'Rejected'}:
            status = 'Verified'
        if not all([full_name, role, tree_species, planting_zone]):
            return jsonify({'success': False, 'error': 'Name, role, tree species, and zone are required'}), 400
        if quantity <= 0 or quantity > 1000 or student_count <= 0 or student_count > 500:
            return jsonify({'success': False, 'error': 'Counts are outside allowed limits'}), 400
        names = split_planter_names(planter_names)
        if len(names) > student_count:
            student_count = len(names)

        new_photos = process_images(request.files.getlist('photos'))
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM participants WHERE id = ?", (participant_id,))
        existing = c.fetchone()
        if not existing:
            conn.close()
            return jsonify({'success': False, 'error': 'Participant not found'}), 404
        photo_path = existing['photo_path'] or (new_photos[0] if new_photos else '')
        c.execute("""
            UPDATE participants
            SET full_name = ?, role = ?, tree_species = ?, quantity = ?, student_count = ?,
                planting_zone = ?, manual_location_name = ?, latitude = ?, longitude = ?,
                planter_names = ?, group_label = ?, status = ?, rejection_scope = NULL,
                rejection_note = NULL, co2_saved_kg = ?
            WHERE id = ?
        """, (
            full_name, role, tree_species, quantity, student_count, planting_zone,
            manual_location_name, latitude, longitude, planter_names, group_label,
            status, quantity * 21.0, participant_id
        ))
        if photo_path != existing['photo_path']:
            c.execute("UPDATE participants SET photo_path = ? WHERE id = ?", (photo_path, participant_id))
        existing_photo_count = len(get_participant_photo_paths(c, participant_id))
        for offset, photo in enumerate(new_photos):
            c.execute("""
                INSERT INTO participant_photos (id, participant_id, photo_path, sort_order, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), participant_id, photo, existing_photo_count + offset, datetime.now().isoformat()))
        conn.commit()
        c.execute("SELECT * FROM participants WHERE id = ?", (participant_id,))
        participant = attach_photo_gallery(c, dict(c.fetchone()))
        participant['photo_url'] = static_photo_url(participant.get('photo_path'))
        totals = current_visible_totals(c)
        conn.close()
        update_event_stats()
        payload = participant_payload(participant)
        payload['stats'] = totals
        socketio.emit('participant_verified', payload)
        return jsonify({'success': True, 'participant': participant})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if request.method == 'POST':
        if session.get('login_attempts', 0) >= 8:
            flash('Too many failed attempts. Clear the session or try again later.', 'error')
            return render_template('admin_login.html'), 429

        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash('Invalid credentials', 'error')
            return render_template('admin_login.html')
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM admins WHERE username = ?", (username,))
        admin = c.fetchone()
        
        if admin and verify_password(password, admin['password_hash']):
            if not str(admin['password_hash']).startswith('pbkdf2_sha256$'):
                c.execute("UPDATE admins SET password_hash = ? WHERE id = ?", (hash_password(password), admin['id']))
                conn.commit()
            conn.close()
            session.clear()
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('operations_hub'))
        conn.close()
        session['login_attempts'] = session.get('login_attempts', 0) + 1
        flash('Invalid credentials', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.clear()
    return redirect(url_for('index'))

@app.route('/export')
@login_required
def export_data():
    """Export all data in various formats"""
    format = request.args.get('format', 'csv')
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM participants ORDER BY timestamp DESC")
    rows = c.fetchall()
    columns = [description[0] for description in c.description]
    gallery_by_participant = {}
    for row in rows:
        gallery_by_participant[row['id']] = get_participant_photo_paths(c, row['id'])
    conn.close()
    export_columns = columns + ['photo_gallery']
    
    if format == 'csv':
        import csv
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(export_columns)
        for row in rows:
            writer.writerow(list(row) + [';'.join(gallery_by_participant.get(row['id'], []))])
        
        return send_file(
            BytesIO(output.getvalue().encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'rootledger_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    
    elif format == 'json':
        data = []
        for row in rows:
            record = dict(row)
            record['photo_gallery'] = gallery_by_participant.get(row['id'], [])
            data.append(record)
        return send_file(
            BytesIO(json.dumps(data, indent=2).encode()),
            mimetype='application/json',
            as_attachment=True,
            download_name=f'rootledger_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )
    
    elif format == 'zip':
        # Create a ZIP archive with all data and photos
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add CSV export
            import csv
            csv_output = StringIO()
            writer = csv.writer(csv_output)
            writer.writerow(export_columns)
            for row in rows:
                writer.writerow(list(row) + [';'.join(gallery_by_participant.get(row['id'], []))])
            zip_file.writestr('data.csv', csv_output.getvalue())
            
            # Add JSON export
            data = []
            for row in rows:
                record = dict(row)
                record['photo_gallery'] = gallery_by_participant.get(row['id'], [])
                data.append(record)
            zip_file.writestr('data.json', json.dumps(data, indent=2))
            
            # Add photos
            for row in rows:
                photo_paths = gallery_by_participant.get(row['id'], []) or [row['photo_path']]
                for photo_path in photo_paths:
                    if not photo_path:
                        continue
                    full_path = os.path.join(BASE_DIR, 'static', photo_path)
                    if os.path.exists(full_path):
                        zip_file.write(full_path, f'photos/{os.path.basename(photo_path)}')
        
        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'rootledger_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        )

@app.route('/backup/create', methods=['POST'])
@login_required
def create_backup():
    """Create a complete system backup"""
    backup_dir = f'backups/backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    os.makedirs(backup_dir, exist_ok=True)
    
    # Copy database
    shutil.copy(app.config['DATABASE'], os.path.join(backup_dir, 'database.db'))
    
    # Copy photos
    shutil.copytree(app.config['UPLOAD_FOLDER'], os.path.join(backup_dir, 'photos'))
    
    # Create metadata
    metadata = {
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0',
        'event': 'Mazingira Day 2026'
    }
    with open(os.path.join(backup_dir, 'metadata.json'), 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Create ZIP
    zip_path = f'{backup_dir}.zip'
    shutil.make_archive(backup_dir, 'zip', backup_dir)
    
    return jsonify({
        'success': True,
        'path': url_for('download_backup', filename=os.path.basename(zip_path))
    })

@app.route('/backup/download/<filename>')
@login_required
def download_backup(filename):
    """Download a generated backup ZIP."""
    safe_name = secure_filename(filename)
    backup_path = os.path.join('backups', safe_name)
    if not os.path.exists(backup_path):
        return "Backup not found", 404
    return send_file(backup_path, as_attachment=True)

# --- Helper Functions ---

def update_event_stats():
    """Update event statistics"""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT SUM(quantity), SUM(COALESCE(student_count, 1)) FROM participants")
    total_trees, total_participants = c.fetchone()
    
    c.execute("""
        UPDATE events 
        SET total_trees = ?, total_participants = ? 
        WHERE id = 'EVENT-2026-001'
    """, (total_trees or 0, total_participants or 0))
    
    conn.commit()
    conn.close()

# --- SocketIO Events ---

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    emit('connected', {'message': f'Connected to {APP_NAME} server'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    pass

# --- Main Entry Point ---

if __name__ == '__main__':
    socketio.run(app, debug=True, host='127.0.0.1', port=5000, allow_unsafe_werkzeug=True, use_reloader=False)
