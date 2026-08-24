from __future__ import annotations

import re
from typing import Any

from .models import EducationItem, ExperienceItem, PersonalInfo, ResumeData, SkillItem
from .ollama_client import AIResumeExtraction, OllamaClient, OllamaError, OllamaResult
from .text_parser import parse_text_resume


def _normalized(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value or "").lower()


def _value_supported(value: str, source: str) -> bool:
    normalized = _normalized(value)
    normalized_source = _normalized(source)
    if not normalized:
        return False
    if normalized in normalized_source:
        return True
    tokens = [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9.+#-]*|\d+(?:\.\d+)?", value)]
    return bool(tokens) and all(_normalized(token) in normalized_source for token in tokens)


def _period_supported(value: str, source: str) -> bool:
    """Allow harmless date normalization such as 2025.03-2025.08."""
    if _value_supported(value, source):
        return True
    value_numbers = {int(part) for part in re.findall(r"\d+", value)}
    source_numbers = {int(part) for part in re.findall(r"\d+", source)}
    return bool(value_numbers) and value_numbers.issubset(source_numbers)


def _explicit_personal_facts(source: str) -> tuple[str, str]:
    role_match = re.search(
        r"(?:求职方向|目标岗位|意向岗位|应聘岗位)\s*(?:是|为|[:：])?\s*([^，。；;\n]{2,40})",
        source,
    )
    target_role = role_match.group(1).strip() if role_match else ""
    availability_match = re.search(
        r"((?:可|可以)?(?:立即|随时|\d+\s*(?:天|周|个月)后)?到岗(?:并)?(?:可|能)?(?:连续)?实习\s*\d+\s*(?:个)?月|"
        r"(?:可|能)(?:连续)?实习\s*\d+\s*(?:个)?月)",
        source,
    )
    availability = availability_match.group(1).strip() if availability_match else ""
    return target_role, availability


def _context_for(source: str, value: str) -> str:
    if not value:
        return ""
    pieces = [part.strip() for part in re.split(r"[\r\n]+|(?<=[。！？!?；;])", source) if part.strip()]
    for piece in pieces:
        if _value_supported(value, piece):
            return piece[:300]
    return ""


def _sanitize_personal(personal: PersonalInfo, source: str) -> tuple[PersonalInfo, list[str]]:
    data = personal.model_dump()
    rejected: list[str] = []
    for key, value in data.items():
        if value in {"", None}:
            continue
        if key == "age":
            if re.search(rf"(?:年龄|今年)\s*[:：]?\s*{value}\s*岁?", source):
                continue
        elif _value_supported(str(value), source):
            continue
        data[key] = None if key == "age" else ""
        rejected.append(f"personal.{key}")
    return PersonalInfo(**data), rejected


def _sanitize_education(items: list[EducationItem], source: str) -> tuple[list[EducationItem], list[str]]:
    accepted: list[EducationItem] = []
    rejected: list[str] = []
    for index, item in enumerate(items):
        if not item.school or not _value_supported(item.school, source):
            rejected.append(f"education.{index}")
            continue
        data = item.model_dump()
        for key in ("period", "major", "degree"):
            supported = _period_supported(data[key], source) if key == "period" else _value_supported(data[key], source)
            if data[key] and not supported:
                data[key] = ""
                rejected.append(f"education.{index}.{key}")
        accepted.append(EducationItem(**data))
    return accepted, rejected


def _sanitize_experiences(
    items: list[ExperienceItem],
    source: str,
    kind: str,
) -> tuple[list[ExperienceItem], list[str]]:
    accepted: list[ExperienceItem] = []
    rejected: list[str] = []
    for index, item in enumerate(items):
        anchor = item.organization if kind == "internships" else item.name or item.organization
        if not anchor or not _value_supported(anchor, source):
            rejected.append(f"{kind}.{index}")
            continue
        context = _context_for(source, anchor)
        if kind == "projects" and (
            re.search(r"(?:求职方向|目标岗位|意向岗位)", context)
            or (re.search(r"(?:熟悉|掌握|技能)", context) and not re.search(r"(?:项目|课题)", context))
        ):
            rejected.append(f"{kind}.{index}")
            continue
        data = item.model_dump()
        for key in ("period", "organization", "role", "name", "technologies", "background"):
            supported = _period_supported(data[key], source) if key == "period" else _value_supported(data[key], source)
            if data[key] and not supported:
                data[key] = ""
                rejected.append(f"{kind}.{index}.{key}")
        data["highlights"] = [
            highlight
            for highlight in item.highlights
            if highlight.content and _value_supported(highlight.content, source)
        ]
        data["results"] = [result for result in item.results if _value_supported(result, source)]
        accepted.append(ExperienceItem(**data))
    return accepted, rejected


def _sanitize_skills(items: list[SkillItem], source: str) -> tuple[list[SkillItem], list[str]]:
    accepted: list[SkillItem] = []
    rejected: list[str] = []
    for index, item in enumerate(items):
        if item.description and _value_supported(item.description, source):
            accepted.append(item)
        else:
            rejected.append(f"skills.{index}")
    return accepted, rejected


def _verified_evidence(extraction: AIResumeExtraction, source: str) -> tuple[dict[str, str], list[str]]:
    verified: dict[str, str] = {}
    rejected: list[str] = []
    for item in extraction.evidence:
        path = item.field_path.strip()
        quote = item.quote.strip()
        if path and quote and _value_supported(quote, source):
            verified[path] = quote[:300]
        elif path:
            rejected.append(path)
    return verified, rejected


def _first_supported(primary: str, fallback: str, source: str) -> str:
    if primary and _value_supported(primary, source):
        return primary
    return fallback


def _warnings_for(result: ResumeData) -> list[str]:
    warnings: list[str] = []
    for label, value in (
        ("姓名", result.personal.name),
        ("手机或邮箱", result.personal.phone or result.personal.email),
        ("教育经历", result.education),
    ):
        if not value:
            warnings.append(f"未可靠识别{label}，请在生成前补充。")
    if not result.projects:
        warnings.append("未识别到独立项目经历；该模板允许省略此分节。")
    if not result.internships:
        warnings.append("未识别到实习/工作经历；该模板允许省略此分节。")
    if not result.skills:
        warnings.append("未识别到专业技能；建议至少补充一项。")
    return warnings


def _build_sources(
    result: ResumeData,
    source: str,
    evidence: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    sources: dict[str, dict[str, Any]] = {}

    def add(path: str, label: str, value: str) -> None:
        quote = evidence.get(path, "") or _context_for(source, value)
        if not quote:
            return
        confidence = 0.92 if path in evidence else 0.79
        if path in {"personal.phone", "personal.email"}:
            confidence = 0.98
        sources[path] = {"标签": label, "原文": quote, "置信度": confidence}

    for key, label in (
        ("name", "姓名"),
        ("phone", "手机"),
        ("email", "邮箱"),
        ("birth_date", "出生年月"),
        ("location", "现居地"),
        ("job_status", "求职状态"),
        ("target_role", "目标岗位"),
        ("availability", "到岗与实习周期"),
    ):
        add(f"personal.{key}", label, str(getattr(result.personal, key) or ""))
    for collection, label, items in (
        ("education", "教育经历", result.education),
        ("projects", "项目经历", result.projects),
        ("internships", "实习/工作经历", result.internships),
        ("skills", "技能", result.skills),
    ):
        for index, item in enumerate(items):
            anchor = (
                item.school
                if collection == "education"
                else item.description
                if collection == "skills"
                else item.organization or item.name
            )
            add(f"{collection}.{index}", f"{label} {index + 1}", anchor)
    for index, award in enumerate(result.awards):
        add(f"awards.{index}", f"荣誉奖项 {index + 1}", award)
    add("summary", "个人简介", result.summary)
    add("self_evaluation", "自我评价", result.self_evaluation)
    low_confidence = [
        {"字段": path, **metadata}
        for path, metadata in sources.items()
        if float(metadata["置信度"]) < 0.8
    ]
    return sources, low_confidence


def _merge_ai_and_rules(
    source: str,
    rules: ResumeData,
    ollama: OllamaResult,
) -> ResumeData:
    extraction = ollama.extraction
    ai_personal, rejected = _sanitize_personal(extraction.personal, source)
    education, education_rejected = _sanitize_education(extraction.education, source)
    projects, project_rejected = _sanitize_experiences(extraction.projects, source, "projects")
    internships, internship_rejected = _sanitize_experiences(extraction.internships, source, "internships")
    skills, skill_rejected = _sanitize_skills(extraction.skills, source)
    rejected.extend(education_rejected + project_rejected + internship_rejected + skill_rejected)
    evidence, evidence_rejected = _verified_evidence(extraction, source)
    rejected.extend(evidence_rejected)

    rules_personal = rules.personal
    explicit_target_role, explicit_availability = _explicit_personal_facts(source)
    personal = PersonalInfo(
        name=_first_supported(ai_personal.name, rules_personal.name, source),
        age=rules_personal.age if rules_personal.age is not None else ai_personal.age,
        birth_date=rules_personal.birth_date or ai_personal.birth_date,
        phone=rules_personal.phone or ai_personal.phone,
        email=rules_personal.email or ai_personal.email,
        location=_first_supported(ai_personal.location, rules_personal.location, source),
        job_status=_first_supported(ai_personal.job_status, rules_personal.job_status, source),
        target_role=explicit_target_role or ai_personal.target_role,
        availability=explicit_availability or ai_personal.availability,
    )
    awards = [award for award in extraction.awards if _value_supported(award, source)]
    rule_projects, _ = _sanitize_experiences(rules.projects, source, "projects")
    rule_internships, _ = _sanitize_experiences(rules.internships, source, "internships")
    summary = extraction.summary if _value_supported(extraction.summary, source) else ""
    self_evaluation = (
        extraction.self_evaluation if _value_supported(extraction.self_evaluation, source) else ""
    )
    result = ResumeData(
        personal=personal,
        education=education or rules.education,
        projects=projects or rule_projects,
        internships=internships or rule_internships,
        skills=skills or rules.skills,
        awards=awards or rules.awards,
        summary=summary,
        self_evaluation=self_evaluation,
        source_filename="粘贴文本（qwen3:4b）",
    )
    sources, low_confidence = _build_sources(result, source, evidence)
    result.warnings = _warnings_for(result)
    if rejected:
        result.warnings.append(f"有 {len(set(rejected))} 个模型字段因缺少原文依据被忽略。")
    if low_confidence:
        result.warnings.append(f"有 {len(low_confidence)} 项内容需要对照原文确认。")
    result.other = {
        key: value for key, value in rules.other.items() if key not in {"文本解析", "解析诊断"}
    }
    result.other["解析诊断"] = {
        "文档类型": "resume",
        "置信度": 0.9 if sources else 0.6,
        "结构": "plain_text_llm",
        "章节标题数": 0,
    }
    result.other["文本解析"] = {
        "来源类型": "plain_text",
        "解析引擎": "ollama",
        "模型": "qwen3:4b",
        "自动回退": False,
        "耗时秒": ollama.elapsed_seconds,
        "输入Token": ollama.prompt_eval_count,
        "输出Token": ollama.eval_count,
        "字符数": len(source),
        "原始文本": source,
        "字段来源": sources,
        "低置信字段": low_confidence,
        "被忽略字段": sorted(set(rejected)),
        "未归类文本": extraction.unresolved_fragments,
    }
    return result


def parse_text_hybrid(text: str, client: OllamaClient | None = None) -> ResumeData:
    rules = parse_text_resume(text)
    ollama_client = client or OllamaClient()
    try:
        ollama = ollama_client.extract(text)
        return _merge_ai_and_rules(text, rules, ollama)
    except OllamaError as exc:
        metadata = rules.other.setdefault("文本解析", {})
        metadata.update(
            {
                "解析引擎": "rules_fallback",
                "模型": "qwen3:4b",
                "自动回退": True,
                "回退原因": str(exc),
            }
        )
        rules.warnings.insert(0, f"qwen3:4b 暂不可用，已自动切换本地规则解析：{exc}")
        return rules
