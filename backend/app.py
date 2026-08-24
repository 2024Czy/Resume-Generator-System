from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .generator import generate_resume
from .llm_parser import parse_text_hybrid
from .models import GenerateRequest, TextParseRequest
from .ollama_client import OllamaClient
from .parser import parse_resume
from .text_parser import parse_text_resume
from .word_reader import read_word


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = Path(os.environ.get("RESUME_TEMPLATE_PATH", ROOT / "templates" / "resume-template-public.docm"))
FRONTEND_DIST = ROOT / "frontend" / "dist"

app = FastAPI(title="简历工坊 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "template": str(TEMPLATE_PATH), "template_exists": TEMPLATE_PATH.exists()}


@app.get("/api/template-profile")
def template_profile() -> dict:
    return {
        "name": "v7.3-27届表格版简历模板",
        "format": "DOCM source / DOCX default output",
        "page_size": "A4",
        "page_count_reference": 3,
        "table_count": 1,
        "grid_columns": 5,
        "prototype_rows": 15,
        "dynamic_sections": ["教育背景", "项目经历", "实习经历", "专业技能"],
        "normalizations": ["教育行改用固定制表位", "实习标题行统一为三等分", "经历条目按内容动态克隆", "缺失照片使用空白占位"],
    }


@app.get("/api/ai-status")
def ai_status() -> dict:
    return OllamaClient().status()


@app.post("/api/parse")
async def parse(file: UploadFile = File(...)) -> dict:
    if Path(file.filename or "").name.startswith("~$"):
        raise HTTPException(status_code=400, detail="不能上传 Word 临时锁定文件（~$ 开头），请关闭文档后选择原文件。")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".docx", ".docm"}:
        raise HTTPException(status_code=400, detail="目前支持 .docx 和 .docm 文件。")
    payload = await file.read()
    if len(payload) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件不能超过 20 MB。")
    try:
        snapshot = read_word(payload)
        result = parse_resume(snapshot, file.filename or "resume")
        return result.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"无法解析该 Word 文件：{exc}") from exc


@app.post("/api/parse-text")
def parse_text(request: TextParseRequest) -> dict:
    try:
        result = (
            parse_text_resume(request.text)
            if request.engine == "rules"
            else parse_text_hybrid(request.text)
        )
        return result.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"无法解析这段文本：{exc}") from exc


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "-", name).strip(" .-")
    return cleaned or "新简历"


@app.post("/api/generate")
def generate(request: GenerateRequest, background_tasks: BackgroundTasks) -> FileResponse:
    if not TEMPLATE_PATH.exists():
        raise HTTPException(status_code=500, detail=f"模板不存在：{TEMPLATE_PATH}")
    suffix = ".docm" if request.output_format.lower() == "docm" else ".docx"
    temp_dir = Path(tempfile.mkdtemp(prefix="resume-workshop-"))
    filename = _safe_filename(request.resume.personal.name) + "-格式化简历" + suffix
    output = temp_dir / filename
    try:
        generate_resume(TEMPLATE_PATH, request.resume, output)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"生成失败：{exc}") from exc
    background_tasks.add_task(lambda: output.unlink(missing_ok=True))
    background_tasks.add_task(lambda: temp_dir.rmdir() if temp_dir.exists() else None)
    media_type = "application/vnd.ms-word.document.macroEnabled.12" if suffix == ".docm" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(output, filename=filename, media_type=media_type, background=background_tasks)


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
