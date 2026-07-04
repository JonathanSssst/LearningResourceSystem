import os
import uuid
import random
import string
import tempfile
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify

from db import get_db, resource_cats, taxonomies_with_terms, search_resources_fts
from helpers import login_required, allowed_file, get_file_type, csrf_token, verify_csrf, can_edit, is_admin


def register_resources_routes(app):

    @app.route('/resource', endpoint='resource')
    @login_required
    def resource():
        db = get_db()
        taxonomies = taxonomies_with_terms(db)
        return render_template('resource.html', taxonomies=taxonomies)

    @app.route('/resource/all', endpoint='resource_all')
    @login_required
    def resource_all():
        db = get_db()
        page = request.args.get('page', 1, type=int)
        sort = request.args.get('sort', 'created_at')
        my_uploads = request.args.get('my_uploads', type=int)
        per_page = app.config['PER_PAGE']
        offset = (page - 1) * per_page

        sort_map = {
            'created_at': 'r.created_at DESC',
            'created_at_asc': 'r.created_at ASC',
            'downloads': 'r.downloads DESC',
            'views': 'r.views DESC',
            'title': 'r.title ASC',
            'title_desc': 'r.title DESC',
        }
        order_clause = sort_map.get(sort, 'r.created_at DESC')

        selected = {}
        all_taxonomies = taxonomies_with_terms(db)
        for tax in all_taxonomies:
            val = request.args.get('cat_' + tax['slug'], type=int)
            if val:
                selected[tax['slug']] = val

        query = 'SELECT DISTINCT r.*, c.name as category_name FROM resources r LEFT JOIN categories c ON r.category_id = c.id'
        count_query = 'SELECT COUNT(DISTINCT r.id) as total FROM resources r'
        params = []
        where_parts = []

        for slug, cat_id in selected.items():
            alias = 'rc_' + slug
            query += ' JOIN resource_categories ' + alias + ' ON r.id = ' + alias + '.resource_id AND ' + alias + '.category_id = ?'
            count_query += ' JOIN resource_categories ' + alias + ' ON r.id = ' + alias + '.resource_id AND ' + alias + '.category_id = ?'
            params.append(cat_id)

        if my_uploads:
            where_parts.append('r.user_id = ?')
            params.append(session['user_id'])

        if not is_admin():
            where_parts.append("r.status = 'approved'")

        if where_parts:
            query += ' WHERE ' + ' AND '.join(where_parts)
            count_query += ' WHERE ' + ' AND '.join(where_parts)

        query += f' ORDER BY {order_clause} LIMIT ? OFFSET ?'
        params.extend([per_page, offset])

        resources = db.execute(query, params).fetchall()

        count_params = params[:-2]
        total = db.execute(count_query, count_params).fetchone()['total']
        total_pages = (total + per_page - 1) // per_page

        return render_template('resource_all.html',
                             resources=resources,
                             taxonomies=all_taxonomies,
                             page=page,
                             sort=sort,
                             total_pages=total_pages,
                             total=total,
                             selected=selected,
                             my_uploads=my_uploads)

    @app.route('/resource/detail', endpoint='resource_detail')
    @login_required
    def resource_detail():
        code = request.args.get('id', '')
        if not code:
            flash('资源不存在', 'error')
            return redirect(url_for('resource_all'))

        db = get_db()

        resource = db.execute('''
            SELECT r.*, c.name as category_name, u.username as uploader
            FROM resources r
            LEFT JOIN categories c ON r.category_id = c.id
            LEFT JOIN users u ON r.user_id = u.id
            WHERE r.code = ?
        ''', (code,)).fetchone()

        if not resource:
            flash('资源不存在', 'error')
            return redirect(url_for('resource_all'))

        resource_id = resource['id']

        db.execute('UPDATE resources SET views = views + 1 WHERE id = ?', (resource_id,))
        db.commit()

        is_favorited = db.execute('SELECT id FROM favorites WHERE user_id = ? AND resource_id = ?',
                                (session['user_id'], resource_id)).fetchone() is not None

        related = []

        cats = resource_cats(resource_id)
        taxonomies = taxonomies_with_terms(db)

        # Comments
        comments = db.execute('''
            SELECT c.*, u.username FROM comments c
            JOIN users u ON c.user_id = u.id
            WHERE c.resource_id = ? ORDER BY c.created_at DESC LIMIT 50
        ''', (resource_id,)).fetchall()

        # Average rating
        avg_rating = db.execute('''
            SELECT COALESCE(AVG(rating), 0) as avg, COUNT(*) as count
            FROM comments WHERE resource_id = ? AND rating > 0
        ''', (resource_id,)).fetchone()

        # Tags
        tags = db.execute('''
            SELECT t.id, t.name FROM resource_tags rt
            JOIN tags t ON rt.tag_id = t.id
            WHERE rt.resource_id = ? ORDER BY t.name
        ''', (resource_id,)).fetchall()

        # Versions
        versions = db.execute('''
            SELECT * FROM resource_versions WHERE resource_id = ? ORDER BY version_number DESC
        ''', (resource_id,)).fetchall()

        # User rating for this resource
        user_comment = db.execute('''
            SELECT rating FROM comments WHERE resource_id = ? AND user_id = ?
        ''', (resource_id, session['user_id'])).fetchone()

        return render_template('resource_detail.html',
                             resource=resource,
                             is_favorited=is_favorited,
                             related=related,
                             resource_cats=cats,
                             taxonomies=taxonomies,
                             can_edit=can_edit(resource),
                             comments=comments,
                             avg_rating=avg_rating,
                             tags=tags,
                             versions=versions,
                             user_rating=user_comment['rating'] if user_comment else 0)

    @app.route('/resource/suggest-related/<resource_id>', endpoint='resource_suggest_related')
    @login_required
    def resource_suggest_related(resource_id):
        db = get_db()
        resource = db.execute('SELECT * FROM resources WHERE code = ?', (resource_id,)).fetchone()
        if not resource:
            return jsonify({'success': False, 'error': '资源不存在'})
        rid = resource['id']

        try:
            all_others = db.execute('''
                SELECT id, title, description, file_type, file_size, created_at
                FROM resources WHERE id != ? ORDER BY downloads DESC LIMIT 200
            ''', (rid,)).fetchall()
            if not all_others:
                return jsonify({'success': True, 'related': []})

            from ai_service import suggest_related
            ai_ids = suggest_related(
                resource['title'],
                resource['description'] or '',
                [dict(r) for r in all_others],
                app.config
            )
            if not ai_ids:
                return jsonify({'success': True, 'related': []})

            placeholders = ','.join('?' for _ in ai_ids)
            rows = db.execute(
                f'SELECT id, code, title FROM resources WHERE id IN ({placeholders})',
                ai_ids
            ).fetchall()
            id_order = {v: k for k, v in enumerate(ai_ids)}
            rows.sort(key=lambda r: id_order.get(r['id'], 999))
            related = [{'id': r['id'], 'code': r['code'], 'title': r['title']} for r in rows]
            return jsonify({'success': True, 'related': related})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/resource/latests', endpoint='resource_latests')
    @login_required
    def resource_latests():
        db = get_db()
        page = request.args.get('page', 1, type=int)
        per_page = app.config['PER_PAGE']
        offset = (page - 1) * per_page

        resources = db.execute('''
            SELECT r.*, c.name as category_name
            FROM resources r
            LEFT JOIN categories c ON r.category_id = c.id
            ORDER BY r.created_at DESC
            LIMIT ? OFFSET ?
        ''', (per_page, offset)).fetchall()

        total = db.execute('SELECT COUNT(*) as total FROM resources').fetchone()['total']
        total_pages = (total + per_page - 1) // per_page

        return render_template('resource_latests.html',
                             resources=resources,
                             page=page,
                             total_pages=total_pages,
                             total=total)

    @app.route('/resource/ranks', endpoint='resource_ranks')
    @login_required
    def resource_ranks():
        db = get_db()

        by_downloads = db.execute('''
            SELECT r.*, c.name as category_name
            FROM resources r
            LEFT JOIN categories c ON r.category_id = c.id
            ORDER BY r.downloads DESC
            LIMIT 20
        ''').fetchall()

        by_views = db.execute('''
            SELECT r.*, c.name as category_name
            FROM resources r
            LEFT JOIN categories c ON r.category_id = c.id
            ORDER BY r.views DESC
            LIMIT 20
        ''').fetchall()

        by_favorites = db.execute('''
            SELECT r.*, c.name as category_name, COUNT(f.id) as fav_count
            FROM resources r
            LEFT JOIN categories c ON r.category_id = c.id
            LEFT JOIN favorites f ON r.id = f.resource_id
            GROUP BY r.id
            ORDER BY fav_count DESC
            LIMIT 20
        ''').fetchall()

        return render_template('resource_ranks.html',
                             by_downloads=by_downloads,
                             by_views=by_views,
                             by_favorites=by_favorites)

    @app.route('/search', endpoint='search')
    @login_required
    def search():
        q = request.args.get('q', '', type=str)
        sort = request.args.get('sort', 'created_at')
        ft = request.args.get('file_type', '')
        page = request.args.get('page', 1, type=int)
        per_page = app.config['PER_PAGE']

        resources = []
        total = 0
        if q:
            db = get_db()
            try:
                resources, total = search_resources_fts(q, ft, sort, page, per_page, db)
            except Exception:
                pass

        total_pages = (total + per_page - 1) // per_page if total else 0

        return render_template('search.html',
                             resources=resources,
                             q=q,
                             sort=sort,
                             file_type=ft,
                             page=page,
                             total_pages=total_pages,
                             total=total)

    @app.route('/resource/analyze', methods=['POST'], endpoint='resource_analyze')
    @login_required
    def resource_analyze():
        if not verify_csrf():
            return jsonify({'success': False, 'error': 'CSRF token无效'})
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '没有选择文件'})
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': '没有选择文件'})

        suffix = os.path.splitext(file.filename)[1]
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        try:
            file.save(tmp_path)
            os.close(fd)

            from ai_service import analyze_file
            db = get_db()
            taxonomies = taxonomies_with_terms(db)
            cat_text = '\n'.join(
                f'{t["name"]}: {", ".join(c["name"] for c in t["categories"])}'
                for t in taxonomies
            )
            user = db.execute('SELECT learning_stage FROM users WHERE id = ?', (session['user_id'],)).fetchone()
            result = analyze_file(tmp_path, file.filename, app.config, cat_text, user['learning_stage'] if user else '高中/高一')

            matched = {}
            for tax in taxonomies:
                suggested = result.get('category_suggestions', {}).get(tax['slug'], '')
                if suggested:
                    for cat in tax['categories']:
                        if suggested.lower() in cat['name'].lower() or cat['name'].lower() in suggested.lower():
                            matched[tax['slug']] = cat['id']
                            break

            return jsonify({'success': True, 'data': {
                'title': result.get('title', ''),
                'description': result.get('description', ''),
                'file_type': result.get('file_type', ''),
                'category_ids': matched,
            }})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @app.route('/resource/upload', methods=['GET', 'POST'], endpoint='resource_upload')
    @login_required
    def resource_upload():
        db = get_db()
        taxonomies = taxonomies_with_terms(db)

        if request.method == 'POST':
            if not verify_csrf():
                flash('表单已过期，请重试', 'error')
                return render_template('resource_upload.html', taxonomies=taxonomies)
            if 'file' not in request.files:
                flash('没有选择文件', 'error')
                return redirect(request.url)

            file = request.files['file']
            if file.filename == '':
                flash('没有选择文件', 'error')
                return redirect(request.url)

            if file and allowed_file(file.filename):
                original_filename = file.filename
                ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
                filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{ext}" if ext else uuid.uuid4().hex

                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                file_size = os.path.getsize(filepath)

                title = request.form.get('title', original_filename)
                description = request.form.get('description', '')
                file_type = get_file_type(file.filename)

                code = ''.join(random.choices(string.ascii_letters + string.digits, k=6))

                # Versioning: check if resource with same original_filename exists for this user
                existing = db.execute(
                    'SELECT id FROM resources WHERE original_filename = ? AND user_id = ?',
                    (original_filename, session['user_id'])
                ).fetchone()

                initial_status = 'approved' if is_admin() else 'pending'
                cursor = db.execute('''
                    INSERT INTO resources (code, title, description, filename, original_filename, file_type, file_size, user_id, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (code, title, description, filename, original_filename, file_type, file_size, session['user_id'], initial_status))
                resource_id = cursor.lastrowid

                if existing:
                    # Create version record for old file
                    old = db.execute('SELECT * FROM resources WHERE id = ?', (existing['id'],)).fetchone()
                    max_ver = db.execute('SELECT COALESCE(MAX(version_number), 0) as mv FROM resource_versions WHERE resource_id = ?',
                                        (existing['id'],)).fetchone()['mv']
                    db.execute('''
                        INSERT INTO resource_versions (resource_id, filename, original_filename, file_size, user_id, version_number)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (existing['id'], old['filename'], old['original_filename'], old['file_size'], old['user_id'], max_ver + 1))

                for tax in taxonomies:
                    key = f'cat_{tax["slug"]}'
                    cat_id = request.form.get(key, type=int)
                    if cat_id:
                        db.execute('INSERT OR IGNORE INTO resource_categories (resource_id, category_id) VALUES (?, ?)',
                                  (resource_id, cat_id))
                        if tax['slug'] == 'file_type':
                            db.execute('UPDATE resources SET category_id = ? WHERE id = ?', (cat_id, resource_id))

                db.commit()

                flash('资源上传成功！', 'success')
                return redirect(url_for('resource_detail', id=code))
            else:
                flash('不支持的文件类型', 'error')

        return render_template('resource_upload.html', taxonomies=taxonomies)

    @app.route('/resource/edit/<resource_id>', methods=['GET', 'POST'], endpoint='resource_edit')
    @login_required
    def resource_edit(resource_id):
        db = get_db()
        resource = db.execute('SELECT * FROM resources WHERE code = ?', (resource_id,)).fetchone()
        if not resource:
            flash('资源不存在', 'error')
            return redirect(url_for('resource_all'))

        if not can_edit(resource):
            flash('无权编辑此资源', 'error')
            return redirect(url_for('resource_detail', id=resource_id))

        taxonomies = taxonomies_with_terms(db)
        cats = resource_cats(resource['id'])

        if request.method == 'POST':
            if not verify_csrf():
                flash('表单已过期，请重试', 'error')
                return redirect(url_for('resource_edit', resource_id=resource_id))
            title = request.form.get('title', resource['title'])
            description = request.form.get('description', '')
            db.execute('UPDATE resources SET title = ?, description = ? WHERE id = ?',
                       (title, description, resource['id']))

            rid = resource['id']
            for tax in taxonomies:
                key = f'cat_{tax["slug"]}'
                cat_id = request.form.get(key, type=int)
                db.execute('''
                    DELETE FROM resource_categories WHERE resource_id = ? AND category_id IN (
                        SELECT id FROM categories WHERE taxonomy_id = ?
                    )
                ''', (rid, tax['id']))
                if cat_id:
                    db.execute('INSERT OR IGNORE INTO resource_categories (resource_id, category_id) VALUES (?, ?)',
                              (rid, cat_id))
                    if tax['slug'] == 'file_type':
                        db.execute('UPDATE resources SET category_id = ? WHERE id = ?', (cat_id, rid))

            db.commit()
            flash('资源已更新', 'success')
            return redirect(url_for('resource_detail', id=resource_id))

        return render_template('resource_edit.html',
                             resource=resource,
                             taxonomies=taxonomies,
                             resource_cats=cats)

    @app.route('/resource/batch-upload', methods=['POST'], endpoint='resource_batch_upload')
    @login_required
    def resource_batch_upload():
        if not verify_csrf():
            return jsonify({'success': False, 'error': 'CSRF token无效'})
        files = request.files.getlist('files')
        use_ai = request.form.get('use_ai') == '1'
        if not files:
            return jsonify({'success': False, 'error': '没有选择文件'})

        db = get_db()
        taxonomies = taxonomies_with_terms(db)

        if use_ai:
            cat_text = '\n'.join(
                f'{t["name"]}: {", ".join(c["name"] for c in t["categories"])}'
                for t in taxonomies
            )
            user = db.execute('SELECT learning_stage FROM users WHERE id = ?', (session['user_id'],)).fetchone()
            learning_stage = user['learning_stage'] if user else '高中/高一'

        results = []

        for file in files:
            if not file.filename or not allowed_file(file.filename):
                results.append({'filename': getattr(file, 'filename', '未知'), 'success': False, 'error': '不支持的文件类型'})
                continue

            original_filename = file.filename
            ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{ext}" if ext else uuid.uuid4().hex
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            file_size = os.path.getsize(filepath)
            file_type = get_file_type(file.filename)
            code = ''.join(random.choices(string.ascii_letters + string.digits, k=6))

            title = original_filename
            description = ''
            matched = {}

            if use_ai:
                try:
                    from ai_service import analyze_file
                    ai_result = analyze_file(filepath, file.filename, app.config, cat_text, learning_stage)
                    title = ai_result.get('title', original_filename)
                    description = ai_result.get('description', '')
                    for tax in taxonomies:
                        suggested = ai_result.get('category_suggestions', {}).get(tax['slug'], '')
                        if suggested:
                            for cat in tax['categories']:
                                if suggested.lower() in cat['name'].lower() or cat['name'].lower() in suggested.lower():
                                    matched[tax['slug']] = cat['id']
                                    break
                except Exception:
                    pass

            initial_status = 'approved' if is_admin() else 'pending'
            cursor = db.execute('''
                INSERT INTO resources (code, title, description, filename, original_filename, file_type, file_size, user_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (code, title, description, filename, original_filename, file_type, file_size, session['user_id'], initial_status))
            resource_id = cursor.lastrowid

            for slug, cat_id in matched.items():
                db.execute('INSERT OR IGNORE INTO resource_categories (resource_id, category_id) VALUES (?, ?)',
                          (resource_id, cat_id))
                if slug == 'file_type':
                    db.execute('UPDATE resources SET category_id = ? WHERE id = ?', (cat_id, resource_id))

            if not use_ai:
                for tax in taxonomies:
                    key = f'cat_{tax["slug"]}'
                    cat_id = request.form.get(key, type=int)
                    if cat_id:
                        db.execute('INSERT OR IGNORE INTO resource_categories (resource_id, category_id) VALUES (?, ?)',
                                  (resource_id, cat_id))
                        if tax['slug'] == 'file_type':
                            db.execute('UPDATE resources SET category_id = ? WHERE id = ?', (cat_id, resource_id))

            db.commit()
            results.append({'filename': original_filename, 'success': True, 'code': code})

        error_count = sum(1 for r in results if not r['success'])
        return jsonify({'success': True, 'results': results, 'total': len(results), 'errors': error_count})

    @app.route('/resource/download/<resource_id>', endpoint='resource_download')
    @login_required
    def resource_download(resource_id):
        db = get_db()
        resource = db.execute('SELECT * FROM resources WHERE code = ?', (resource_id,)).fetchone()

        if not resource:
            flash('资源不存在', 'error')
            return redirect(url_for('resource_all'))

        db.execute('UPDATE resources SET downloads = downloads + 1 WHERE id = ?', (resource['id'],))
        db.commit()

        return send_from_directory(app.config['UPLOAD_FOLDER'], resource['filename'],
                                 as_attachment=True, download_name=resource['original_filename'])

    @app.route('/resource/delete/<resource_id>', methods=['POST'], endpoint='resource_delete')
    @login_required
    def resource_delete(resource_id):
        if not verify_csrf():
            flash('表单已过期，请重试', 'error')
            return redirect(url_for('resource_all'))
        db = get_db()
        resource = db.execute('SELECT * FROM resources WHERE code = ?', (resource_id,)).fetchone()

        if not resource:
            flash('资源不存在', 'error')
            return redirect(url_for('resource_all'))

        if not can_edit(resource):
            flash('无权删除此资源', 'error')
            return redirect(url_for('resource_detail', id=resource_id))

        rid = resource['id']
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], resource['filename'])
        if os.path.exists(filepath):
            os.remove(filepath)

        db.execute('DELETE FROM favorites WHERE resource_id = ?', (rid,))
        db.execute('DELETE FROM resource_categories WHERE resource_id = ?', (rid,))
        db.execute('DELETE FROM resources WHERE id = ?', (rid,))
        db.commit()

        flash('资源已删除', 'success')
        return redirect(url_for('resource_all'))

    @app.route('/resource/all/batch-delete', methods=['POST'], endpoint='resource_all_batch_delete')
    @login_required
    def resource_all_batch_delete():
        if not verify_csrf():
            flash('表单已过期，请重试', 'error')
            return redirect(url_for('resource_all'))
        codes = request.form.getlist('codes')
        if not codes:
            flash('没有选择任何资源', 'error')
            return redirect(url_for('resource_all', page=int(request.form.get('page', 1))))

        db = get_db()
        placeholders = ','.join('?' for _ in codes)
        is_admin = session.get('username') == 'admin'
        if is_admin:
            resources = db.execute(f'SELECT id, filename FROM resources WHERE code IN ({placeholders})', codes).fetchall()
        else:
            resources = db.execute(f'SELECT id, filename FROM resources WHERE code IN ({placeholders}) AND user_id = ?', codes + [session['user_id']]).fetchall()

        for r in resources:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], r['filename'])
            if os.path.exists(filepath):
                os.remove(filepath)

        if resources:
            ids = [r['id'] for r in resources]
            id_placeholders = ','.join('?' for _ in ids)
            db.execute(f'DELETE FROM favorites WHERE resource_id IN ({id_placeholders})', ids)
            db.execute(f'DELETE FROM resource_categories WHERE resource_id IN ({id_placeholders})', ids)
            db.execute(f'DELETE FROM resources WHERE id IN ({id_placeholders})', ids)
            db.commit()
        flash(f'已删除 {len(resources)} 个资源', 'success')

        page = int(request.form.get('page', 1))
        selected = {}
        for key, val in request.form.items():
            if key.startswith('cat_'):
                selected[key] = val
        return redirect(url_for('resource_all', page=page, **selected))

    @app.route('/resource/move/<resource_id>', methods=['POST'], endpoint='resource_move')
    @login_required
    def resource_move(resource_id):
        if not verify_csrf():
            flash('表单已过期，请重试', 'error')
            return redirect(url_for('resource_detail', id=resource_id))
        db = get_db()
        resource = db.execute('SELECT * FROM resources WHERE code = ?', (resource_id,)).fetchone()
        if not resource:
            flash('资源不存在', 'error')
            return redirect(url_for('resource_all'))
        if not can_edit(resource):
            flash('无权修改此资源分类', 'error')
            return redirect(url_for('resource_detail', id=resource_id))
        rid = resource['id']
        taxonomies = taxonomies_with_terms(db)

        for tax in taxonomies:
            key = f'cat_{tax["slug"]}'
            cat_id = request.form.get(key, type=int)
            db.execute('''
                DELETE FROM resource_categories WHERE resource_id = ? AND category_id IN (
                    SELECT id FROM categories WHERE taxonomy_id = ?
                )
            ''', (rid, tax['id']))
            if cat_id:
                db.execute('INSERT OR IGNORE INTO resource_categories (resource_id, category_id) VALUES (?, ?)',
                          (rid, cat_id))
                if tax['slug'] == 'file_type':
                    db.execute('UPDATE resources SET category_id = ? WHERE id = ?', (cat_id, rid))

        db.commit()
        flash('分类已更新', 'success')
        return redirect(url_for('resource_detail', id=resource_id))

    @app.route('/resource/favorite/<resource_id>', methods=['POST'], endpoint='resource_favorite')
    @login_required
    def resource_favorite(resource_id):
        if not verify_csrf():
            flash('表单已过期，请重试', 'error')
            return redirect(url_for('resource_detail', id=resource_id))
        db = get_db()
        resource = db.execute('SELECT * FROM resources WHERE code = ?', (resource_id,)).fetchone()
        if not resource:
            flash('资源不存在', 'error')
            return redirect(url_for('resource_all'))
        rid = resource['id']

        existing = db.execute('SELECT id FROM favorites WHERE user_id = ? AND resource_id = ?',
                             (session['user_id'], rid)).fetchone()

        if existing:
            db.execute('DELETE FROM favorites WHERE id = ?', (existing['id'],))
            message = '已取消收藏'
        else:
            db.execute('INSERT INTO favorites (user_id, resource_id) VALUES (?, ?)',
                      (session['user_id'], rid))
            message = '已添加收藏'

        db.commit()
        flash(message, 'success')
        return redirect(url_for('resource_detail', id=resource_id))

    @app.route('/resource/preview/<resource_id>', endpoint='resource_preview')
    @login_required
    def resource_preview(resource_id):
        db = get_db()
        resource = db.execute('SELECT * FROM resources WHERE code = ?', (resource_id,)).fetchone()

        if not resource:
            flash('资源不存在', 'error')
            return redirect(url_for('resource_all'))

        if resource['file_type'] == 'image':
            return send_from_directory(app.config['UPLOAD_FOLDER'], resource['filename'])

        if resource['file_type'] in ('text', 'code'):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], resource['filename'])
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(50000)
                return render_template('resource_preview.html',
                                     resource=resource,
                                     content=content,
                                     preview_type='text')
            except Exception:
                pass

        if resource['file_type'] in ('video', 'audio'):
            return send_from_directory(app.config['UPLOAD_FOLDER'], resource['filename'])

        if resource['file_type'] == 'pdf':
            if request.args.get('raw'):
                return send_from_directory(app.config['UPLOAD_FOLDER'], resource['filename'])
            return render_template('resource_preview.html',
                                 resource=resource,
                                 preview_type='pdf')

        return render_template('resource_preview.html',
                             resource=resource,
                             preview_type='unsupported')

    @app.route('/favorites', endpoint='favorites')
    @login_required
    def favorites():
        db = get_db()
        page = request.args.get('page', 1, type=int)
        per_page = app.config['PER_PAGE']
        offset = (page - 1) * per_page

        resources = db.execute('''
            SELECT r.*, c.name as category_name, f.created_at as favorited_at
            FROM favorites f
            JOIN resources r ON f.resource_id = r.id
            LEFT JOIN categories c ON r.category_id = c.id
            WHERE f.user_id = ?
            ORDER BY f.created_at DESC
            LIMIT ? OFFSET ?
        ''', (session['user_id'], per_page, offset)).fetchall()

        total = db.execute('SELECT COUNT(*) as total FROM favorites WHERE user_id = ?',
                          (session['user_id'],)).fetchone()['total']
        total_pages = (total + per_page - 1) // per_page

        return render_template('favorites.html',
                             resources=resources,
                             page=page,
                             total_pages=total_pages,
                             total=total,
                             per_page=per_page)

    @app.route('/favorites/batch-delete', methods=['POST'], endpoint='favorites_batch_delete')
    @login_required
    def favorites_batch_delete():
        if not verify_csrf():
            flash('表单已过期，请重试', 'error')
            return redirect(url_for('favorites'))
        codes = request.form.getlist('codes')
        if not codes:
            flash('没有选择任何资源', 'error')
            return redirect(url_for('favorites'))

        db = get_db()
        placeholders = ','.join('?' for _ in codes)
        db.execute(f'''
            DELETE FROM favorites WHERE user_id = ? AND resource_id IN (
                SELECT id FROM resources WHERE code IN ({placeholders})
            )
        ''', [session['user_id']] + codes)
        db.commit()
        flash(f'已取消 {len(codes)} 个资源的收藏', 'success')
        return redirect(url_for('favorites', page=int(request.form.get('page', 1))))

    @app.route('/resource/comment/<resource_code>', methods=['POST'], endpoint='resource_comment')
    @login_required
    def resource_comment(resource_code):
        if not verify_csrf():
            flash('表单已过期', 'error')
            return redirect(url_for('resource_detail', id=resource_code))
        db = get_db()
        resource = db.execute('SELECT * FROM resources WHERE code = ?', (resource_code,)).fetchone()
        if not resource:
            flash('资源不存在', 'error')
            return redirect(url_for('resource_all'))
        content = request.form.get('content', '').strip()
        rating = request.form.get('rating', 0, type=int)
        if not content:
            flash('评论内容不能为空', 'error')
            return redirect(url_for('resource_detail', id=resource_code))
        if rating < 0 or rating > 5:
            rating = 0
        existing = db.execute('SELECT id FROM comments WHERE resource_id = ? AND user_id = ?',
                            (resource['id'], session['user_id'])).fetchone()
        if existing:
            db.execute('UPDATE comments SET content = ?, rating = ? WHERE id = ?',
                      (content, rating, existing['id']))
        else:
            db.execute('INSERT INTO comments (resource_id, user_id, content, rating) VALUES (?, ?, ?, ?)',
                      (resource['id'], session['user_id'], content, rating))
        db.commit()
        flash('评论已提交', 'success')
        return redirect(url_for('resource_detail', id=resource_code))

    @app.route('/resource/tags/<resource_code>', methods=['POST'], endpoint='resource_tags')
    @login_required
    def resource_tags(resource_code):
        if not verify_csrf():
            flash('表单已过期', 'error')
            return redirect(url_for('resource_detail', id=resource_code))
        db = get_db()
        resource = db.execute('SELECT * FROM resources WHERE code = ?', (resource_code,)).fetchone()
        if not resource:
            flash('资源不存在', 'error')
            return redirect(url_for('resource_all'))
        if not can_edit(resource):
            flash('无权修改标签', 'error')
            return redirect(url_for('resource_detail', id=resource_code))
        tag_names = [t.strip() for t in request.form.get('tags', '').split(',') if t.strip()]
        rid = resource['id']
        db.execute('DELETE FROM resource_tags WHERE resource_id = ?', (rid,))
        for name in tag_names:
            existing = db.execute('SELECT id FROM tags WHERE name = ?', (name,)).fetchone()
            if existing:
                tag_id = existing['id']
            else:
                cursor = db.execute('INSERT INTO tags (name) VALUES (?)', (name,))
                tag_id = cursor.lastrowid
            db.execute('INSERT OR IGNORE INTO resource_tags (resource_id, tag_id) VALUES (?, ?)', (rid, tag_id))
        db.commit()
        flash('标签已更新', 'success')
        return redirect(url_for('resource_detail', id=resource_code))

    @app.route('/tag/search', endpoint='tag_search')
    @login_required
    def tag_search():
        q = request.args.get('q', '', type=str)
        if not q:
            return jsonify([])
        db = get_db()
        tags = db.execute('SELECT id, name FROM tags WHERE name LIKE ? ORDER BY name LIMIT 20',
                         (f'%{q}%',)).fetchall()
        return jsonify([dict(t) for t in tags])

    @app.route('/admin/pending', endpoint='admin_pending')
    @login_required
    def admin_pending():
        if not is_admin():
            flash('无权限', 'error')
            return redirect(url_for('home'))
        db = get_db()
        page = request.args.get('page', 1, type=int)
        per_page = app.config['PER_PAGE']
        offset = (page - 1) * per_page

        resources = db.execute('''
            SELECT r.*, u.username as uploader FROM resources r
            LEFT JOIN users u ON r.user_id = u.id
            WHERE r.status != 'approved'
            ORDER BY r.created_at DESC LIMIT ? OFFSET ?
        ''', (per_page, offset)).fetchall()

        total = db.execute("SELECT COUNT(*) as total FROM resources WHERE status != 'approved'").fetchone()['total']
        total_pages = (total + per_page - 1) // per_page

        pending_count = db.execute("SELECT COUNT(*) as cnt FROM resources WHERE status = 'pending'").fetchone()['cnt']

        return render_template('admin_pending.html',
                             resources=resources,
                             page=page,
                             total_pages=total_pages,
                             total=total,
                             pending_count=pending_count)

    @app.route('/resource/approve/<resource_code>', methods=['POST'], endpoint='resource_approve')
    @login_required
    def resource_approve(resource_code):
        if not is_admin():
            flash('无权限', 'error')
            return redirect(url_for('home'))
        if not verify_csrf():
            flash('表单已过期', 'error')
            return redirect(url_for('home'))
        db = get_db()
        db.execute('UPDATE resources SET status = ? WHERE code = ?', ('approved', resource_code))
        db.commit()
        flash('资源已通过审核', 'success')
        return redirect(url_for('resource_detail', id=resource_code))

    @app.route('/resource/reject/<resource_code>', methods=['POST'], endpoint='resource_reject')
    @login_required
    def resource_reject(resource_code):
        if not is_admin():
            flash('无权限', 'error')
            return redirect(url_for('home'))
        if not verify_csrf():
            flash('表单已过期', 'error')
            return redirect(url_for('home'))
        db = get_db()
        db.execute('UPDATE resources SET status = ? WHERE code = ?', ('rejected', resource_code))
        db.commit()
        flash('资源已拒绝', 'info')
        return redirect(url_for('resource_detail', id=resource_code))

    @app.route('/resource/version/download/<int:version_id>', endpoint='version_download')
    @login_required
    def version_download(version_id):
        db = get_db()
        version = db.execute('''
            SELECT v.*, r.code FROM resource_versions v
            JOIN resources r ON v.resource_id = r.id
            WHERE v.id = ?
        ''', (version_id,)).fetchone()
        if not version:
            flash('版本不存在', 'error')
            return redirect(url_for('home'))
        return send_from_directory(app.config['UPLOAD_FOLDER'], version['filename'],
                                 as_attachment=True, download_name=version['original_filename'])
