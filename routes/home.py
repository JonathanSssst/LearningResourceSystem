from datetime import datetime, timedelta
from flask import render_template, redirect, url_for, session

from db import get_db
from helpers import login_required


def register_home_routes(app):

    @app.route('/', endpoint='index')
    def index():
        if 'user_id' in session:
            return redirect(url_for('home'))
        return redirect(url_for('login'))

    @app.route('/home', endpoint='home')
    @login_required
    def home():
        db = get_db()

        total_resources = db.execute('SELECT COUNT(*) as count FROM resources').fetchone()['count']
        total_categories = db.execute('SELECT COUNT(*) as count FROM taxonomies').fetchone()['count']
        total_downloads = db.execute('SELECT COALESCE(SUM(downloads), 0) as total FROM resources').fetchone()['total']
        total_favorites = db.execute('SELECT COUNT(*) as count FROM favorites WHERE user_id = ?', (session['user_id'],)).fetchone()['count']

        recent_resources = db.execute('''
            SELECT r.*, c.name as category_name
            FROM resources r
            LEFT JOIN categories c ON r.category_id = c.id
            ORDER BY r.created_at DESC
            LIMIT 6
        ''').fetchall()

        subject_cats = db.execute('''
            SELECT c.*, COUNT(rc.id) as resource_count
            FROM categories c
            LEFT JOIN resource_categories rc ON c.id = rc.category_id
            WHERE c.taxonomy_id = (SELECT id FROM taxonomies WHERE slug = 'subject')
            GROUP BY c.id
            ORDER BY resource_count DESC
        ''').fetchall()

        return render_template('home.html',
                             total_resources=total_resources,
                             total_categories=total_categories,
                             total_downloads=total_downloads,
                             total_favorites=total_favorites,
                             recent_resources=recent_resources,
                             subject_cats=subject_cats)

    @app.route('/dashboard', endpoint='dashboard')
    @login_required
    def dashboard():
        db = get_db()

        stats = {
            'total_resources': db.execute('SELECT COUNT(*) as count FROM resources').fetchone()['count'],
            'total_categories': db.execute('SELECT COUNT(*) as count FROM categories').fetchone()['count'],
            'total_taxonomies': db.execute('SELECT COUNT(*) as count FROM taxonomies').fetchone()['count'],
            'total_downloads': db.execute('SELECT COALESCE(SUM(downloads), 0) as total FROM resources').fetchone()['total'],
            'total_views': db.execute('SELECT COALESCE(SUM(views), 0) as total FROM resources').fetchone()['total'],
            'total_users': db.execute('SELECT COUNT(*) as count FROM users').fetchone()['count'],
            'total_favorites': db.execute('SELECT COUNT(*) as count FROM favorites').fetchone()['count'],
        }

        rows = db.execute('''
            SELECT t.name as taxonomy_name, c.name, COUNT(rc.id) as count
            FROM categories c
            JOIN taxonomies t ON c.taxonomy_id = t.id
            LEFT JOIN resource_categories rc ON c.id = rc.category_id
            GROUP BY c.id
            ORDER BY t.id, count DESC
        ''').fetchall()

        taxonomy_pies = {}
        for r in rows:
            taxonomy_pies.setdefault(r['taxonomy_name'], []).append({'name': r['name'], 'count': r['count']})

        file_type_stats = db.execute('''
            SELECT file_type, COUNT(*) as count
            FROM resources
            GROUP BY file_type
            ORDER BY count DESC
        ''').fetchall()

        top_downloads = db.execute('''
            SELECT r.*, c.name as category_name
            FROM resources r
            LEFT JOIN categories c ON r.category_id = c.id
            ORDER BY r.downloads DESC
            LIMIT 10
        ''').fetchall()

        top_views = db.execute('''
            SELECT r.*, c.name as category_name
            FROM resources r
            LEFT JOIN categories c ON r.category_id = c.id
            ORDER BY r.views DESC
            LIMIT 5
        ''').fetchall()

        top_favorites = db.execute('''
            SELECT r.*, c.name as category_name, COUNT(f.id) as fav_count
            FROM resources r
            LEFT JOIN categories c ON r.category_id = c.id
            LEFT JOIN favorites f ON r.id = f.resource_id
            GROUP BY r.id
            ORDER BY fav_count DESC
            LIMIT 5
        ''').fetchall()

        rows = db.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM resources
            WHERE created_at >= DATE('now', '-30 days')
            GROUP BY DATE(created_at)
            ORDER BY date
        ''').fetchall()

        trend_map = {r['date']: r['count'] for r in rows}
        today = datetime.utcnow()
        upload_trend = []
        for i in range(29, -1, -1):
            d = (today - timedelta(days=i)).strftime('%Y-%m-%d')
            upload_trend.append({'date': d, 'count': trend_map.get(d, 0)})

        return render_template('dashboard.html',
                             stats=stats,
                             taxonomy_pies=taxonomy_pies,
                             file_type_stats=[dict(r) for r in file_type_stats],
                             top_downloads=top_downloads,
                             top_views=top_views,
                             top_favorites=top_favorites,
                             upload_trend=[dict(r) for r in upload_trend])
