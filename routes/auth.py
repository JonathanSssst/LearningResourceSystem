import secrets
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from flask import render_template, request, redirect, url_for, session, flash, current_app

from db import get_db
from helpers import login_required, verify_csrf, is_admin


def register_auth_routes(app):

    @app.route('/login', methods=['GET', 'POST'], endpoint='login')
    def login():
        if request.method == 'POST':
            if not verify_csrf():
                flash('表单已过期，请重试', 'error')
                return render_template('login.html')
            username = request.form.get('username', '')
            password = request.form.get('password', '')

            db = get_db()
            user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role'] or 'user'
                session['timezone'] = user['timezone'] or '+08:00'
                session['csrf_token'] = secrets.token_hex(16)
                if request.form.get('remember'):
                    session.permanent = True
                    app.permanent_session_lifetime = 2592000  # 30 days
                flash('登录成功！', 'success')
                next_url = request.args.get('next')
                return redirect(next_url or url_for('home'))
            else:
                flash('用户名或密码错误', 'error')

        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'], endpoint='register')
    def register():
        if request.method == 'POST':
            if not verify_csrf():
                flash('表单已过期，请重试', 'error')
                return render_template('register.html')
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            confirm = request.form.get('confirm', '')
            learning_stage = request.form.get('learning_stage', '高中/高一')

            if not username or not password:
                flash('用户名和密码不能为空', 'error')
                return render_template('register.html')

            if password != confirm:
                flash('两次密码输入不一致', 'error')
                return render_template('register.html')

            db = get_db()
            try:
                db.execute('INSERT INTO users (username, password, email, learning_stage) VALUES (?, ?, ?, ?)',
                           (username, generate_password_hash(password), '', learning_stage))
                db.commit()
                flash('注册成功，请登录', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('用户名已存在', 'error')

        return render_template('register.html')

    @app.route('/profile', methods=['GET', 'POST'], endpoint='profile')
    @login_required
    def profile():
        db = get_db()
        if request.method == 'POST':
            action = request.form.get('action', '')
            if action == 'password':
                old_pw = request.form.get('old_password', '')
                new_pw = request.form.get('new_password', '')
                confirm = request.form.get('confirm_password', '')
                user = db.execute('SELECT password FROM users WHERE id = ?', (session['user_id'],)).fetchone()
                if user and not check_password_hash(user['password'], old_pw):
                    flash('原密码错误', 'error')
                elif not new_pw:
                    flash('新密码不能为空', 'error')
                elif new_pw != confirm:
                    flash('两次密码输入不一致', 'error')
                else:
                    db.execute('UPDATE users SET password = ? WHERE id = ?',
                               (generate_password_hash(new_pw), session['user_id']))
                    db.commit()
                    flash('密码已修改', 'success')
                return redirect(url_for('profile'))

            learning_stage = request.form.get('learning_stage', '高中/高一')
            timezone = request.form.get('timezone', '+08:00')
            db.execute('UPDATE users SET learning_stage = ?, timezone = ? WHERE id = ?',
                       (learning_stage, timezone, session['user_id']))
            db.commit()
            session['timezone'] = timezone
            flash('设置已更新', 'success')
            return redirect(url_for('profile'))

        user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        session['timezone'] = user['timezone'] or '+08:00'

        page = request.args.get('page', 1, type=int)
        per_page = 10
        offset = (page - 1) * per_page
        resources = db.execute('''
            SELECT r.*, c.name as category_name FROM resources r
            LEFT JOIN categories c ON r.category_id = c.id
            WHERE r.user_id = ? ORDER BY r.created_at DESC LIMIT ? OFFSET ?
        ''', (session['user_id'], per_page, offset)).fetchall()
        total = db.execute('SELECT COUNT(*) as cnt FROM resources WHERE user_id = ?', (session['user_id'],)).fetchone()['cnt']
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        return render_template('profile.html', user=user, resources=resources, page=page, total_pages=total_pages, total=total)

    @app.route('/logout', endpoint='logout')
    def logout():
        session.clear()
        flash('已退出登录', 'info')
        return redirect(url_for('login'))

    @app.route('/admin/users', endpoint='admin_users')
    @login_required
    def admin_users():
        if not is_admin():
            flash('无权限访问', 'error')
            return redirect(url_for('home'))

        db = get_db()
        q = request.args.get('q', '', type=str)
        page = request.args.get('page', 1, type=int)
        per_page = 15
        offset = (page - 1) * per_page

        if q:
            search = f'%{q}%'
            total = db.execute('SELECT COUNT(*) as t FROM users WHERE username LIKE ?', (search,)).fetchone()['t']
            users = db.execute('''
                SELECT u.*, (SELECT COUNT(*) FROM resources WHERE user_id = u.id) as resource_count,
                       (SELECT COUNT(*) FROM favorites WHERE user_id = u.id) as favorite_count
                FROM users u WHERE u.username LIKE ? ORDER BY u.created_at DESC LIMIT ? OFFSET ?
            ''', (search, per_page, offset)).fetchall()
        else:
            total = db.execute('SELECT COUNT(*) as t FROM users').fetchone()['t']
            users = db.execute('''
                SELECT u.*, (SELECT COUNT(*) FROM resources WHERE user_id = u.id) as resource_count,
                       (SELECT COUNT(*) FROM favorites WHERE user_id = u.id) as favorite_count
                FROM users u ORDER BY u.created_at DESC LIMIT ? OFFSET ?
            ''', (per_page, offset)).fetchall()

        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        return render_template('admin_users.html', users=users, page=page, total_pages=total_pages, total=total, q=q)

    @app.route('/admin/user/edit/<int:user_id>', methods=['POST'], endpoint='admin_user_edit')
    @login_required
    def admin_user_edit(user_id):
        if not is_admin():
            flash('无权限访问', 'error')
            return redirect(url_for('home'))
        if not verify_csrf():
            flash('表单已过期', 'error')
            return redirect(url_for('admin_users'))

        db = get_db()
        user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            flash('用户不存在', 'error')
            return redirect(url_for('admin_users'))

        role = request.form.get('role', 'user')
        learning_stage = request.form.get('learning_stage', '高中/高一')
        timezone = request.form.get('timezone', '+08:00')
        new_password = request.form.get('new_password', '')

        db.execute('UPDATE users SET role = ?, learning_stage = ?, timezone = ? WHERE id = ?',
                   (role, learning_stage, timezone, user_id))
        if new_password:
            from werkzeug.security import generate_password_hash
            db.execute('UPDATE users SET password = ? WHERE id = ?',
                       (generate_password_hash(new_password), user_id))
        db.commit()
        flash('用户信息已更新', 'success')
        return redirect(url_for('admin_users'))

    @app.route('/admin/user/delete/<int:user_id>', methods=['POST'], endpoint='admin_user_delete')
    @login_required
    def admin_user_delete(user_id):
        if not is_admin():
            flash('无权限访问', 'error')
            return redirect(url_for('home'))
        if not verify_csrf():
            flash('表单已过期', 'error')
            return redirect(url_for('admin_users'))
        if user_id == session['user_id']:
            flash('不能删除自己', 'error')
            return redirect(url_for('admin_users'))

        db = get_db()
        user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            flash('用户不存在', 'error')
            return redirect(url_for('admin_users'))

        db.execute('DELETE FROM favorites WHERE user_id = ?', (user_id,))
        db.execute('DELETE FROM resource_categories WHERE resource_id IN (SELECT id FROM resources WHERE user_id = ?)', (user_id,))
        db.execute('DELETE FROM resources WHERE user_id = ?', (user_id,))
        db.execute('DELETE FROM users WHERE id = ?', (user_id,))
        db.commit()
        flash(f'用户 {user["username"]} 已删除', 'success')
        return redirect(url_for('admin_users'))
