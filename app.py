import os
import logging
import time
from flask import Flask, request, g, send_from_directory, render_template

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-5s %(message)s',
    datefmt='%m-%d %H:%M:%S',
)
logger = logging.getLogger('lrs')

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'lrs-secret-key-2024')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
app.config['DATABASE'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'lrs.db')
app.config['PER_PAGE'] = 12
app.config['PUBLIC_BASE_URL'] = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
app.config['PERMANENT_SESSION_LIFETIME'] = 2592000  # 30 days (used with "remember me")


@app.before_request
def start_timer():
    g.start_time = time.time()


@app.after_request
def log_request(response):
    elapsed = time.time() - g.start_time
    logger.info(
        '%s %s%s \033[33m%s\033[0m \033[90m[%.0fms]\033[0m',
        request.method,
        request.path,
        ('?' + request.query_string.decode()) if request.query_string else '',
        response.status_code,
        elapsed * 1000,
    )
    return response


from db import close_db, init_db
app.teardown_appcontext(close_db)


@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

from helpers import format_file_size, prefix_keys, utc_to_local, csrf_token, highlight, can_edit
from db import get_db
app.jinja_env.filters['filesize'] = format_file_size
app.jinja_env.filters['prefix_keys'] = prefix_keys
app.jinja_env.filters['utc_to_local'] = utc_to_local
app.jinja_env.filters['highlight'] = highlight

@app.context_processor
def inject_globals():
    pending_count = 0
    try:
        pending_count = get_db().execute("SELECT COUNT(*) as cnt FROM resources WHERE status = 'pending'").fetchone()['cnt']
    except Exception:
        pass
    return dict(csrf_token=csrf_token, pending_count=pending_count, can_edit=can_edit)

from routes.auth import register_auth_routes
from routes.home import register_home_routes
from routes.resources import register_resources_routes
from routes.categories import register_categories_routes
from routes.api import register_api_routes
register_auth_routes(app)
register_home_routes(app)
register_resources_routes(app)
register_categories_routes(app)
register_api_routes(app)


@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404, title='页面未找到', message='你访问的页面不存在，可能已被删除或地址输入有误。'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', code=500, title='服务器内部错误', message='服务器遇到了意外错误，请稍后重试。'), 500


@app.errorhandler(413)
def too_large(e):
    return render_template('error.html', code=413, title='文件过大', message='上传的文件大小超过限制（最大 100MB）。'), 413

if __name__ == '__main__':
    init_db(app.config['DATABASE'])
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    logger.info('\033[32m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m')
    logger.info('\033[32m  LRS 服务启动\033[0m')
    logger.info('\033[32m  PID: %s\033[0m', os.getpid())
    logger.info('\033[32m  地址: http://0.0.0.0:5000\033[0m')
    logger.info('\033[32m  数据库: %s\033[0m', app.config['DATABASE'])
    logger.info('\033[32m  上传目录: %s\033[0m', app.config['UPLOAD_FOLDER'])
    logger.info('\033[32m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m')
    app.run(debug=True, host='0.0.0.0', port=5000)
