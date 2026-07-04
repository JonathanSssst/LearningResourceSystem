import os
import sqlite3
import string
import random
from werkzeug.security import generate_password_hash
from flask import g, current_app


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db(db_path=None):
    if db_path is None:
        db_path = current_app.config['DATABASE']
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = sqlite3.connect(db_path)
    cursor = db.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            role TEXT DEFAULT 'user',
            learning_stage TEXT DEFAULT '高中/高一',
            timezone TEXT DEFAULT '+08:00',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS taxonomies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            icon TEXT DEFAULT 'folder',
            taxonomy_id INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (taxonomy_id) REFERENCES taxonomies (id),
            UNIQUE(name, taxonomy_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            title TEXT NOT NULL,
            description TEXT,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            file_type TEXT,
            file_size INTEGER,
            category_id INTEGER,
            user_id INTEGER,
            downloads INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            status TEXT DEFAULT 'approved',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resource_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            FOREIGN KEY (resource_id) REFERENCES resources (id),
            FOREIGN KEY (category_id) REFERENCES categories (id),
            UNIQUE(resource_id, category_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            resource_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (resource_id) REFERENCES resources (id),
            UNIQUE(user_id, resource_id)
        )
    ''')

    default_taxonomies = [
        ('文件类型', 'file_type', '按文件格式和类型分类'),
        ('学科分类', 'subject', '按学科领域和知识体系分类'),
        ('难度等级', 'difficulty', '按学习难度和进阶程度分类'),
    ]
    for name, slug, desc in default_taxonomies:
        cursor.execute('SELECT id FROM taxonomies WHERE slug = ?', (slug,))
        if not cursor.fetchone():
            cursor.execute('INSERT INTO taxonomies (name, slug, description) VALUES (?, ?, ?)', (name, slug, desc))

    cursor.execute('SELECT id, slug FROM taxonomies')
    tax_map = {row[1]: row[0] for row in cursor.fetchall()}

    default_categories = {
        'file_type': [
            ('文档资料', '各类学习文档、笔记、资料', 'file-text'),
            ('视频教程', '教学视频、课程录像', 'video'),
            ('音频资料', '音频课程、听力材料', 'music'),
            ('代码项目', '编程项目、源代码', 'code'),
            ('图片素材', '学习相关图片、图表', 'image'),
            ('压缩包', '打包的资料集合', 'archive'),
            ('其他', '其他类型的学习资源', 'file'),
        ],
        'subject': [
            ('数学', '数学学科相关资源', 'function'),
            ('物理', '物理学科相关资源', 'atom'),
            ('化学', '化学学科相关资源', 'flask'),
            ('生物', '生物学科相关资源', 'dna'),
            ('计算机科学', '计算机科学相关资源', 'computer'),
            ('英语', '英语学习相关资源', 'translate'),
            ('语文', '语文与文学相关资源', 'book'),
            ('历史', '历史学科相关资源', 'history'),
            ('地理', '地理学科相关资源', 'earth'),
            ('政治', '政治学科相关资源', 'government'),
            ('其他学科', '其他学科领域资源', 'more'),
        ],
        'difficulty': [
            ('入门', '适合初学者，无基础要求', 'seed'),
            ('初级', '需要一定基础知识', 'plant'),
            ('中级', '需要较好的基础知识', 'tree'),
            ('高级', '需要扎实的专业知识', 'mountain'),
            ('专家', '面向专业人士的深度内容', 'star'),
        ],
    }

    for slug, cats in default_categories.items():
        tid = tax_map.get(slug)
        if tid is None:
            continue
        for name, desc, icon in cats:
            cursor.execute('SELECT id FROM categories WHERE name = ? AND taxonomy_id = ?', (name, tid))
            if not cursor.fetchone():
                cursor.execute('INSERT INTO categories (name, description, icon, taxonomy_id) VALUES (?, ?, ?, ?)', (name, desc, icon, tid))

    try:
        cursor.execute('ALTER TABLE users ADD COLUMN role TEXT DEFAULT \'user\'')
    except Exception:
        pass

    cursor.execute('SELECT id FROM users WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        cursor.execute('INSERT INTO users (username, password, email, learning_stage) VALUES (?, ?, ?, ?)', ('admin', generate_password_hash('admin123'), 'admin@lrs.com', '高中/高一'))
    cursor.execute('UPDATE users SET role = ? WHERE username = ?', ('admin', 'admin'))

    rows = cursor.execute('SELECT id, password FROM users').fetchall()
    for row in rows:
        if '$' not in row[1]:
            cursor.execute('UPDATE users SET password = ? WHERE id = ?', (generate_password_hash(row[1]), row[0]))

    try:
        cursor.execute('ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT \'+08:00\'')
    except Exception:
        pass

    try:
        cursor.execute('ALTER TABLE resources ADD COLUMN code TEXT')
    except Exception:
        pass

    existing = cursor.execute('SELECT id, code FROM resources WHERE code IS NULL').fetchall()
    for row in existing:
        code = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        cursor.execute('UPDATE resources SET code = ? WHERE id = ?', (code, row[0]))

    # Create indexes for performance
    for idx_sql in [
        'CREATE INDEX IF NOT EXISTS idx_resources_user_id ON resources(user_id)',
        'CREATE INDEX IF NOT EXISTS idx_resources_category_id ON resources(category_id)',
        'CREATE INDEX IF NOT EXISTS idx_resources_code ON resources(code)',
        'CREATE INDEX IF NOT EXISTS idx_resources_file_type ON resources(file_type)',
        'CREATE INDEX IF NOT EXISTS idx_resources_created_at ON resources(created_at)',
        'CREATE INDEX IF NOT EXISTS idx_resource_categories_resource ON resource_categories(resource_id)',
        'CREATE INDEX IF NOT EXISTS idx_resource_categories_category ON resource_categories(category_id)',
        'CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)',
        'CREATE INDEX IF NOT EXISTS idx_favorites_resource ON favorites(resource_id)',
        'CREATE INDEX IF NOT EXISTS idx_comments_resource ON comments(resource_id)',
        'CREATE INDEX IF NOT EXISTS idx_comments_user ON comments(user_id)',
        'CREATE INDEX IF NOT EXISTS idx_resource_tags_resource ON resource_tags(resource_id)',
        'CREATE INDEX IF NOT EXISTS idx_resource_tags_tag ON resource_tags(tag_id)',
        'CREATE INDEX IF NOT EXISTS idx_resource_versions_resource ON resource_versions(resource_id)',
    ]:
        try:
            cursor.execute(idx_sql)
        except Exception:
            pass

    # Full-text search with FTS5
    try:
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS resources_fts USING fts5(
                title, description, original_filename,
                content=resources,
                content_rowid=id,
                tokenize='unicode61'
            )
        ''')
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS resources_fts_ai AFTER INSERT ON resources BEGIN
                INSERT INTO resources_fts(rowid, title, description, original_filename)
                VALUES (new.id, new.title, new.description, new.original_filename);
            END
        ''')
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS resources_fts_ad AFTER DELETE ON resources BEGIN
                INSERT INTO resources_fts(resources_fts, rowid, title, description, original_filename)
                VALUES ('delete', old.id, old.title, old.description, old.original_filename);
            END
        ''')
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS resources_fts_au AFTER UPDATE ON resources BEGIN
                INSERT INTO resources_fts(resources_fts, rowid, title, description, original_filename)
                VALUES ('delete', old.id, old.title, old.description, old.original_filename);
                INSERT INTO resources_fts(rowid, title, description, original_filename)
                VALUES (new.id, new.title, new.description, new.original_filename);
            END
        ''')
        cursor.execute("INSERT INTO resources_fts(resources_fts) VALUES('rebuild')")
    except Exception:
        pass  # FTS5 not available, fall back to LIKE

    # New tables: comments, tags, versions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            rating INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (resource_id) REFERENCES resources (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resource_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            FOREIGN KEY (resource_id) REFERENCES resources (id),
            FOREIGN KEY (tag_id) REFERENCES tags (id),
            UNIQUE(resource_id, tag_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resource_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            file_size INTEGER,
            user_id INTEGER,
            version_number INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (resource_id) REFERENCES resources (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Migration: add role and status columns if missing
    for col_sql in [
        "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'",
        "ALTER TABLE resources ADD COLUMN status TEXT DEFAULT 'approved'",
    ]:
        try:
            cursor.execute(col_sql)
        except Exception:
            pass

    db.commit()
    db.close()


def resource_cats(resource_id):
    db = get_db()
    rows = db.execute('''
        SELECT c.id, c.name, c.taxonomy_id, t.name as taxonomy_name, t.slug as taxonomy_slug
        FROM resource_categories rc
        JOIN categories c ON rc.category_id = c.id
        JOIN taxonomies t ON c.taxonomy_id = t.id
        WHERE rc.resource_id = ?
        ORDER BY t.id, c.name
    ''', (resource_id,)).fetchall()
    grouped = {}
    for r in rows:
        key = r['taxonomy_slug']
        if key not in grouped:
            grouped[key] = {'name': r['taxonomy_name'], 'slug': key, 'terms': []}
        grouped[key]['terms'].append(r)
    return grouped


def taxonomies_with_terms(db=None):
    if db is None:
        db = get_db()
    rows = db.execute('''
        SELECT t.*, c.id as cat_id, c.name as cat_name, c.description as cat_desc, c.icon as cat_icon,
               (SELECT COUNT(*) FROM resource_categories rc WHERE rc.category_id = c.id) as resource_count
        FROM taxonomies t
        LEFT JOIN categories c ON c.taxonomy_id = t.id
        ORDER BY t.id, c.id
    ''').fetchall()
    grouped = {}
    for r in rows:
        tid = r['id']
        if tid not in grouped:
            grouped[tid] = {'id': tid, 'name': r['name'], 'slug': r['slug'], 'description': r['description'], 'categories': []}
        if r['cat_id']:
            grouped[tid]['categories'].append({'id': r['cat_id'], 'name': r['cat_name'], 'description': r['cat_desc'], 'icon': r['cat_icon'], 'resource_count': r['resource_count']})
    return list(grouped.values())


def search_resources_fts(q, file_type='', sort='created_at', page=1, per_page=12, db=None):
    if db is None:
        db = get_db()
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

    # Sanitize and build FTS5 query: escape special chars, OR each term with prefix
    import re
    fts_chars = re.compile(r'[^\w\s\u4e00-\u9fff]')
    terms = [fts_chars.sub('', t.strip()) for t in q.split() if t.strip()]
    if not terms:
        return [], 0
    fts_query = ' OR '.join(t + '*' for t in terms)

    params = [fts_query]
    where_extra = ''
    if file_type:
        where_extra = ' AND r.file_type = ?'
        params.append(file_type)

    rows = db.execute(f'''
        SELECT r.*, c.name as category_name
        FROM resources_fts fts
        JOIN resources r ON r.id = fts.rowid
        LEFT JOIN categories c ON r.category_id = c.id
        WHERE resources_fts MATCH ?
        {where_extra}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    ''', params + [per_page, offset]).fetchall()

    count_params = [fts_query]
    if file_type:
        count_params.append(file_type)
    total = db.execute(f'''
        SELECT COUNT(*) as total
        FROM resources_fts fts
        JOIN resources r ON r.id = fts.rowid
        WHERE resources_fts MATCH ?
        {where_extra}
    ''', count_params).fetchone()['total']

    return rows, total
