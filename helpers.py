import secrets
from functools import wraps
from datetime import datetime, timedelta
from html import escape
from flask import session, redirect, url_for, request


ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'zip', 'rar', 'mp4', 'mp3', 'py', 'java', 'cpp', 'c', 'html', 'css', 'js'}


def csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(16)
    return session['csrf_token']


def verify_csrf():
    token = request.form.get('csrf_token', '') or request.headers.get('X-CSRF-Token', '')
    if not token or token != session.get('csrf_token', ''):
        return False
    return True


def can_edit(resource):
    return session.get('role') == 'admin' or session.get('user_id') == resource['user_id']


def is_admin():
    return session.get('role') == 'admin'


def is_editor():
    return session.get('role') in ('admin', 'editor')


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_type(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    type_map = {
        'pdf': 'pdf', 'doc': 'doc', 'docx': 'doc', 'txt': 'text',
        'png': 'image', 'jpg': 'image', 'jpeg': 'image', 'gif': 'image',
        'mp4': 'video', 'avi': 'video', 'mov': 'video',
        'mp3': 'audio', 'wav': 'audio',
        'zip': 'archive', 'rar': 'archive', '7z': 'archive',
        'py': 'code', 'java': 'code', 'cpp': 'code', 'c': 'code', 'js': 'code', 'html': 'code', 'css': 'code',
        'xls': 'spreadsheet', 'xlsx': 'spreadsheet',
        'ppt': 'presentation', 'pptx': 'presentation'
    }
    return type_map.get(ext, 'other')


def format_file_size(size_bytes):
    if size_bytes is None:
        return '0 B'
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def prefix_keys(d, prefix):
    return {prefix + k: v for k, v in d.items()}


def utc_to_local(utc_str, tz_offset='+08:00'):
    if not utc_str:
        return ''
    try:
        if 'T' in utc_str:
            utc_str = utc_str.replace('T', ' ')
        if '.' in utc_str:
            utc_str = utc_str.split('.')[0]
        dt = datetime.strptime(utc_str, '%Y-%m-%d %H:%M:%S')
        sign = 1 if tz_offset[0] == '+' else -1
        h, m = int(tz_offset[1:3]), int(tz_offset[4:6]) if len(tz_offset) > 5 else 0
        dt += timedelta(hours=sign * h, minutes=sign * m)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return utc_str


def highlight(text, query):
    if not text or not query:
        return text or ''
    escaped = escape(text)
    terms = [t.strip() for t in query.split() if t.strip()]
    if not terms:
        return escaped
    result = escaped
    for term in terms:
        pattern = escape(term)
        # Use case-insensitive replacement via regex-style; simplest: do lower match
        import re
        result = re.sub(f'(?i)({re.escape(pattern)})', r'<mark>\1</mark>', result)
    return result
