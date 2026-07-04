from flask import jsonify

from db import get_db
from helpers import login_required


def register_api_routes(app):

    @app.route('/api/stats', endpoint='api_stats')
    @login_required
    def api_stats():
        db = get_db()
        stats = {
            'total_resources': db.execute('SELECT COUNT(*) as count FROM resources').fetchone()['count'],
            'total_categories': db.execute('SELECT COUNT(*) as count FROM categories').fetchone()['count'],
            'total_downloads': db.execute('SELECT COALESCE(SUM(downloads), 0) as total FROM resources').fetchone()['total'],
        }
        return jsonify(stats)
