# 学习资源管理系统 (Learning Resource System — LRS)

基于 Flask 的多维度分类学习资源管理平台，支持 AI 智能分析、批量上传、数据看板。

## 功能特性

### 核心功能
- **资源上传** — 单文件 / 批量上传，支持 10+ 种文件格式，单文件最大 100MB
- **资源下载 / 预览** — 带下载统计，图片/文本/代码/视频/音频/PDF 在线预览
- **多维度分类** — 文件类型、学科、难度等级三维独立分类体系，交叉筛选
- **收藏系统** — 个人收藏夹，支持批量取消收藏
- **全文搜索** — 按标题、描述、原始文件名搜索
- **批量操作** — 资源列表批量选择删除，收藏批量取消

### AI 能力
- **智能分析** — 上传时自动分析内容，提取标题、描述、推荐分类（PDF/TXT）
- **关联推荐** — 资源详情页异步加载 AI 推荐的相关资源（基于标题和描述语义匹配）

### 数据看板
- 6 项 KPI 统计卡片
- 分类分布饼图（Canvas 绘制，hover 展开动画 + 折叠图例）
- 文件类型分布饼图
- 近 30 天上传趋势柱状图（hover 高亮过渡动画）
- 下载 TOP10、浏览 TOP5、收藏 TOP5 排行

### 用户系统
- 注册 / 登录 / 登出
- 学习阶段体系：小学→一年级\~六年级、初中→初一\~初三、高中→高一\~高三、大学→大一\~大四、硕博
- 时区配置（UTC-12 ~ UTC+12，默认 +08:00）

## 技术栈

| 层 | 技术 |
|------|------|
| 后端框架 | Flask 2.x |
| 数据库 | SQLite3 |
| 模板引擎 | Jinja2 |
| 前端 | 原生 HTML + CSS + JavaScript |
| AI | Volcengine Ark SDK（Doubao 模型）+ DeepSeek |
| 图标 | Remixicon（本地托管） |
| 文件存储 | 本地文件系统 |

## 项目结构

```
LRS/
├── app.py                  # 应用入口
├── ai_service.py           # AI 分析 + 关联推荐
├── db.py                   # 数据库连接 / 初始化 / 迁移
├── helpers.py              # 装饰器、文件类型、时间转换
├── .env                    # 环境变量（ARK_API_KEY 等）
│
├── routes/
│   ├── auth.py             # 登录/注册/登出/个人资料
│   ├── home.py             # 首页 / 数据看板
│   ├── resources.py        # 资源 CRUD / 批量 / 收藏 / 预览
│   ├── categories.py       # 分类管理
│   └── api.py              # 统计数据 API
│
├── templates/
│   ├── base.html           # 主布局（顶栏、导航、页脚）
│   ├── login.html / register.html / profile.html
│   ├── home.html / dashboard.html
│   ├── resource.html / resource_all.html
│   ├── resource_detail.html / resource_preview.html
│   ├── resource_latests.html / resource_ranks.html
│   ├── resource_upload.html（单文件/批量上传）
│   └── favorites.html / search.html / categories.html
│
├── static/
│   ├── css/style.css / remixicon.css
│   ├── fonts/remixicon.*（本地字体文件）
│   └── js/main.js / upload-ai.js
│
├── logs/                   # 保存的日志文件
└── uploads/                # 上传文件存储目录（自动创建）
```

## 快速开始

### 环境要求
- Python 3.9+
- pip

### 安装

```bash
git clone <repo-url>
cd LRS
pip install flask python-dotenv volcenginesdkarkruntime
```

### 配置

复制 `.env` 文件并填写 AI API 密钥：

```bash
ARK_API_KEY=your_ark_api_key_here
ARK_MODEL=doubao-seed-evolution-model
ARK_MODEL_LIGHT=deepseek-v4-flash-model
ARK_BASE=https://ark.cn-beijing.volces.com/api/v3
```

### 启动

```bash
python app.py
```

首次运行自动创建 SQLite 数据库、初始化分类维度、创建管理员账号。服务默认监听 `http://0.0.0.0:5000`。

## 路由一览

### 页面路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 自动跳转首页或登录 |
| `/login` | GET/POST | 登录 |
| `/register` | GET/POST | 注册 |
| `/logout` | GET | 登出 |
| `/profile` | GET/POST | 个人资料（学习阶段、时区） |
| `/home` | GET | 首页概览 |
| `/resource` | GET | 资源管理主页 |
| `/resource/all` | GET | 全部资源（分页 + 多维筛选） |
| `/resource/detail?id=` | GET | 资源详情 |
| `/resource/upload` | GET/POST | 上传资源 |
| `/resource/batch-upload` | POST | 批量上传 API |
| `/resource/download/<code>` | GET | 下载资源 |
| `/resource/delete/<code>` | POST | 删除资源 |
| `/resource/all/batch-delete` | POST | 批量删除 |
| `/resource/move/<code>` | POST | 移动分类 |
| `/resource/favorite/<code>` | POST | 收藏/取消收藏 |
| `/resource/preview/<code>` | GET | 在线预览 |
| `/resource/analyze` | POST | AI 智能分析 |
| `/resource/suggest-related/<code>` | GET | AI 关联推荐 |
| `/resource/latests` | GET | 最新上传 |
| `/resource/ranks` | GET | 排行榜 |
| `/search?q=` | GET | 搜索 |
| `/favorites` | GET | 收藏夹 |
| `/favorites/batch-delete` | POST | 批量取消收藏 |
| `/categories` | GET | 分类管理 |
| `/dashboard` | GET | 数据看板 |
| `/api/stats` | GET | 统计数据 JSON |
| `/uploads/<filename>` | GET | 静态文件服务 |

## 数据库设计

### users
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| username | TEXT UNIQUE | 用户名 |
| password | TEXT | 密码 |
| email | TEXT | 邮箱 |
| learning_stage | TEXT | 学习阶段（默认 高中/高一） |
| timezone | TEXT | 时区偏移（默认 +08:00） |
| created_at | TIMESTAMP | 注册时间 |

### taxonomies
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT | 维度名称 |
| slug | TEXT UNIQUE | 标识符 |
| description | TEXT | 描述 |

### categories
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT | 名称 |
| taxonomy_id | INTEGER FK | 所属维度 |
| description / icon | TEXT | 描述/图标 |

### resources
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键（内部用） |
| code | TEXT UNIQUE | 6 位字母数字标识（公开 URL 用） |
| title / description | TEXT | 标题/描述 |
| filename / original_filename | TEXT | 存储名/原始名 |
| file_type | TEXT | 文件类型 |
| file_size | INTEGER | 字节数 |
| downloads / views | INTEGER | 统计 |
| user_id | INTEGER FK | 上传者 |
| created_at | TIMESTAMP | 上传时间 |

### resource_categories（多对多）
| 字段 | 说明 |
|------|------|
| resource_id + category_id | UNIQUE(resource_id, category_id) |

### favorites
| 字段 | 说明 |
|------|------|
| user_id + resource_id | UNIQUE(user_id, resource_id) |

## 默认账号

- **用户名**: `admin`
- **密码**: `admin123`
- **学习阶段**: 高中/高一

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ARK_API_KEY` | — | Volcengine Ark API 密钥 |
| `ARK_MODEL` | — | 主力模型（文件分析、上传 AI） |
| `ARK_MODEL_LIGHT` | =ARK_MODEL | 轻量模型（关联推荐） |
| `ARK_BASE` | `https://ark.cn-beijing.volces.com/api/v3` | API 地址 |

## 支持的文件类型

文档：`txt pdf doc docx`
表格：`xls xlsx`
演示：`ppt pptx`
图片：`png jpg jpeg gif`
视频：`mp4 avi mov`
音频：`mp3 wav`
压缩：`zip rar 7z`
代码：`py java cpp c js html css`

## 注意事项

1. **AI 限制** — Volcengine Ark API `responses.create` 不支持 `input_video` / `input_audio` 内容类型，视频和音频文件始终以文件名作为标题
2. **文件编码** — 使用 `secure_filename` 生成存储名，原始文件名保留为 `original_filename` 字段
3. **时间存储** — 数据库统一存储 UTC 时间，显示时根据用户时区转换
4. **SQLite** — 不适用高并发场景，生产环境建议迁移至 PostgreSQL
5. **密码** — 当前使用明文存储，生产环境请改为哈希加密
