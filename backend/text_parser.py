from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Callable, TypeVar

from .models import EducationItem, ExperienceItem, Highlight, ResumeData, SkillItem
from .parser import ENTRY_DATE_RE, PERIOD_RE, parse_resume
from .word_reader import ParagraphUnit, WordSnapshot


BULLET_RE = re.compile(r"^\s*(?:[•●▪■◆◇◦○·]|[-*])\s*")
SECTION_LINE_RE = re.compile(
    r"^(?:基本信息|个人信息|教育背景|教育经历|项目经历|项目经验|实习经历|工作经历|"
    r"专业技能|技能特长|荣誉奖项|获奖经历|自我评价)\s*[:：]?$"
)
SCHOOL_RE = re.compile(r"[\u4e00-\u9fffA-Za-z·（）()]{2,32}(?:大学|学院)")
DEGREE_RE = re.compile(r"博士研究生|硕士研究生|本科|博士|硕士|学士|MBA|大专|专科")
COMPANY_SUFFIX = r"公司|集团|研究院|事务所|工作室|中心|实验室|银行|医院|学校"
ROLE_RE = re.compile(
    r"(?:担任|作为|职位(?:是|为)?|任职为?)\s*([^，,。；;]{2,24}?(?:实习生|工程师|分析师|"
    r"经理|助理|负责人|开发|产品|运营|设计师|研究员))(?=[，,。；;]|$)"
)
ACTION_RE = re.compile(r"^(?:主要)?(?:负责|参与|完成|开发|设计|搭建|优化|实现|协助|主导|推进|维护|撰写|组织)")
RESULT_RE = re.compile(
    r"(?:提升|提高|降低|减少|增长|增加|达到|缩短|节省|优化).{0,28}?\d+(?:\.\d+)?\s*(?:%|个|倍|万|小时|天|秒|ms)?",
    re.I,
)
PROJECT_ENDING = r"(?:系统|平台|产品|模型|工具)(?:项目)?|项目"
PROJECT_NAME_RE = re.compile(rf"([^，,。；;]{{2,36}}?(?:{PROJECT_ENDING}))")
SKILL_TRIGGER_RE = re.compile(r"(?:熟悉|掌握|擅长|技能|技术栈|会使用)")
TEXT_DATE = r"(?:19|20)\d{2}(?:(?:[./-]\d{1,2})|(?:年(?:\d{1,2}月)?))?"
TEXT_PERIOD_RE = re.compile(rf"({TEXT_DATE}\s*(?:[-–—~至到]+\s*(?:{TEXT_DATE}|至今|现在|今)))")
T = TypeVar("T")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n|；;")


def _line_units(text: str) -> list[ParagraphUnit]:
    units: list[ParagraphUnit] = []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        is_bullet = BULLET_RE.match(line) is not None
        clean_line = BULLET_RE.sub("", line, count=1).strip() if is_bullet else line
        if clean_line:
            units.append(ParagraphUnit(text=clean_line, is_bullet=is_bullet))
    return units


def _semantic_chunks(text: str, units: Iterable[ParagraphUnit]) -> list[str]:
    candidates = [
        unit.text
        for unit in units
        if not SECTION_LINE_RE.match(_clean(unit.text))
        and not (len(unit.text) > 80 and len(re.findall(r"[。！？!?]", unit.text)) > 1)
    ]
    candidates.extend(
        part.strip()
        for part in re.split(r"(?<=[。！？!?])\s*", text.replace("\r", "\n"))
        if part.strip() and "\n" not in part.strip()
    )
    seen: set[str] = set()
    chunks: list[str] = []
    for candidate in candidates:
        clean = _clean(candidate)
        if clean and clean not in seen:
            seen.add(clean)
            chunks.append(clean)
    return chunks


def _period(text: str) -> str:
    text_range = TEXT_PERIOD_RE.search(text)
    if text_range:
        return _clean(text_range.group(1))
    range_match = PERIOD_RE.search(text)
    if range_match:
        return _clean(range_match.group(1))
    date_match = ENTRY_DATE_RE.search(text)
    return _clean(date_match.group(1)) if date_match else ""


def _source_for(chunks: list[str], value: str) -> str:
    if not value:
        return ""
    normalized = _clean(value)
    for chunk in chunks:
        if normalized in _clean(chunk):
            return chunk[:240]
    return ""


def _school(text: str) -> str:
    explicit = re.search(r"(?:就读于|毕业于|考入|进入)\s*([^，,。；;]{2,32}?(?:大学|学院))", text)
    if explicit:
        return _clean(explicit.group(1))
    match = SCHOOL_RE.search(text)
    if not match:
        return ""
    candidate = match.group(0)
    return _clean(re.sub(r"^.*?(?:在|于)", "", candidate))


def _major(text: str, school: str) -> str:
    tail = text.split(school, 1)[-1] if school and school in text else text
    match = re.search(
        r"(?:就读|学习|攻读)?\s*([\u4e00-\u9fffA-Za-z0-9+·（）()\-]{2,30}?)\s*专业",
        tail,
    )
    return _clean(match.group(1)) if match else ""


def _organization(text: str) -> str:
    explicit = re.search(rf"(?:在|就职于|任职于)\s*([^，,。；;]{{2,40}}?(?:{COMPANY_SUFFIX}))", text)
    if explicit:
        return _clean(explicit.group(1))
    short = re.search(r"(?:在|就职于|任职于)\s*([^，,。；;]{2,24}?)(?:实习|工作|任职)", text)
    if short:
        return _clean(short.group(1))
    fallback = re.search(rf"([^，,。；;]{{2,40}}?(?:{COMPANY_SUFFIX}))", text)
    return _clean(fallback.group(1)) if fallback else ""


def _project_name(text: str) -> str:
    explicit = re.search(
        rf"(?:参与|负责|完成|开发|搭建|设计|做过|项目(?:名称)?[:：])\s*"
        rf"([^，,。；;]{{2,36}}?(?:{PROJECT_ENDING}))",
        text,
    )
    match = explicit or PROJECT_NAME_RE.search(text)
    if not match:
        return ""
    value = _clean(match.group(1))
    return re.sub(r"^(?:过|了|一个|一项)", "", value).strip()


def _technologies(text: str) -> str:
    match = re.search(r"(?:技术栈\s*[:：]?|使用|基于)\s*([^。；;]{2,100})", text, re.I)
    if not match:
        return ""
    value = re.split(r"(?:，|,)(?=(?:负责|参与|完成|开发|设计|优化|实现))", match.group(1), maxsplit=1)[0]
    return _clean(value)


def _details(text: str) -> tuple[list[Highlight], list[str]]:
    highlights: list[Highlight] = []
    results: list[str] = []
    for clause in re.split(r"[。；;]|(?<!\d)[，,](?!\d)", text):
        clean = _clean(clause)
        if not clean:
            continue
        if RESULT_RE.search(clean):
            results.append(clean)
        elif ACTION_RE.match(clean):
            highlights.append(Highlight(label="主要工作", content=clean))
    return highlights[:8], results[:5]


def _infer_education(chunks: list[str]) -> list[tuple[EducationItem, str]]:
    inferred: list[tuple[EducationItem, str]] = []
    seen: set[tuple[str, str]] = set()
    for chunk in chunks:
        school = _school(chunk)
        if not school or not (DEGREE_RE.search(chunk) or re.search(r"就读|毕业|专业|学历", chunk)):
            continue
        item = EducationItem(
            period=_period(chunk),
            school=school,
            major=_major(chunk, school),
            degree=DEGREE_RE.search(chunk).group(0) if DEGREE_RE.search(chunk) else "",
        )
        key = (item.period, item.school)
        if key not in seen:
            seen.add(key)
            inferred.append((item, chunk))
    return inferred


def _infer_internships(chunks: list[str]) -> list[tuple[ExperienceItem, str]]:
    inferred: list[tuple[ExperienceItem, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for chunk in chunks:
        if not re.search(r"实习|工作|任职|就职", chunk):
            continue
        organization = _organization(chunk)
        if not organization:
            continue
        role_match = ROLE_RE.search(chunk)
        role = _clean(role_match.group(1)) if role_match else ""
        if not role:
            fallback_role = re.search(r"([^，,。；;]{2,18}?(?:实习生|工程师|分析师|经理|助理|负责人|设计师|研究员))(?=[，,。；;]|$)", chunk)
            role = _clean(fallback_role.group(1)) if fallback_role else ""
        highlights, results = _details(chunk)
        item = ExperienceItem(
            period=_period(chunk),
            organization=organization,
            role=role,
            name=_project_name(chunk),
            technologies=_technologies(chunk),
            highlights=highlights,
            results=results,
        )
        key = (item.period, item.organization, item.role)
        if key not in seen:
            seen.add(key)
            inferred.append((item, chunk))
    return inferred


def _infer_projects(chunks: list[str], internships: list[ExperienceItem]) -> list[tuple[ExperienceItem, str]]:
    inferred: list[tuple[ExperienceItem, str]] = []
    internship_names = {item.name for item in internships if item.name}
    seen: set[str] = set()
    for chunk in chunks:
        name = _project_name(chunk)
        if not name or name in internship_names or name in seen:
            continue
        if re.search(r"实习|工作|任职|就职", chunk) and _organization(chunk):
            continue
        highlights, results = _details(chunk)
        role_match = re.search(r"(?:担任|作为)\s*([^，,。；;]{2,16}?(?:负责人|成员|队长|开发|设计))", chunk)
        item = ExperienceItem(
            period=_period(chunk),
            role=_clean(role_match.group(1)) if role_match else "",
            name=name,
            technologies=_technologies(chunk),
            highlights=highlights,
            results=results,
        )
        seen.add(name)
        inferred.append((item, chunk))
    return inferred


def _infer_skills(chunks: list[str]) -> list[tuple[SkillItem, str]]:
    inferred: list[tuple[SkillItem, str]] = []
    for chunk in chunks:
        if not SKILL_TRIGGER_RE.search(chunk) or re.search(r"实习|工作|任职", chunk):
            continue
        description = re.sub(r"^(?:专业)?技能\s*[:：]\s*", "", chunk).strip()
        inferred.append((SkillItem(category="专业技能", description=description), chunk))
    return inferred[:6]


def _append_unique(existing: list[T], incoming: Iterable[T], key: Callable[[T], object]) -> list[T]:
    values = list(existing)
    seen = {key(item) for item in values}
    for item in incoming:
        item_key = key(item)
        if item_key not in seen:
            values.append(item)
            seen.add(item_key)
    return values


def parse_text_resume(text: str) -> ResumeData:
    clean_text = text.strip()
    units = _line_units(clean_text)
    snapshot = WordSnapshot(text_boxes=[], body_paragraphs=units, table_rows=[], reading_units=units)
    result = parse_resume(snapshot, "", enforce_quality_gate=False)
    chunks = _semantic_chunks(clean_text, units)

    name_match = re.search(r"(?:我叫|姓名\s*[:：]|名字是)\s*([\u4e00-\u9fff·]{2,4})(?=[，,。；;\s]|$)", clean_text)
    if name_match:
        result.personal.name = name_match.group(1)
    elif result.personal.name and re.search(r"项目|系统|平台|工具|模型|经历|背景|技能", result.personal.name):
        result.personal.name = ""

    inferred_education = _infer_education(chunks)
    inferred_internships = _infer_internships(chunks)
    result.education = _append_unique(
        result.education,
        (item for item, _ in inferred_education),
        lambda item: (item.period, item.school),
    )
    result.internships = _append_unique(
        result.internships,
        (item for item, _ in inferred_internships),
        lambda item: (item.period, item.organization, item.role),
    )
    inferred_projects = _infer_projects(chunks, result.internships)
    result.projects = _append_unique(
        result.projects,
        (item for item, _ in inferred_projects),
        lambda item: (item.period, item.name, item.organization),
    )
    inferred_skills = _infer_skills(chunks)
    result.skills = _append_unique(
        result.skills,
        (item for item, _ in inferred_skills),
        lambda item: (item.category, item.description),
    )

    sources: dict[str, dict[str, object]] = {}

    def add_source(path: str, label: str, value: str, confidence: float, source: str = "") -> None:
        snippet = source or _source_for(chunks, value)
        if value and snippet:
            sources[path] = {"标签": label, "原文": snippet, "置信度": confidence}

    for key, label in (("name", "姓名"), ("phone", "手机"), ("email", "邮箱"), ("birth_date", "出生年月"), ("location", "现居地"), ("job_status", "求职状态")):
        add_source(f"personal.{key}", label, str(getattr(result.personal, key) or ""), 0.95)
    for index, item in enumerate(result.education):
        source = next((chunk for inferred, chunk in inferred_education if inferred.school == item.school and inferred.period == item.period), "")
        add_source(f"education.{index}", f"教育经历 {index + 1}", item.school, 0.76 if source else 0.88, source)
    for index, item in enumerate(result.projects):
        source = next((chunk for inferred, chunk in inferred_projects if inferred.name == item.name), "")
        add_source(f"projects.{index}", f"项目经历 {index + 1}", item.name, 0.68 if source else 0.84, source)
    for index, item in enumerate(result.internships):
        source = next((chunk for inferred, chunk in inferred_internships if inferred.organization == item.organization and inferred.period == item.period), "")
        add_source(f"internships.{index}", f"实习/工作经历 {index + 1}", item.organization, 0.7 if source else 0.84, source)
    for index, item in enumerate(result.skills):
        source = next((chunk for inferred, chunk in inferred_skills if inferred.description == item.description), "")
        add_source(f"skills.{index}", f"技能 {index + 1}", item.description, 0.72 if source else 0.84, source)

    low_confidence = [
        {"字段": path, **metadata}
        for path, metadata in sources.items()
        if float(metadata["置信度"]) < 0.75
    ]
    meaningful = bool(
        result.personal.name
        or result.personal.phone
        or result.personal.email
        or result.education
        or result.projects
        or result.internships
        or result.skills
    )
    result.warnings = []
    for label, value in (
        ("姓名", result.personal.name),
        ("手机或邮箱", result.personal.phone or result.personal.email),
        ("教育经历", result.education),
    ):
        if not value:
            result.warnings.append(f"未可靠识别{label}，请在生成前补充。")
    if not result.projects:
        result.warnings.append("未识别到项目经历；该模板允许省略此分节。")
    if not result.internships:
        result.warnings.append("未识别到实习/工作经历；该模板允许省略此分节。")
    if not result.skills:
        result.warnings.append("未识别到专业技能；建议至少补充一项。")
    if not meaningful:
        result.warnings.insert(0, "未从文本中可靠识别出简历信息，请补充姓名、教育或经历描述。")
    if low_confidence:
        result.warnings.append(f"有 {len(low_confidence)} 项内容由语义规则推断，请对照原文重点确认。")
    result.other["文本解析"] = {
        "来源类型": "plain_text",
        "解析引擎": "rules",
        "模型": "",
        "自动回退": False,
        "字符数": len(clean_text),
        "原始文本": clean_text,
        "字段来源": sources,
        "低置信字段": low_confidence,
    }
    result.source_filename = "粘贴文本"
    return result
