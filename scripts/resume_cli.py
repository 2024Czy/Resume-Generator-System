from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.generator import generate_resume  # noqa: E402
from backend.llm_parser import parse_text_hybrid  # noqa: E402
from backend.models import ResumeData  # noqa: E402
from backend.parser import parse_resume  # noqa: E402
from backend.text_parser import parse_text_resume  # noqa: E402
from backend.word_reader import read_word  # noqa: E402


MAX_WORD_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 50_000


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _require_input(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"Input file does not exist: {path}")


def _prepare_output(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise ValueError(f"Output already exists (pass --force to replace it): {path}")
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_json(data: ResumeData, output: Path, force: bool) -> None:
    _prepare_output(output, force)
    output.write_text(
        json.dumps(data.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> ResumeData:
    _require_input(path)
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if isinstance(payload, dict) and "resume" in payload:
        payload = payload["resume"]
    return ResumeData.model_validate(payload)


def parse_word(args: argparse.Namespace) -> None:
    source = _path(args.input)
    output = _path(args.output)
    _require_input(source)
    if source.name.startswith("~$"):
        raise ValueError("Word lock files beginning with ~$ are not valid resume inputs")
    if source.suffix.lower() not in {".docx", ".docm"}:
        raise ValueError("Word input must use a .docx or .docm extension")
    if source.stat().st_size > MAX_WORD_BYTES:
        raise ValueError("Word input exceeds the 20 MB limit")
    result = parse_resume(read_word(source.read_bytes()), source.name)
    _write_json(result, output, args.force)
    print(output)


def parse_text(args: argparse.Namespace) -> None:
    source = _path(args.input)
    output = _path(args.output)
    _require_input(source)
    text = source.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError("Text input is empty")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError("Text input exceeds the 50,000 character limit")
    result = parse_text_resume(text) if args.engine == "rules" else parse_text_hybrid(text)
    result.source_filename = source.name
    _write_json(result, output, args.force)
    print(output)


def validate(args: argparse.Namespace) -> None:
    resume = _read_json(_path(args.input))
    print(
        json.dumps(
            {
                "valid": True,
                "name": resume.personal.name,
                "education_count": len(resume.education),
                "project_count": len(resume.projects),
                "internship_count": len(resume.internships),
                "warning_count": len(resume.warnings),
            },
            ensure_ascii=False,
        )
    )


def generate(args: argparse.Namespace) -> None:
    source = _path(args.input)
    output = _path(args.output)
    template = _path(args.template) if args.template else ROOT / "templates" / "resume-template-public.docm"
    _require_input(template)
    if output.suffix.lower() not in {".docx", ".docm"}:
        raise ValueError("Generated output must use a .docx or .docm extension")
    resume = _read_json(source)
    _prepare_output(output, args.force)
    generate_resume(template, resume, output)
    print(output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="resume_cli.py",
        description="Local CLI for parsing and formatting Chinese resumes.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    word = subparsers.add_parser("parse-word", help="Parse a DOCX or DOCM resume into JSON")
    word.add_argument("input", help="Input Word resume")
    word.add_argument("--output", required=True, help="Output JSON path")
    word.add_argument("--force", action="store_true", help="Replace an existing output file")
    word.set_defaults(handler=parse_word)

    text_parser = subparsers.add_parser("parse-text", help="Parse a UTF-8 text file into JSON")
    text_parser.add_argument("input", help="Input UTF-8 text file")
    text_parser.add_argument("--engine", choices=("rules", "hybrid"), default="rules")
    text_parser.add_argument("--output", required=True, help="Output JSON path")
    text_parser.add_argument("--force", action="store_true", help="Replace an existing output file")
    text_parser.set_defaults(handler=parse_text)

    check = subparsers.add_parser("validate", help="Validate resume JSON and print a summary")
    check.add_argument("input", help="Input resume JSON")
    check.set_defaults(handler=validate)

    generate_parser = subparsers.add_parser("generate", help="Generate a formatted Word resume")
    generate_parser.add_argument("input", help="Input resume JSON")
    generate_parser.add_argument("--output", required=True, help="Output .docx or .docm path")
    generate_parser.add_argument("--template", help="Compatible DOCM template; defaults to the bundled template")
    generate_parser.add_argument("--force", action="store_true", help="Replace an existing output file")
    generate_parser.set_defaults(handler=generate)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.handler(args)
    except Exception as exc:
        parser.exit(1, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
