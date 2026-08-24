---
name: resume-workshop
description: Parse Chinese Word or plain-text resumes into editable structured JSON and generate consistently formatted DOCX/DOCM resumes from the bundled anonymous template. Use for local resume extraction, review, normalization, and Word-format conversion; do not use for PDF, scanned-image, or legacy DOC resumes.
---

# Resume Workshop

Use the bundled local CLI to turn `.docx`, `.docm`, or UTF-8 text into structured resume data, help the user review that data, and generate a formatted Word resume. Keep resume data on the local machine unless the user explicitly asks to send it elsewhere.

## Locate the runtime

Treat the directory containing this `SKILL.md` as `SKILL_DIR`. Use Python 3.11 or newer. Before the first operation, verify the dependencies with:

```bash
python -c "import lxml, PIL, pydantic"
```

If they are missing, install `SKILL_DIR/requirements.txt` into a suitable local virtual environment. The CLI does not require the web frontend or FastAPI server.

## Parse input

- For Word input, run:

  ```bash
  python SKILL_DIR/scripts/resume_cli.py parse-word INPUT.docx --output resume.json
  ```

- For text saved in a UTF-8 file, use deterministic local rules by default:

  ```bash
  python SKILL_DIR/scripts/resume_cli.py parse-text INPUT.txt --engine rules --output resume.json
  ```

- Use `--engine hybrid` only when semantic extraction is useful and a local Ollama `qwen3:4b` service is available. It may fall back to rules. It never requires a remote model.

Read [references/resume-schema.md](references/resume-schema.md) when editing or validating the JSON. Review `warnings`, `other.field_confidence`, and `other.field_sources` when present. Preserve source wording where practical, flag uncertain or missing facts, and never invent dates, employers, schools, results, or contact information.

## Review and generate

Make requested edits in a copy of the parsed JSON. Before generating, check at least the name, phone/email, education periods, experience periods, organization names, roles, and section classification. If material facts are uncertain, show them to the user for confirmation.

Generate a Word file only from reviewed JSON:

```bash
python SKILL_DIR/scripts/resume_cli.py generate resume.json --output formatted-resume.docx
```

The bundled template is `templates/resume-template-public.docm`. Pass `--template PATH` only when the user supplies a compatible template. The generator refuses to overwrite existing files unless `--force` is explicitly supplied; use `--force` only when replacement is intended.

Return the structured JSON and/or generated Word file requested by the user, plus a concise list of unresolved warnings. Remind the user to visually inspect the final Word layout when formatting matters.

## Boundaries

- Supported inputs are `.docx`, `.docm`, and plain UTF-8 text. Do not rename unsupported `.doc`, PDF, image, or scanned resumes to bypass validation.
- The public template is table-layout-specific. A substantially different template requires code adaptation, not just `--template`.
- Resume content is sensitive personal data. Do not commit parsed JSON, generated resumes, photos, or source resumes to Git unless the user explicitly asks and understands they will be published.
