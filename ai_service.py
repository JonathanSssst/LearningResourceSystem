import os, time, json, logging
from volcenginesdkarkruntime import Ark
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger('lrs')

ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
ARK_BASE = os.environ.get("ARK_BASE", "https://ark.cn-beijing.volces.com/api/v3")
ARK_MODEL = os.environ.get("ARK_MODEL", "doubao-seed-2-1-turbo-260628")
ARK_MODEL_LIGHT = os.environ.get("ARK_MODEL_LIGHT", ARK_MODEL)


def _strip_markdown(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n", 1)
        text = lines[1] if len(lines) > 1 else text[3:]
        text = text.rsplit("```", 1)[0].strip()
    return text


def _call_llm_json(system_prompt: str, user_prompt: str, model: str = None) -> dict:
    client = Ark(
        base_url=ARK_BASE,
        api_key=ARK_API_KEY,
    )
    completion = client.chat.completions.create(
        model=model or ARK_MODEL_LIGHT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        timeout=120,
    )
    raw = completion.choices[0].message.content
    return json.loads(_strip_markdown(raw))


def _upload_and_poll(file_path: str, preprocess: dict = None) -> object:
    client = Ark(base_url=ARK_BASE, api_key=ARK_API_KEY)
    with open(file_path, "rb") as fh:
        kwargs = {"file": fh, "purpose": "user_data"}
        if preprocess:
            kwargs["preprocess_configs"] = preprocess
        f = client.files.create(**kwargs)
    logger.info('文件上传中 file_id=%s', f.id)
    
    while f.status == "processing":
        time.sleep(2)
        f = client.files.retrieve(f.id)
    if f.status == "failed":
        raise Exception("文件解析失败")
    return f


def analyze_file(filepath: str, filename: str, config: dict, categories_info: str, learning_stage: str) -> dict:
    ft = _guess_file_type(filename)
    ext = os.path.splitext(filepath)[1].lower()

    prompt = f"""你是一个学习资源管理系统的 AI 助手。请分析文件内容，返回 JSON（不要 markdown 包裹）：

{{"title": "资源标题（简洁准确）",
"description": "资源描述（2-3句话概括内容）",
"file_type": "文件类型（pdf|doc|image|video|audio|code|archive|text|spreadsheet）",
"category_suggestions": {{
    "file_type": "最匹配的文件类型分类",
    "subject": "最匹配的学科分类",
    "difficulty": "根据用户学习阶段（{learning_stage}）匹配的难度等级"
}}}}

文件名：{filename}

系统现有分类维度（请从中选取最合适的分类名称）：
{categories_info}

用户当前学习阶段：{learning_stage}"""

    client = Ark(base_url=ARK_BASE, api_key=ARK_API_KEY)
    content = []
    video_audio = False

    if ext == '.pdf':
        file = _upload_and_poll(filepath)
        content.append({"type": "input_file", "file_id": file.id})
    elif ext in ('.txt',):
        with open(filepath, "r", encoding="utf-8") as fh:
            content.append(fh.read())
    elif ext in ('.mp4', '.avi', '.mov'):
        file = _upload_and_poll(filepath, {"video": {"fps": 0.3}})
        content.append({"type": "input_video", "file_id": file.id})
        video_audio = True
    elif ext in ('.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a'):
        file = _upload_and_poll(filepath)
        content.append({"type": "input_audio", "file_id": file.id})
        video_audio = True
    else:
        title = os.path.splitext(filename)[0]
        return {"title": title, "description": "", "file_type": ft, "category_suggestions": {}}

    content.append({"type": "input_text", "text": prompt})
    try:
        resp = client.responses.create(
            model=ARK_MODEL,
            input=[
                {"role": "system", "content": "你是一个学习资源管理系统的 AI 助手。"},
                {"role": "user", "content": content},
            ],
        )
        text = next(item.content[0].text for item in resp.output if hasattr(item, 'content') and item.content)
        return json.loads(_strip_markdown(text))
    except Exception as e:
        logger.warning('AI analysis failed for %s: %s', ext, e)
        if video_audio:
            logger.info('Video/audio analysis not supported by Ark API, using filename fallback')
        title = os.path.splitext(filename)[0]
        return {"title": title, "description": "", "file_type": ft, "category_suggestions": {}}


def _guess_file_type(filename: str) -> str:
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    type_map = {
        'pdf': 'pdf', 'doc': 'doc', 'docx': 'doc', 'txt': 'text',
        'png': 'image', 'jpg': 'image', 'jpeg': 'image', 'gif': 'image', 'webp': 'image',
        'mp4': 'video', 'avi': 'video', 'mov': 'video', 'mkv': 'video', 'wmv': 'video', 'webm': 'video',
        'mp3': 'audio', 'wav': 'audio', 'flac': 'audio', 'aac': 'audio', 'ogg': 'audio', 'wma': 'audio', 'm4a': 'audio',
        'zip': 'archive', 'rar': 'archive', '7z': 'archive',
        'py': 'code', 'java': 'code', 'cpp': 'code', 'c': 'code', 'js': 'code', 'html': 'code', 'css': 'code',
        'ts': 'code', 'tsx': 'code', 'jsx': 'code', 'go': 'code', 'rs': 'code', 'rb': 'code', 'php': 'code',
        'xls': 'spreadsheet', 'xlsx': 'spreadsheet',
        'ppt': 'presentation', 'pptx': 'presentation'
    }
    return type_map.get(ext, 'other')


def suggest_related(title: str, description: str, all_resources: list, config: dict = None) -> list:
    lines = []
    for r in all_resources:
        lines.append(
            f'[ID {r["id"]}] 标题：{r["title"]}　类型：{r.get("file_type","")}　'
            f'大小：{r.get("file_size","")}　上传时间：{r.get("created_at","")}　'
            f'描述：{r.get("description","")[:60]}'
        )
    resource_list = "\n".join(lines)

    prompt = f"""当前资源信息：
标题：{title}
描述：{description}

其他所有资源列表：
{resource_list}

请从以上资源中至多选出最相关的 3 个（可以不足 3 个），按相关度从高到低排列。返回 JSON（不要 markdown 包裹）：
{{"related_ids": [id1, id2, id3]}}"""

    try:
        result = _call_llm_json(
            "你是一个学习资源管理系统的 AI 助手，负责推荐最相关的学习资源。",
            prompt,
            model=ARK_MODEL_LIGHT
        )
        ids = result.get("related_ids", [])
        return [i for i in ids if any(r["id"] == i for r in all_resources)][:3]
    except Exception as e:
        logger.warning('suggest_related 调用失败: %s', e)
        return []
