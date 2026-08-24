from __future__ import annotations

import base64
import copy
import html
import io
import re
import zipfile
from pathlib import Path

from lxml import etree
from PIL import Image, ImageOps

from .models import EducationItem, ExperienceItem, ResumeData, SkillItem


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
NS = {"w": W, "mc": MC}


def qn(local: str) -> str:
    return f"{{{W}}}{local}"


def _text(node: etree._Element) -> str:
    return "".join(t.text or "" for t in node.findall(".//w:t", NS)).strip()


def _run_properties(paragraph: etree._Element, bold: bool) -> etree._Element | None:
    fallback = None
    for run in paragraph.findall("w:r", NS):
        rpr = run.find("w:rPr", NS)
        if rpr is None:
            continue
        if fallback is None:
            fallback = rpr
        b = rpr.find("w:b", NS)
        is_bold = b is not None and b.get(qn("val"), "1") not in {"0", "false", "off"}
        if is_bold == bold:
            return copy.deepcopy(rpr)
    return copy.deepcopy(fallback) if fallback is not None else None


def _clear_paragraph(paragraph: etree._Element) -> None:
    for child in list(paragraph):
        if child.tag != qn("pPr"):
            paragraph.remove(child)


def _add_run(
    paragraph: etree._Element,
    text: str,
    bold: bool = False,
    tab_before: bool = False,
    run_properties: etree._Element | None = None,
) -> None:
    run = etree.Element(qn("r"))
    rpr = copy.deepcopy(run_properties) if run_properties is not None else _run_properties(paragraph, bold)
    if rpr is not None:
        run.append(rpr)
    if tab_before:
        run.append(etree.Element(qn("tab")))
    text_node = etree.Element(qn("t"))
    if text.startswith(" ") or text.endswith(" "):
        text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_node.text = text
    run.append(text_node)
    paragraph.append(run)


def _append_run_text(run: etree._Element, text: str) -> None:
    normalized = html.unescape(text or "").replace("\r\n", "\n").replace("\r", "\n")
    for index, line in enumerate(normalized.split("\n")):
        if index:
            run.append(etree.Element(qn("br")))
        text_node = etree.Element(qn("t"))
        if line.startswith(" ") or line.endswith(" "):
            text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        text_node.text = line
        run.append(text_node)


def _set_paragraph(paragraph: etree._Element, parts: list[tuple[str, bool]]) -> etree._Element:
    prototypes = {False: _run_properties(paragraph, False), True: _run_properties(paragraph, True)}
    _clear_paragraph(paragraph)
    for text, bold in parts:
        if not text:
            continue
        run = etree.Element(qn("r"))
        rpr = prototypes[bold] if prototypes[bold] is not None else prototypes[not bold]
        if rpr is not None:
            run.append(copy.deepcopy(rpr))
        _append_run_text(run, text)
        paragraph.append(run)
    return paragraph


def _set_cell_text(cell: etree._Element, value: str) -> None:
    paragraph = cell.find("w:p", NS)
    if paragraph is None:
        paragraph = etree.SubElement(cell, qn("p"))
    _set_paragraph(paragraph, [(value, True)])
    width_node = cell.find("w:tcPr/w:tcW", NS)
    width = int(width_node.get(qn("w"), "0")) if width_node is not None else 0
    _set_paragraph_font_size(paragraph, _adaptive_half_points([value], width))
    for extra in cell.findall("w:p", NS)[1:]:
        cell.remove(extra)
    _set_cell_single_line(cell)


def _set_cell_single_line(cell: etree._Element) -> None:
    """Keep compact metadata rows on one line and let Word fit the text."""
    tcpr = cell.find("w:tcPr", NS)
    if tcpr is None:
        tcpr = etree.Element(qn("tcPr"))
        cell.insert(0, tcpr)
    property_order = [
        "cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
        "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark", "headers",
    ]
    for local in ("noWrap",):
        if tcpr.find(f"w:{local}", NS) is not None:
            continue
        element = etree.Element(qn(local))
        desired = property_order.index(local)
        for index, child in enumerate(tcpr):
            child_local = etree.QName(child).localname
            child_order = property_order.index(child_local) if child_local in property_order else len(property_order)
            if child_order > desired:
                tcpr.insert(index, element)
                break
        else:
            tcpr.append(element)


def _set_table_fixed_layout(table: etree._Element) -> None:
    tblpr = table.find("w:tblPr", NS)
    if tblpr is None:
        tblpr = etree.Element(qn("tblPr"))
        table.insert(0, tblpr)
    layout = tblpr.find("w:tblLayout", NS)
    if layout is None:
        layout = etree.SubElement(tblpr, qn("tblLayout"))
    layout.set(qn("type"), "fixed")


def _set_tab_stops(paragraph: etree._Element, positions: list[int]) -> None:
    ppr = paragraph.find("w:pPr", NS)
    if ppr is None:
        ppr = etree.Element(qn("pPr"))
        paragraph.insert(0, ppr)
    old = ppr.find("w:tabs", NS)
    if old is not None:
        ppr.remove(old)
    tabs = etree.Element(qn("tabs"))
    for position in positions:
        tab = etree.SubElement(tabs, qn("tab"))
        tab.set(qn("val"), "left")
        tab.set(qn("pos"), str(position))
    ppr.insert(0, tabs)


def _visual_units(text: str) -> float:
    units = 0.0
    for char in text:
        if "\u4e00" <= char <= "\u9fff" or char in "（）【】《》":
            units += 1.0
        elif char.isspace():
            units += 0.35
        else:
            units += 0.55
    return units


def _adaptive_half_points(values: list[str], available_width: int, base: int = 18, minimum: int = 16) -> int:
    visible = [value for value in values if value]
    if not visible or available_width <= 0:
        return base
    estimated_width = sum(_visual_units(value) * 180 for value in visible) + max(0, len(visible) - 1) * 260
    if estimated_width <= available_width:
        return base
    return max(minimum, min(base, int(base * available_width / estimated_width)))


def _set_paragraph_font_size(paragraph: etree._Element, half_points: int) -> None:
    for rpr in paragraph.findall(".//w:rPr", NS):
        for local in ("sz", "szCs"):
            size = rpr.find(f"w:{local}", NS)
            if size is None:
                size = etree.SubElement(rpr, qn(local))
            size.set(qn("val"), str(half_points))


def _education_tab_positions(item: EducationItem, total_width: int = 9860) -> list[int]:
    period_width = max(1900, min(2600, int(_visual_units(item.period) * 180 + 300)))
    school_cap = 2700 if item.degree else 3000
    school_width = max(1700, min(school_cap, int(_visual_units(item.school) * 180 + 250)))
    major_start = period_width + school_width + 180
    positions = [period_width, major_start]
    if item.degree:
        degree_width = max(900, min(1700, int(_visual_units(item.degree) * 180 + 350)))
        degree_start = max(major_start + 1800, total_width - degree_width)
        positions.append(min(degree_start, total_width - 700))
    return positions


def _education_row(prototype: etree._Element, items: list[EducationItem]) -> etree._Element:
    row = copy.deepcopy(prototype)
    cell = row.find("w:tc", NS)
    if cell is None:
        return row
    prototypes = cell.findall("w:p", NS)
    base = prototypes[0] if prototypes else etree.Element(qn("p"))
    for paragraph in prototypes:
        cell.remove(paragraph)
    for item in items:
        paragraph = copy.deepcopy(base)
        bold_rpr = _run_properties(paragraph, True)
        line_size = _adaptive_half_points([item.period, item.school, item.major, item.degree], 9860)
        if bold_rpr is not None:
            for local in ("sz", "szCs"):
                size = bold_rpr.find(f"w:{local}", NS)
                if size is None:
                    size = etree.SubElement(bold_rpr, qn(local))
                size.set(qn("val"), str(line_size))
        _set_tab_stops(paragraph, _education_tab_positions(item))
        _clear_paragraph(paragraph)
        _add_run(paragraph, item.period, bold=True, run_properties=bold_rpr)
        _add_run(paragraph, item.school, bold=True, tab_before=True, run_properties=bold_rpr)
        _add_run(paragraph, item.major, bold=True, tab_before=True, run_properties=bold_rpr)
        if item.degree:
            _add_run(paragraph, item.degree, bold=True, tab_before=True, run_properties=bold_rpr)
        cell.append(paragraph)
    if not items:
        paragraph = copy.deepcopy(base)
        _set_paragraph(paragraph, [("教育信息待补充", False)])
        cell.append(paragraph)
    _set_cell_single_line(cell)
    return row


def _header_row(prototype: etree._Element, period: str, middle: str, right: str) -> etree._Element:
    row = copy.deepcopy(prototype)
    cells = row.findall("w:tc", NS)
    for cell, value in zip(cells, (period, middle, right)):
        _set_cell_text(cell, value)
    return row


def _paragraph_copy(prototype: etree._Element, parts: list[tuple[str, bool]]) -> etree._Element:
    paragraph = copy.deepcopy(prototype)
    return _set_paragraph(paragraph, parts)


BULLET_PREFIX_RE = re.compile(r"^\s*(?:[\uf06c\uf0b7•●▪■◆◇◦○·]|[-*])\s*")
EXPLICIT_HEADING_LINES = {"核心功能", "核心工作", "主要工作", "工作内容", "主要职责"}


def _clean_input_text(value: str) -> str:
    return html.unescape(value or "").replace("\r\n", "\n").replace("\r", "\n")


def _labelled_parts(text: str, default_label: str = "") -> list[tuple[str, bool]]:
    clean = text.strip()
    match = re.match(r"^([^：:\n]{1,12})[：:]\s*(.*)$", clean)
    if match:
        label = match.group(1).strip().rstrip("：:") + "："
        return [(label, True), (match.group(2).strip(), False)]
    if default_label:
        return [(default_label.rstrip("：:") + "：", True), (clean, False)]
    return [(clean, False)]


def _without_leading_label(text: str, labels: set[str]) -> str:
    clean = _clean_input_text(text).strip()
    alternation = "|".join(re.escape(label.rstrip("：:")) for label in labels)
    return re.sub(rf"^(?:{alternation})\s*[：:]\s*", "", clean, count=1)


def _append_multiline_background(
    cell: etree._Element,
    value: str,
    body_prototype: etree._Element,
    heading_prototype: etree._Element,
    bullet_prototype: etree._Element,
) -> None:
    lines = [line.strip() for line in _clean_input_text(value).split("\n") if line.strip()]
    for index, raw_line in enumerate(lines):
        is_bullet = BULLET_PREFIX_RE.match(raw_line) is not None
        line = BULLET_PREFIX_RE.sub("", raw_line, count=1).strip() if is_bullet else raw_line
        if line in EXPLICIT_HEADING_LINES:
            cell.append(_paragraph_copy(heading_prototype, [(line, True)]))
            continue
        default_label = "背景" if index == 0 and not re.match(r"^背景\s*[：:]", line) else ""
        prototype = bullet_prototype if is_bullet else body_prototype
        cell.append(_paragraph_copy(prototype, _labelled_parts(line, default_label)))


def _body_row(prototype: etree._Element, item: ExperienceItem) -> etree._Element:
    row = copy.deepcopy(prototype)
    cell = row.find("w:tc", NS)
    if cell is None:
        return row
    old = cell.findall("w:p", NS)
    title_p = old[0] if old else etree.Element(qn("p"))
    background_p = old[1] if len(old) > 1 else title_p
    heading_p = old[2] if len(old) > 2 else title_p
    bullet_p = next(
        (
            p
            for p in old
            if (p.find("w:pPr/w:numPr/w:numId", NS) is not None)
            and p.find("w:pPr/w:numPr/w:numId", NS).get(qn("val"), "0") != "0"
        ),
        background_p,
    )
    for paragraph in old:
        cell.remove(paragraph)

    title = item.name or item.organization
    if item.technologies:
        title = f"{title}（{item.technologies}）"
    cell.append(_paragraph_copy(title_p, [(title, True)]))
    if item.background:
        _append_multiline_background(cell, item.background, background_p, heading_p, bullet_p)
    if item.highlights:
        cell.append(_paragraph_copy(heading_p, [("核心工作", True)]))
        for highlight in item.highlights:
            parts: list[tuple[str, bool]] = []
            if highlight.label:
                label = highlight.label.rstrip("：:")
                parts.append((label + "：", True))
                parts.append((_without_leading_label(highlight.content, {label}), False))
            else:
                parts.append((highlight.content, False))
            cell.append(_paragraph_copy(bullet_p, parts))
    if len(item.results) == 1:
        result = _without_leading_label(item.results[0], {"成果", "项目成果", "工作成果"})
        cell.append(_paragraph_copy(background_p, [("成果：", True), (result, True)]))
    elif item.results:
        cell.append(_paragraph_copy(heading_p, [("成果：", True)]))
        for result in item.results:
            clean_result = _without_leading_label(result, {"成果", "项目成果", "工作成果"})
            cell.append(_paragraph_copy(bullet_p, [(clean_result, False)]))
    return row


def _skills_row(prototype: etree._Element, skills: list[SkillItem], awards: list[str]) -> etree._Element:
    row = copy.deepcopy(prototype)
    cell = row.find("w:tc", NS)
    if cell is None:
        return row
    old = cell.findall("w:p", NS)
    base = old[0] if old else etree.Element(qn("p"))
    for paragraph in old:
        cell.remove(paragraph)
    combined = list(skills)
    if awards:
        combined.append(SkillItem(category="荣誉奖项", description="；".join(awards)))
    for skill in combined:
        label = (skill.category or "其他技能").rstrip("：:") + "："
        cell.append(_paragraph_copy(base, [(label, True), (skill.description, False)]))
    if not combined:
        cell.append(_paragraph_copy(base, [("专业技能：", True), ("待补充", False)]))
    return row


def _replace_text_box(document: etree._Element, data: ResumeData) -> None:
    personal = data.personal
    for content in document.findall(".//w:txbxContent", NS):
        paragraphs = content.findall("w:p", NS)
        visible = "\n".join(_text(p) for p in paragraphs)
        if "手机" in visible and "邮箱" in visible and paragraphs:
            _set_paragraph(paragraphs[0], [(personal.name or "姓名待补充", True)])
            if len(paragraphs) > 1:
                _set_paragraph(paragraphs[1], [("手机：", False), (personal.phone or "待补充", False)])
            if len(paragraphs) > 2:
                _set_paragraph(paragraphs[2], [("邮箱：", False), (personal.email or "待补充", False)])
        elif "出生年月" in visible and paragraphs:
            paragraph = paragraphs[0]
            prototypes = {False: _run_properties(paragraph, False), True: _run_properties(paragraph, True)}
            _clear_paragraph(paragraph)
            values = [
                ("出生年月：", personal.birth_date or (str(personal.age) + "岁" if personal.age else "待补充")),
                ("求职状态：", personal.job_status or "待补充"),
            ]
            for line_index, (label, value) in enumerate(values):
                if line_index:
                    br_run = etree.Element(qn("r"))
                    if prototypes[False] is not None:
                        br_run.append(copy.deepcopy(prototypes[False]))
                    br_run.append(etree.Element(qn("br")))
                    paragraph.append(br_run)
                _add_run(paragraph, label + value, bold=False, run_properties=prototypes[False])


def _photo_jpeg(photo_base64: str) -> bytes:
    if photo_base64:
        try:
            raw = base64.b64decode(photo_base64)
            with Image.open(io.BytesIO(raw)) as image:
                image = image.convert("RGB")
                image = ImageOps.fit(image, (354, 531), method=Image.Resampling.LANCZOS, centering=(0.5, 0.42))
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=92, optimize=True)
                return output.getvalue()
        except Exception:
            pass
    blank = Image.new("RGB", (354, 531), "white")
    output = io.BytesIO()
    blank.save(output, format="JPEG", quality=90)
    return output.getvalue()


def _docx_content_types(payload: bytes) -> bytes:
    root = etree.fromstring(payload)
    for override in root:
        content_type = override.get("ContentType", "")
        if content_type == "application/vnd.ms-word.document.macroEnabled.main+xml":
            override.set("ContentType", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")


def generate_resume(template_path: Path, data: ResumeData, output_path: Path) -> Path:
    with zipfile.ZipFile(template_path, "r") as source:
        document = etree.fromstring(source.read("word/document.xml"))
        _replace_text_box(document, data)
        table = document.find(".//w:tbl", NS)
        if table is None:
            raise ValueError("模板不包含主简历表格")
        _set_table_fixed_layout(table)
        rows = table.findall("w:tr", NS)
        if len(rows) < 15:
            raise ValueError("模板表格行型不足，无法执行 v7.3 转换规则")
        prototypes = {
            "education": rows[0],
            "project_heading": rows[1],
            "project_header": rows[2],
            "project_body": rows[3],
            "internship_heading": rows[4],
            "internship_header": rows[5],
            "internship_body": rows[6],
            "skills_heading": rows[13],
            "skills_body": rows[14],
        }
        for row in rows:
            table.remove(row)
        table.append(_education_row(prototypes["education"], data.education))
        if data.projects:
            table.append(copy.deepcopy(prototypes["project_heading"]))
            for item in data.projects:
                table.append(_header_row(prototypes["project_header"], item.period, item.organization or item.name, item.role))
                table.append(_body_row(prototypes["project_body"], item))
        if data.internships:
            table.append(copy.deepcopy(prototypes["internship_heading"]))
            for item in data.internships:
                table.append(_header_row(prototypes["internship_header"], item.period, item.organization, item.role))
                table.append(_body_row(prototypes["internship_body"], item))
        table.append(copy.deepcopy(prototypes["skills_heading"]))
        table.append(_skills_row(prototypes["skills_body"], data.skills, data.awards))

        document_bytes = etree.tostring(document, xml_declaration=True, encoding="UTF-8", standalone="yes")
        photo = _photo_jpeg(data.photo_base64)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        is_docx = output_path.suffix.lower() == ".docx"
        with zipfile.ZipFile(output_path, "w") as target:
            for info in source.infolist():
                payload = source.read(info.filename)
                if info.filename == "word/document.xml":
                    payload = document_bytes
                elif info.filename == "word/media/image1.jpeg":
                    payload = photo
                elif info.filename == "[Content_Types].xml" and is_docx:
                    payload = _docx_content_types(payload)
                target.writestr(info, payload)
    return output_path
