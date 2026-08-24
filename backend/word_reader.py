from __future__ import annotations

import base64
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree
from PIL import Image


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
V = "urn:schemas-microsoft-com:vml"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS = {"w": W, "r": R, "mc": MC, "v": V, "wp": WP}


def qn(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


@dataclass
class ParagraphUnit:
    text: str
    is_bullet: bool = False
    bold_prefix: str = ""


@dataclass
class TableRow:
    cells: list[list[ParagraphUnit]] = field(default_factory=list)
    starts_section: bool = False

    @property
    def cell_texts(self) -> list[str]:
        return ["\n".join(p.text for p in cell if p.text) for cell in self.cells]


@dataclass
class WordSnapshot:
    text_boxes: list[list[ParagraphUnit]]
    body_paragraphs: list[ParagraphUnit]
    table_rows: list[TableRow]
    photo_base64: str = ""
    reading_units: list[ParagraphUnit] = field(default_factory=list)

    @property
    def all_text(self) -> str:
        if self.reading_units:
            return "\n".join(unit.text for unit in self.reading_units if unit.text)
        pieces: list[str] = []
        for box in self.text_boxes:
            pieces.extend(p.text for p in box if p.text)
        pieces.extend(p.text for p in self.body_paragraphs if p.text)
        for row in self.table_rows:
            pieces.extend(text for text in row.cell_texts if text)
        return "\n".join(pieces)


def _visible_text(node: etree._Element) -> str:
    chunks: list[str] = []

    def walk(current: etree._Element) -> None:
        if current.tag == qn(MC, "Fallback"):
            return
        if current.tag == qn(W, "t") and current.text:
            chunks.append(current.text)
            return
        if current.tag == qn(W, "tab"):
            chunks.append("\t")
            return
        if current.tag in {qn(W, "br"), qn(W, "cr")}:
            chunks.append("\n")
            return
        for child in current:
            walk(child)

    walk(node)
    return re.sub(r"[ \u3000]+", " ", "".join(chunks)).strip()


def _paragraph_unit(paragraph: etree._Element) -> ParagraphUnit:
    text = _visible_text(paragraph)
    num_id = paragraph.find("w:pPr/w:numPr/w:numId", NS)
    is_bullet = num_id is not None and num_id.get(qn(W, "val"), "0") not in {"", "0"}
    bold_chunks: list[str] = []
    for run in paragraph.findall("w:r", NS):
        rpr = run.find("w:rPr", NS)
        bold = None if rpr is None else rpr.find("w:b", NS)
        is_bold = bold is not None and bold.get(qn(W, "val"), "1") not in {"0", "false", "off"}
        if not is_bold:
            if bold_chunks:
                break
            continue
        bold_chunks.append(_visible_text(run))
    return ParagraphUnit(text=text, is_bullet=is_bullet, bold_prefix="".join(bold_chunks).strip())


def _has_ancestor(node: etree._Element, tag: str) -> bool:
    current = node.getparent()
    while current is not None:
        if current.tag == tag:
            return True
        current = current.getparent()
    return False


def _style_position(style: str, name: str) -> float | None:
    match = re.search(rf"(?:^|;){re.escape(name)}\s*:\s*(-?\d+(?:\.\d+)?)pt", style, re.I)
    return float(match.group(1)) if match else None


def _text_box_position(
    content: etree._Element,
    source_index: int,
    flow_indices: dict[int, int],
) -> tuple[int, float, float, int]:
    """Return a sortable visual position for a floating text box.

    DrawingML stores offsets in EMU and legacy VML stores them in points.  The
    absolute unit does not matter for ordering, so VML points are converted to
    EMU.  Unpositioned boxes retain their package order after positioned ones.
    """
    current = content.getparent()
    anchor = None
    shape = None
    outer_paragraph = None
    while current is not None:
        if current.tag in {qn(WP, "anchor"), qn(WP, "inline")}:
            anchor = current
        if current.tag == qn(V, "shape"):
            shape = current
        if current.tag == qn(W, "p"):
            outer_paragraph = current
        current = current.getparent()

    flow_index = flow_indices.get(id(outer_paragraph), source_index)

    if anchor is not None:
        horizontal = anchor.find("wp:positionH", NS)
        vertical = anchor.find("wp:positionV", NS)
        x_text = horizontal.findtext("wp:posOffset", default="0", namespaces=NS) if horizontal is not None else "0"
        y_text = vertical.findtext("wp:posOffset", default="0", namespaces=NS) if vertical is not None else "0"
        try:
            return flow_index, float(y_text), float(x_text), source_index
        except ValueError:
            pass

    if shape is not None:
        style = shape.get("style", "")
        x = _style_position(style, "margin-left")
        y = _style_position(style, "margin-top")
        if x is not None or y is not None:
            return flow_index, (y or 0.0) * 12700, (x or 0.0) * 12700, source_index

    return flow_index, float("inf"), float(source_index), source_index


def _paragraph_without_text_boxes(paragraph: etree._Element) -> ParagraphUnit:
    clone = etree.fromstring(etree.tostring(paragraph))
    for box in clone.findall(".//w:txbxContent", NS):
        parent = box.getparent()
        if parent is not None:
            parent.remove(box)
    return _paragraph_unit(clone)


def _best_photo(archive: zipfile.ZipFile) -> str:
    candidates: list[tuple[float, bytes]] = []
    for name in archive.namelist():
        if not name.lower().startswith("word/media/") or name.endswith("/"):
            continue
        payload = archive.read(name)
        try:
            with Image.open(io.BytesIO(payload)) as image:
                width, height = image.size
                if width < 60 or height < 60:
                    continue
                ratio = width / height
                portrait_score = abs(ratio - 2 / 3)
                area_bonus = min(width * height / 1_000_000, 1)
                score = portrait_score - area_bonus * 0.15
                candidates.append((score, payload))
        except Exception:
            continue
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0])
    return base64.b64encode(candidates[0][1]).decode("ascii")


def read_word(source: bytes | Path) -> WordSnapshot:
    stream = io.BytesIO(source) if isinstance(source, bytes) else source
    with zipfile.ZipFile(stream) as archive:
        document = etree.fromstring(archive.read("word/document.xml"))
        body = document.find("w:body", NS)
        flow_nodes = (
            body.xpath(
                ".//w:p[not(ancestor::w:txbxContent) and not(ancestor::w:tbl)] | .//w:tr",
                namespaces=NS,
            )
            if body is not None
            else []
        )
        flow_indices = {id(node): index for index, node in enumerate(flow_nodes)}
        positioned_boxes: list[tuple[tuple[int, float, float, int], list[ParagraphUnit]]] = []
        # VML text boxes are still common in Chinese resume templates.  They can
        # appear directly below w:pict (without mc:Choice), so limiting the
        # search to compatibility branches silently drops section headings.
        for source_index, content in enumerate(document.findall(".//w:txbxContent", NS)):
            # AlternateContent contains a modern DrawingML representation and
            # a legacy VML fallback of the same shape.  Prefer Choice and keep
            # direct (non-fallback) VML shapes used by older resume templates.
            if _has_ancestor(content, qn(MC, "Fallback")):
                continue
            units = [_paragraph_unit(p) for p in content.findall("w:p", NS)]
            if any(unit.text for unit in units):
                positioned_boxes.append((_text_box_position(content, source_index, flow_indices), units))
        positioned_boxes.sort(key=lambda item: item[0])
        text_boxes = [units for _, units in positioned_boxes]

        body_paragraphs: list[ParagraphUnit] = []
        if body is not None:
            for paragraph in body.xpath(
                ".//w:p[not(ancestor::w:txbxContent) and not(ancestor::w:tbl)]",
                namespaces=NS,
            ):
                unit = _paragraph_without_text_boxes(paragraph)
                if unit.text:
                    body_paragraphs.append(unit)

        table_rows: list[TableRow] = []
        table_rows_by_flow: dict[int, TableRow] = {}
        for table in document.findall(".//w:tbl", NS):
            for row in table.findall("w:tr", NS):
                cells: list[list[ParagraphUnit]] = []
                starts_section = False
                for cell in row.findall("w:tc", NS):
                    top_border = cell.find("w:tcPr/w:tcBorders/w:top", NS)
                    if top_border is not None:
                        border_style = top_border.get(qn(W, "val"), "")
                        border_size = top_border.get(qn(W, "sz"), "0")
                        starts_section = starts_section or (
                            border_style not in {"", "nil", "none"}
                            and border_size not in {"", "0"}
                        )
                    cells.append(
                        [
                            _paragraph_unit(paragraph)
                            for paragraph in cell.findall("w:p", NS)
                            if _visible_text(paragraph)
                        ]
                    )
                parsed_row = TableRow(cells=cells, starts_section=starts_section)
                table_rows.append(parsed_row)
                table_rows_by_flow[id(row)] = parsed_row

        boxes_by_flow: dict[int, list[tuple[tuple[int, float, float, int], list[ParagraphUnit]]]] = {}
        for key, units in positioned_boxes:
            boxes_by_flow.setdefault(key[0], []).append((key, units))

        reading_units: list[ParagraphUnit] = []
        for flow_index, node in enumerate(flow_nodes):
            if node.tag == qn(W, "p"):
                unit = _paragraph_without_text_boxes(node)
                if unit.text:
                    reading_units.append(unit)
                for _, units in sorted(boxes_by_flow.get(flow_index, []), key=lambda item: item[0]):
                    reading_units.extend(unit for unit in units if unit.text)
            elif node.tag == qn(W, "tr"):
                row = table_rows_by_flow.get(id(node))
                if row is not None:
                    reading_units.extend(
                        unit
                        for cell in row.cells
                        for unit in cell
                        if unit.text
                    )
        return WordSnapshot(
            text_boxes=text_boxes,
            body_paragraphs=body_paragraphs,
            table_rows=table_rows,
            photo_base64=_best_photo(archive),
            reading_units=reading_units,
        )
