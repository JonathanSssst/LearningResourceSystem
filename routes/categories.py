import sqlite3
from flask import render_template, request, redirect, url_for, flash

from db import get_db, taxonomies_with_terms
from helpers import login_required, csrf_token, verify_csrf


def register_categories_routes(app):

    @app.route('/categories', endpoint='categories')
    @login_required
    def categories():
        db = get_db()
        all_taxonomies = taxonomies_with_terms(db)
        return render_template('categories.html', taxonomies=all_taxonomies)

    @app.route('/category/add', methods=['POST'], endpoint='category_add')
    @login_required
    def category_add():
        if not verify_csrf():
            flash('表单已过期，请重试', 'error')
            return redirect(url_for('categories'))
        name = request.form.get('name', '')
        description = request.form.get('description', '')
        taxonomy_id = request.form.get('taxonomy_id', 1, type=int)

        if name:
            db = get_db()
            try:
                db.execute('INSERT INTO categories (name, description, taxonomy_id) VALUES (?, ?, ?)', (name, description, taxonomy_id))
                db.commit()
                flash('分类添加成功', 'success')
            except sqlite3.IntegrityError:
                flash('该分类名称在此分类维度中已存在', 'error')

        return redirect(url_for('categories'))

    @app.route('/category/delete/<int:category_id>', methods=['POST'], endpoint='category_delete')
    @login_required
    def category_delete(category_id):
        if not verify_csrf():
            flash('表单已过期，请重试', 'error')
            return redirect(url_for('categories'))
        db = get_db()

        db.execute('DELETE FROM resource_categories WHERE category_id = ?', (category_id,))
        db.execute('UPDATE resources SET category_id = NULL WHERE category_id = ?', (category_id,))
        db.execute('DELETE FROM categories WHERE id = ?', (category_id,))
        db.commit()

        flash('分类已删除', 'info')
        return redirect(url_for('categories'))

    @app.route('/category/edit/<int:category_id>', methods=['POST'], endpoint='category_edit')
    @login_required
    def category_edit(category_id):
        if not verify_csrf():
            flash('表单已过期，请重试', 'error')
            return redirect(url_for('categories'))
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        if not name:
            flash('分类名称不能为空', 'error')
            return redirect(url_for('categories'))

        db = get_db()
        try:
            db.execute('UPDATE categories SET name = ?, description = ? WHERE id = ?',
                       (name, description, category_id))
            db.commit()
            flash('分类已更新', 'success')
        except sqlite3.IntegrityError:
            flash('该分类名称已存在', 'error')
        return redirect(url_for('categories'))
