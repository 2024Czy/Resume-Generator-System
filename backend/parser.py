from __future__ import annotations

import re
from datetime import date, datetime
from typing import Iterable

from .models import EducationItem, ExperienceItem, Highlight, PersonalInfo, ResumeData, SkillItem
from .word_reader import ParagraphUnit, TableRow, WordSnapshot


SECTION_ALIASES = {
    "education": {"教育背景", "教育经历", "学历背景"},
    "projects": {"项目经历", "项目经验", "科研经历", "科研项目", "科研竞赛"},
    "internships": {"实习经历", "工作经历", "实践经历", "职业经历"},
    "skills": {"技能", "专业技能", "技能特长", "个人技能", "技能与荣誉"},
    "awards": {"荣誉奖项", "获奖经历", "奖项荣誉", "荣誉证书", "证书"},
    "self_evaluation": {"自我评价", "个人评价", "自我介绍", "个人总结"},
}

BACKGROUND_LABELS = {"背景", "项目背景", "工作背景", "简介", "项目简介", "项目介绍", "业务定位", "项目概述"}
RESULT_LABELS = {"成果", "项目成果", "工作成果", "主要成果"}
HIGHLIGHT_HEADINGS = {"核心工作", "核心贡献", "核心功能", "主要工作", "工作内容", "核心职责", "主要职责"}
PROJECT_ROLES = {"第一负责人", "第二负责人", "第一作者", "第二作者", "负责人", "项目成员", "核心成员", "队长"}
ROLE_SUFFIX_PATTERN = (
    r"VLA大模型算法实习生|大模型算法实习生|机器学习算法实习生|深度学习算法实习生|NLP算法实习生|"
    r"算法实习生|开发实习生|产品实习生|数据实习生|实习生|工程师|分析师|助理|经理|部长|主席|成员"
)

DATE_TOKEN = r"(?:19|20)\d{2}(?:[./年-]\d{1,2})?"
PERIOD_SUFFIX = rf"(?:[-–—~]\s*(?:{DATE_TOKEN}|至今|现在)|至\s*(?:{DATE_TOKEN}|今|现在))"
PERIOD_RE = re.compile(rf"({DATE_TOKEN}\s*{PERIOD_SUFFIX})")
ENTRY_DATE_RE = re.compile(
    rf"(?<!\d)({DATE_TOKEN}(?:\s*{PERIOD_SUFFIX})?)(?!\d)"
)
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?(1[3-9]\d{9})(?!\d)")
BIRTH_RE = re.compile(r"(?:出生(?:年月|日期)?|生日)\s*[:：]?\s*((?:19|20)\d{2}[./年-]\d{1,2}(?:[./月-]\d{1,2})?)")
AGE_RE = re.compile(r"年龄\s*[:：]?\s*(\d{1,2})")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" \t\r\n|；;")


def _normalize_period(text: str) -> str:
    match = PERIOD_RE.search(text)
    return _clean(match.group(1)) if match else ""


def _age_from_birth(value: str) -> int | None:
    numbers = [int(part) for part in re.findall(r"\d+", value)]
    if len(numbers) < 2:
        return None
    year, month = numbers[0], numbers[1]
    day = numbers[2] if len(numbers) > 2 else 1
    today = date.today()
    return today.year - year - ((today.month, today.day) < (month, day))


def _name_from_filename(filename: str) -> str:
    stem = re.sub(r"\.(?:docx|docm)$", "", filename, flags=re.I)
    blocked = re.compile(r"大学|学院|简历|求职|应聘|岗位|工程师|实习|硕士|本科|博士|技能")
    for part in re.split(r"[-_—–|\s]+", stem):
        candidate = part.strip("（）()[]【】 ")
        if re.fullmatch(r"[\u4e00-\u9fff·]{2,4}", candidate) and not blocked.search(candidate):
            return candidate
    return ""


def _personal(snapshot: WordSnapshot, filename: str = "") -> PersonalInfo:
    text = snapshot.all_text
    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search(text)
    birth = BIRTH_RE.search(text)
    explicit_age = AGE_RE.search(text)
    name = ""
    explicit_name = re.search(r"(?:姓名|名字)\s*[:：]\s*([\u4e00-\u9fff·]{2,4})", text)
    if explicit_name:
        name = explicit_name.group(1)
    candidates = [unit.text for unit in snapshot.body_paragraphs]
    candidates.extend(unit.text for box in snapshot.text_boxes for unit in box)
    candidates.extend(text.splitlines())
    if not name:
        for line in candidates:
            candidate = _clean(line)
            leading_name = re.match(
                r"^([\u4e00-\u9fff·]{2,4})(?=\s*(?:求职意向|应聘岗位|目标岗位|手机|电话|邮箱|年龄))",
                candidate,
            )
            if leading_name:
                name = leading_name.group(1)
                break
    if not name:
        for line in candidates:
            candidate = _clean(line)
            if (
                2 <= len(candidate) <= 8
                and not re.search(r"[:：@\d]", candidate)
                and not _section_key(candidate)
                and candidate not in {"基本信息", "个人信息", "联系方式", "求职意向"}
            ):
                name = candidate
                break
    if not name:
        name = _name_from_filename(filename)
    birth_date = birth.group(1) if birth else ""
    status_match = re.search(r"求职状态\s*[:：]?\s*([^\n]+)", text)
    location_match = re.search(r"(?:现居地|所在地|地址)\s*[:：]?\s*([^\n；;]+)", text)
    return PersonalInfo(
        name=name,
        age=int(explicit_age.group(1)) if explicit_age else _age_from_birth(birth_date),
        birth_date=birth_date,
        phone=phone.group(1) if phone else "",
        email=email.group(0) if email else "",
        location=_clean(location_match.group(1)) if location_match else "",
        job_status=_clean(status_match.group(1)) if status_match else "",
    )


def _section_key(text: str) -> str | None:
    normalized = re.sub(r"[\s:：|]+", "", text)
    for key, aliases in SECTION_ALIASES.items():
        if normalized in aliases:
            return key
    return None


def _split_title_tech(text: str) -> tuple[str, str]:
    text = _clean(text)
    match = re.match(r"^(.*?)[（(]([^（）()]{5,})[）)]$", text)
    if not match:
        return text, ""
    return _clean(match.group(1)), _clean(match.group(2))


def _split_label(text: str, bold_prefix: str = "") -> tuple[str, str]:
    clean = _clean(text)
    match = re.match(r"^([^：:]{1,30})[：:]\s*(.+)$", clean)
    if match:
        return _clean(match.group(1)), _clean(match.group(2))
    if bold_prefix and clean.startswith(bold_prefix):
        label = bold_prefix.rstrip("：:")
        content = clean[len(bold_prefix) :].lstrip("：: ")
        return label, content
    return "", clean


def _explode_units(units: Iterable[ParagraphUnit]) -> list[ParagraphUnit]:
    exploded: list[ParagraphUnit] = []
    for unit in units:
        lines = [line.strip() for line in re.split(r"[\r\n]+", unit.text) if line.strip()]
        if not lines:
            continue
        for index, line in enumerate(lines):
            exploded.append(
                ParagraphUnit(
                    text=line,
                    is_bullet=unit.is_bullet,
                    bold_prefix=unit.bold_prefix if index == 0 else "",
                )
            )
    return exploded


def _detail(units: list[ParagraphUnit]) -> dict:
    visible = [unit for unit in _explode_units(units) if _clean(unit.text)]
    if not visible:
        return {"name": "", "technologies": "", "background": "", "highlights": [], "results": []}
    first_text = _clean(visible[0].text)
    first_label, _ = _split_label(first_text, visible[0].bold_prefix)
    first_is_body = (
        first_label in BACKGROUND_LABELS | RESULT_LABELS | {"职责", "核心职责", "主要职责"}
        or first_text.rstrip("：:") in HIGHLIGHT_HEADINGS | RESULT_LABELS
        or (len(first_text) > 80 and re.search(r"[。；，]", first_text) is not None)
    )
    if first_is_body:
        name, technologies = "", ""
        detail_units = visible
    else:
        name, technologies = _split_title_tech(first_text)
        detail_units = visible[1:]
    background = ""
    highlights: list[Highlight] = []
    results: list[str] = []
    mode = "body"
    for unit in detail_units:
        text = _clean(unit.text)
        if text.rstrip("：:") in HIGHLIGHT_HEADINGS:
            mode = "highlights"
            continue
        if text.rstrip("：:") in RESULT_LABELS:
            mode = "results"
            continue
        label, content = _split_label(text, unit.bold_prefix)
        if label in BACKGROUND_LABELS:
            if not background:
                background = content
            elif content:
                highlights.append(Highlight(label=label, content=content))
        elif label in RESULT_LABELS:
            if content:
                results.append(content)
            mode = "results"
        elif label in {"职责", "核心职责", "主要职责"}:
            if content:
                highlights.append(Highlight(label=label, content=content))
        elif mode == "results":
            results.append(text)
        elif unit.is_bullet or mode == "highlights":
            highlights.append(Highlight(label=label, content=content))
        elif not background:
            background = text
        elif mode == "body" and not label and not unit.is_bullet:
            background = _clean(f"{background} {text}")
        else:
            highlights.append(Highlight(label=label, content=content))
    return {
        "name": name,
        "technologies": technologies,
        "background": background,
        "highlights": highlights,
        "results": results,
    }


def _find_row(rows: list[TableRow], heading: str) -> int | None:
    for index, row in enumerate(rows):
        texts = row.cell_texts
        if len(texts) == 1 and _section_key(_clean(texts[0])) == heading:
            return index
    return None


def _education_from_template(rows: list[TableRow], end_index: int | None) -> list[EducationItem]:
    if not rows:
        return []
    items: list[EducationItem] = []
    limit = 0 if end_index is None else end_index
    candidate_rows = rows[:limit] if limit else rows[:1]
    for row in candidate_rows:
        if len(row.cells) != 1:
            continue
        for unit in row.cells[0]:
            text = unit.text.strip()
            period = _normalize_period(text)
            if not period:
                continue
            remainder = text.replace(period, "", 1).strip()
            fields = [part.strip() for part in re.split(r"\s{2,}|\t+", remainder) if part.strip()]
            if len(fields) < 3:
                fields = [part.strip() for part in re.split(r"\s+", remainder) if part.strip()]
            school = fields[0] if fields else ""
            degree = fields[-1] if len(fields) >= 2 else ""
            major = " ".join(fields[1:-1]) if len(fields) >= 3 else ""
            items.append(EducationItem(period=period, school=school, major=major, degree=degree))
    return items


def _experiences_from_rows(
    rows: list[TableRow],
    start: int | None,
    end: int | None,
    kind: str,
) -> list[ExperienceItem]:
    if start is None:
        return []
    finish = len(rows) if end is None else end
    items: list[ExperienceItem] = []
    index = start + 1
    while index < finish:
        row = rows[index]
        texts = [_clean(text) for text in row.cell_texts]
        if len(texts) == 3 and _normalize_period(texts[0]):
            detail_units: list[ParagraphUnit] = []
            if index + 1 < finish and len(rows[index + 1].cells) == 1:
                detail_units = rows[index + 1].cells[0]
                index += 1
            detail = _detail(detail_units)
            middle = texts[1]
            organization = middle
            if kind == "projects" and not detail["name"]:
                detail["name"] = middle
                organization = ""
            items.append(
                ExperienceItem(
                    period=_normalize_period(texts[0]) or texts[0],
                    organization=organization,
                    role=texts[2],
                    **detail,
                )
            )
        index += 1
    compact_units: list[ParagraphUnit] = []
    for row in rows[start + 1 : finish]:
        if len(row.cells) != 1:
            continue
        units = _explode_units(row.cells[0])
        if units and PERIOD_RE.match(_clean(units[0].text)):
            compact_units.extend(units)
    if compact_units:
        items.extend(_generic_experiences(compact_units, kind=kind))
    return items


def _skills_from_rows(rows: list[TableRow], start: int | None) -> list[SkillItem]:
    if start is None:
        return []
    items: list[SkillItem] = []
    for row in rows[start + 1 :]:
        if len(row.cells) != 1:
            continue
        if any(_section_key(_clean(unit.text)) for unit in row.cells[0]):
            break
        for unit in _explode_units(row.cells[0]):
            label, content = _split_label(unit.text, unit.bold_prefix)
            if label or content:
                items.append(SkillItem(category=label or "其他技能", description=content))
    return items


def _generic_sections(snapshot: WordSnapshot) -> dict[str, list[ParagraphUnit]]:
    units: list[ParagraphUnit] = []
    if snapshot.reading_units:
        units.extend(snapshot.reading_units)
    # Synthetic snapshots and older callers may not provide reading_units.
    elif snapshot.text_boxes and not snapshot.body_paragraphs and not snapshot.table_rows:
        for box in snapshot.text_boxes:
            units.extend(box)
    else:
        units.extend(snapshot.body_paragraphs)
        for row in snapshot.table_rows:
            for cell in row.cells:
                units.extend(cell)
    sections: dict[str, list[ParagraphUnit]] = {key: [] for key in SECTION_ALIASES}
    active: str | None = None
    for unit in units:
        key = _section_key(_clean(unit.text))
        if key:
            active = key
        elif active:
            sections[active].append(unit)
    return sections


def _boxed_table_sections(snapshot: WordSnapshot) -> dict[str, list[TableRow]]:
    """Map floating section labels to table blocks separated by top borders.

    Many designer resumes anchor every heading in one VML paragraph and use
    table borders, rather than heading paragraphs, to delimit the content.  The
    XML order of those labels matches the order of the bordered table blocks.
    """
    headings: list[str] = []
    for box in snapshot.text_boxes:
        for unit in box:
            key = _section_key(_clean(unit.text))
            if key and (not headings or headings[-1] != key):
                headings.append(key)

    starts = [
        index
        for index, row in enumerate(snapshot.table_rows)
        if row.starts_section
        and any(_clean(text) for text in row.cell_texts)
        and re.search(DATE_TOKEN, " ".join(row.cell_texts))
    ]
    if not headings or len(starts) < len(headings):
        return {}

    sections: dict[str, list[TableRow]] = {}
    for position, (key, start) in enumerate(zip(headings, starts)):
        end = starts[position + 1] if position + 1 < len(headings) else len(snapshot.table_rows)
        sections.setdefault(key, []).extend(snapshot.table_rows[start:end])
    return sections


def _education_from_section_rows(rows: list[TableRow]) -> list[EducationItem]:
    items: list[EducationItem] = []
    school_re = re.compile(r"[\u4e00-\u9fff·]+(?:大学|学院)(?:[（(][^（）()]{1,40}[）)])?")
    degree_re = re.compile(r"(?:博士研究生|硕士研究生|本科|博士|硕士|学士|MBA)")
    for row in rows:
        texts = [_clean(text) for text in row.cell_texts if _clean(text)]
        if not texts:
            continue
        joined = " | ".join(texts)
        period = _normalize_period(joined)
        if not period:
            continue
        remainder = joined.replace(period, "", 1).strip(" -–—|~")
        school_match = school_re.search(remainder)
        degree_match = degree_re.search(remainder)
        school = school_match.group(0) if school_match else ""
        degree = degree_match.group(0) if degree_match else ""
        major = ""
        if len(texts) > 1:
            major = texts[1].replace("\n", " ")
            major = re.sub(r"^[\u4e00-\u9fff·]+学院\s*", "", major)
        if not school:
            fields = [part for part in re.split(r"\t+|\s+[|｜]\s+|\s{2,}", remainder) if part]
            school = fields[0] if fields else remainder
        items.append(EducationItem(period=period, school=_clean(school), major=_clean(major), degree=degree))
    return items


def _experience_units_from_rows(rows: list[TableRow]) -> list[ParagraphUnit]:
    return [
        unit
        for row in rows
        for cell in row.cells
        for unit in _explode_units(cell)
        if _clean(unit.text)
    ]


def _awards_from_rows(rows: list[TableRow]) -> list[str]:
    awards: list[str] = []
    for row in rows:
        texts = [_clean(text) for text in row.cell_texts if _clean(text)]
        if len(texts) >= 2 and re.search(DATE_TOKEN, texts[0]):
            awards.append(_clean(f"{texts[0]} {' '.join(texts[1:])}"))
        elif len(texts) == 1 and re.search(r"奖|荣誉|证书|优秀", texts[0]):
            awards.append(texts[0])
    return awards


def _practice_from_rows(rows: list[TableRow]) -> list[ExperienceItem]:
    items: list[ExperienceItem] = []
    action_re = re.compile(r"\s+(?=参与|负责|协助|组织|策划|完成|撰写|整理|开展|承担)")
    role_re = re.compile(rf"({ROLE_SUFFIX_PATTERN}|实习|负责人)$")
    for unit in _experience_units_from_rows(rows):
        text = _clean(unit.text)
        matches = list(ENTRY_DATE_RE.finditer(text))
        for index, match in enumerate(matches):
            finish = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            segment = _clean(text[match.end() : finish])
            if not segment:
                continue
            parts = action_re.split(segment, maxsplit=1)
            header = _clean(parts[0])
            background = _clean(parts[1]) if len(parts) > 1 else ""
            role_match = role_re.search(header)
            role = role_match.group(1) if role_match else ""
            organization = _clean(header[: role_match.start()]) if role_match else header
            items.append(
                ExperienceItem(
                    period=_clean(match.group(1)),
                    organization=organization,
                    role=role,
                    background=background,
                )
            )
    return items


def _undated_experience_groups(units: list[ParagraphUnit]) -> list[list[ParagraphUnit]]:
    starts = [0] if units else []
    for index in range(1, len(units)):
        text = _clean(units[index].text)
        next_text = _clean(units[index + 1].text) if index + 1 < len(units) else ""
        if (
            text
            and not _normalize_period(text)
            and not re.match(r"^(?:背景|项目背景|工作背景|简介|项目简介|项目介绍|业务定位|职责|成果|核心工作|核心功能|主要工作)\s*[:：]", text)
            and re.match(r"^(?:背景|项目背景|工作背景|简介|项目简介|项目介绍|业务定位)\s*[:：]", next_text)
        ):
            starts.append(index)
    starts.append(len(units))
    return [units[start:end] for start, end in zip(starts, starts[1:]) if start < end]


def _generic_experiences(
    units: list[ParagraphUnit],
    allow_undated: bool = False,
    kind: str = "internships",
) -> list[ExperienceItem]:
    groups: list[list[ParagraphUnit]] = []
    current: list[ParagraphUnit] = []
    for unit in units:
        if _normalize_period(unit.text):
            if current:
                groups.append(current)
            current = [unit]
        elif current:
            current.append(unit)
    if current:
        groups.append(current)

    if not groups and allow_undated:
        groups = _undated_experience_groups([unit for unit in units if _clean(unit.text)])

    items: list[ExperienceItem] = []
    for group in groups:
        raw_header = group[0].text.strip()
        header = _clean(raw_header)
        period = _normalize_period(raw_header)
        if not period:
            detail = _detail(group)
            items.append(ExperienceItem(**detail))
            continue
        raw_remainder = raw_header.replace(period, "", 1).strip(" -–—|\t")
        remainder = _clean(raw_remainder)
        header_fields = [
            _clean(part)
            for part in re.split(r"\t+|\s{2,}|\s+[|｜]\s+", raw_remainder)
            if _clean(part)
        ]
        organization = ""
        role = ""
        title = ""
        role_match = re.search(
            r"(第一负责人|第二负责人|第一作者|第二作者|负责人|项目成员|核心成员|队长|"
            + ROLE_SUFFIX_PATTERN
            + r")$",
            remainder,
        )
        if len(header_fields) >= 2:
            organization, role = header_fields[0], " ".join(header_fields[1:])
        elif role_match:
            role = role_match.group(1)
            prefix = _clean(remainder[: role_match.start()])
            if role in PROJECT_ROLES:
                title = prefix
            else:
                organization = prefix
        else:
            organization = remainder
        detail_units = list(group[1:])
        if title:
            detail_units.insert(0, ParagraphUnit(text=title))
        detail_groups = _undated_experience_groups(detail_units) or [[]]
        for detail_group in detail_groups:
            detail = _detail(detail_group)
            item_organization = organization
            if kind == "projects":
                header_title = title or organization
                if not detail["name"] and header_title:
                    detail["name"] = header_title
                    item_organization = ""
                elif title:
                    item_organization = ""
            items.append(
                ExperienceItem(
                    period=period,
                    organization=item_organization,
                    role=role,
                    **detail,
                )
            )
    return items


def _generic_education(units: list[ParagraphUnit]) -> list[EducationItem]:
    items: list[EducationItem] = []
    for unit in units:
        text = _clean(unit.text)
        period = _normalize_period(text)
        if not period:
            continue
        remainder = text.replace(period, "", 1).strip()
        fields = [part for part in re.split(r"\s{2,}|\t+|\s+[|｜]\s+", remainder) if part]
        if len(fields) == 1:
            fields = remainder.split()
        if fields:
            items.append(
                EducationItem(
                    period=period,
                    school=fields[0],
                    major=" ".join(fields[1:-1]) if len(fields) > 2 else "",
                    degree=fields[-1] if len(fields) > 1 else "",
                )
            )
    return items


def parse_resume(
    snapshot: WordSnapshot,
    filename: str = "",
    enforce_quality_gate: bool = True,
) -> ResumeData:
    rows = snapshot.table_rows
    project_index = _find_row(rows, "projects")
    internship_index = _find_row(rows, "internships")
    skills_index = _find_row(rows, "skills")
    awards_index = _find_row(rows, "awards")

    education = _education_from_template(rows, project_index)
    project_end = internship_index if internship_index is not None else skills_index
    projects = _experiences_from_rows(rows, project_index, project_end, "projects")
    internships = _experiences_from_rows(rows, internship_index, skills_index, "internships")
    skills = _skills_from_rows(rows, skills_index)
    awards: list[str] = []

    boxed = _boxed_table_sections(snapshot)
    if not education and boxed.get("education"):
        education = _education_from_section_rows(boxed["education"])
    if not projects and boxed.get("projects"):
        projects = _generic_experiences(_experience_units_from_rows(boxed["projects"]), kind="projects")
    if not internships and boxed.get("internships"):
        internships = _practice_from_rows(boxed["internships"])
    if boxed.get("awards"):
        awards = _awards_from_rows(boxed["awards"])

    generic = _generic_sections(snapshot)
    if not education or not projects or not internships or not skills or not awards:
        if not education:
            education = _generic_education(generic["education"])
        if not projects:
            projects = _generic_experiences(generic["projects"], allow_undated=True, kind="projects")
        if not internships:
            internships = _generic_experiences(generic["internships"], kind="internships")
        if not skills:
            skills = [SkillItem(category=label, description=content) for label, content in (_split_label(u.text, u.bold_prefix) for u in generic["skills"]) if label or content]
        if not awards:
            awards = [_clean(u.text) for u in generic["awards"] if _clean(u.text)]

    warnings: list[str] = []
    personal = _personal(snapshot, filename)
    required = {
        "姓名": personal.name,
        "手机": personal.phone,
        "邮箱": personal.email,
        "教育经历": education,
    }
    for label, value in required.items():
        if not value:
            warnings.append(f"未可靠识别{label}，请在生成前补充。")
    if not projects:
        warnings.append("未识别到项目经历；该模板允许省略此分节。")
    if not internships:
        warnings.append("未识别到实习/工作经历；该模板允许省略此分节。")
    if not skills:
        warnings.append("未识别到专业技能；建议至少补充一项。")

    section_count = sum(
        1
        for unit in (snapshot.reading_units or [u for box in snapshot.text_boxes for u in box])
        if _section_key(_clean(unit.text))
    )
    quality_score = sum(
        [
            0.15 if personal.name else 0,
            0.10 if personal.phone else 0,
            0.10 if personal.email else 0,
            0.25 if education else 0,
            0.15 if projects else 0,
            0.15 if internships else 0,
            0.10 if skills else 0,
        ]
    )
    is_resume = quality_score >= 0.45 and bool(personal.phone or personal.email) and bool(education or section_count >= 2)
    if not is_resume:
        warnings.insert(0, "文档疑似不是简历或关键信息过少，请确认上传文件。")
    if enforce_quality_gate and not is_resume and not (personal.phone or personal.email) and not education:
        # Do not flood the editor with hundreds of false skills when a report,
        # question bank, or another non-resume document happens to contain a
        # heading such as “技能”.  Preserve only the diagnostic warning.
        personal = PersonalInfo()
        projects = []
        internships = []
        skills = []
        awards = []
        warnings = ["文档疑似不是简历或关键信息过少，请确认上传文件。"]

    other: dict[str, object] = {
        "解析诊断": {
            "文档类型": "resume" if is_resume else "low_confidence",
            "置信度": round(quality_score, 2),
            "结构": (
                "hybrid"
                if snapshot.text_boxes and snapshot.table_rows
                else "text_boxes"
                if snapshot.text_boxes
                else "tables"
                if snapshot.table_rows
                else "paragraphs"
            ),
            "章节标题数": section_count,
        }
    }
    education_notes = [
        _clean(unit.text)
        for unit in generic["education"]
        if _clean(unit.text) and not _normalize_period(unit.text)
    ]
    if education_notes:
        other["教育补充"] = education_notes
    self_evaluation = [_clean(unit.text) for unit in generic["self_evaluation"] if _clean(unit.text)]
    if self_evaluation:
        other["自我评价"] = self_evaluation

    return ResumeData(
        personal=personal,
        education=education,
        projects=projects,
        internships=internships,
        skills=skills,
        awards=awards,
        photo_base64=snapshot.photo_base64,
        source_filename=filename,
        warnings=warnings,
        other=other,
    )
