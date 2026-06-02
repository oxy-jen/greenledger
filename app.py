import os
import uuid
import json
from datetime import datetime
import hmac
import secrets
from urllib.parse import urlparse
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session, flash, abort
from flask_socketio import SocketIO, emit
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from PIL import Image
import sqlite3
import hashlib
from functools import wraps
import shutil
import zipfile
from io import BytesIO, StringIO

app = Flask(__name__)
APP_NAME = 'RootLedger'
RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL', '')
DEFAULT_PRIMARY_HOST = urlparse(RENDER_EXTERNAL_URL).netloc or 'rootledger-osaw.onrender.com'
PRIMARY_HOST = os.environ.get('PRIMARY_HOST', DEFAULT_PRIMARY_HOST)
IS_PRODUCTION = os.environ.get('RENDER') == 'true' or os.environ.get('FLASK_ENV') == 'production'
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or ('dev-secret' if not IS_PRODUCTION else secrets.token_urlsafe(64))
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max limit
app.config['DATABASE'] = os.environ.get('DATABASE_PATH', os.path.join('instance', 'database.db'))
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = IS_PRODUCTION
app.config['FORCE_HTTPS'] = os.environ.get('FORCE_HTTPS', '1' if IS_PRODUCTION else '0') == '1'
app.config['APP_NAME'] = APP_NAME

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('instance', exist_ok=True)
os.makedirs('backups', exist_ok=True)

def allowed_origins():
    configured = os.environ.get('ALLOWED_ORIGINS')
    if configured:
        return [origin.strip() for origin in configured.split(',') if origin.strip()]
    return [
        f'https://{PRIMARY_HOST}',
        'http://localhost:5000',
        'http://127.0.0.1:5000'
    ]


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
        "img-src 'self' data: blob: https://*.tile.openstreetmap.org https://server.arcgisonline.com; "
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
        'rejection_note': 'TEXT'
    }
    for column, definition in participant_migrations.items():
        if column not in existing_columns:
            c.execute(f"ALTER TABLE participants ADD COLUMN {column} {definition}")
    
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

def extract_exif_gps(file):
    """Extract GPS coordinates from image EXIF data when the camera supplied it."""
    try:
        file.seek(0)
        img = Image.open(file)
        gps = img.getexif().get(34853)
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

def resolve_location(browser_lat, browser_lng, browser_accuracy, exif_location):
    """Prefer EXIF GPS when browser accuracy is poor; otherwise use browser GPS."""
    lat = parse_float(browser_lat)
    lng = parse_float(browser_lng)
    accuracy = parse_float(browser_accuracy)

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
    """Participant Portal - Mobile"""
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit_planting():
    """Handle participant registration"""
    try:
        # Get form data
        full_name = (request.form.get('full_name') or '').strip()
        role = (request.form.get('role') or '').strip()
        tree_species = (request.form.get('tree_species') or '').strip()
        quantity = int(request.form.get('quantity', 1))
        planting_zone = (request.form.get('planting_zone') or '').strip()
        latitude = request.form.get('lat')
        longitude = request.form.get('lng')
        location_accuracy = request.form.get('accuracy')
        browser_data = request.form.get('browser_data')
        photo_source = request.form.get('photo_source', 'camera')
        photo = request.files.get('photo')
        
        # Validation
        if not all([full_name, role, tree_species, planting_zone, photo]) or not photo.filename:
            return render_template('index.html', error="All fields are required")
        photo_extension = photo.filename.rsplit('.', 1)[-1].lower() if '.' in photo.filename else ''
        if photo_extension not in ALLOWED_IMAGE_EXTENSIONS:
            return render_template('index.html', error="Please upload a JPG, PNG, or WebP image.")
        if quantity <= 0:
            return render_template('index.html', error="Quantity must be greater than zero")
        if quantity > 1000:
            return render_template('index.html', error="Quantity must be 1000 or less")

        exif_location = extract_exif_gps(photo)
        final_lat, final_lng, final_accuracy, location_source = resolve_location(
            latitude, longitude, location_accuracy, exif_location
        )
        if final_lat is None or final_lng is None:
            return render_template(
                'index.html',
                error="Location was not captured. Please allow location access and submit again."
            )
        
        # Process photo
        photo_filename = process_image(photo)
        photo_path = f"uploads/{photo_filename}"
        
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
            location_source, browser_data, photo_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            photo_source
        ))
        conn.commit()
        
        # Get the inserted record
        c.execute("SELECT * FROM participants WHERE record_number = ?", (record_number,))
        participant = dict(c.fetchone())
        conn.close()
        
        # Emit real-time update
        socketio.emit('new_planting', {
            'id': participant['id'],
            'full_name': full_name,
            'role': role,
            'tree_species': tree_species,
            'quantity': quantity,
            'planting_zone': planting_zone,
            'photo_path': photo_path,
            'lat': participant['latitude'],
            'lng': participant['longitude'],
            'timestamp': participant['timestamp'],
            'is_vip': is_vip,
            'co2_saved': co2_saved,
            'record_number': record_number
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
    conn.close()
    
    if not participant:
        return "Record not found", 404
    
    return render_template('record.html', participant=dict(participant))

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
    
    conn.close()
    
    return render_template('hub.html', 
                         total_participants=total_participants,
                         total_trees=total_trees,
                         total_co2=total_co2,
                         recent=recent,
                         dept_stats=dept_stats,
                         pending=pending)

@app.route('/api/stats')
def get_stats():
    """API endpoint for real-time stats"""
    conn = get_db_connection()
    c = conn.cursor()
    
    visible_filter = "status != 'Rejected'"

    c.execute(f"SELECT SUM(quantity) FROM participants WHERE {visible_filter}")
    total_trees = c.fetchone()[0] or 0
    
    c.execute(f"SELECT COUNT(*) FROM participants WHERE {visible_filter}")
    total_participants = c.fetchone()[0]
    
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
        SELECT full_name, role, tree_species, quantity, photo_path, is_vip,
               planting_zone, latitude, longitude, timestamp, record_number
        FROM participants
        WHERE {visible_filter}
        ORDER BY timestamp DESC LIMIT 10
    """)
    recent = [{'name': row[0], 'role': row[1], 'species': row[2], 
               'quantity': row[3], 'photo': row[4], 'vip': bool(row[5]),
               'zone': row[6], 'lat': row[7], 'lng': row[8],
               'timestamp': row[9], 'record_number': row[10]} 
              for row in c.fetchall()]
    
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
        SELECT record_number, full_name, role, tree_species, quantity,
               planting_zone, photo_path, latitude, longitude, timestamp,
               status, co2_saved_kg
        FROM participants
        WHERE status != 'Rejected'
          AND latitude IS NOT NULL
          AND longitude IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 5000
    """)
    records = []
    for row in c.fetchall():
        quantity = max(int(row['quantity'] or 1), 1)
        records.append({
            'id': row['record_number'],
            'name': row['full_name'],
            'role': row['role'],
            'species': row['tree_species'],
            'quantity': quantity,
            'zone': row['planting_zone'],
            'photo': row['photo_path'],
            'lat': row['latitude'],
            'lng': row['longitude'],
            'timestamp': row['timestamp'],
            'status': row['status'],
            'co2': row['co2_saved_kg']
        })
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
    participants = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(participants)

@app.route('/api/tree-of-the-moment')
def tree_of_the_moment():
    """Return a real record for the display spotlight, preferring VIPs."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM participants
        WHERE status != 'Rejected'
        ORDER BY is_vip DESC, timestamp DESC
        LIMIT 1
    """)
    row = c.fetchone()
    conn.close()
    return jsonify(dict(row) if row else {})

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
    """Pin a participant to spotlight"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE participants SET is_vip = 1 WHERE id = ?", (participant_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

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
    conn.close()
    
    if format == 'csv':
        import csv
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(row)
        
        return send_file(
            BytesIO(output.getvalue().encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'rootledger_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    
    elif format == 'json':
        data = [dict(row) for row in rows]
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
            writer.writerow(columns)
            for row in rows:
                writer.writerow(row)
            zip_file.writestr('data.csv', csv_output.getvalue())
            
            # Add JSON export
            data = [dict(row) for row in rows]
            zip_file.writestr('data.json', json.dumps(data, indent=2))
            
            # Add photos
            for row in rows:
                photo_path = row[7]  # Assuming photo_path is at index 7
                if photo_path:
                    full_path = os.path.join('static', photo_path)
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
    
    c.execute("SELECT SUM(quantity), COUNT(*) FROM participants")
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
    socketio.run(app, debug=True, host='127.0.0.1', port=5000)
