# Resume JSON schema

The CLI reads and writes one `ResumeData` JSON object. `generate` also accepts an API-style wrapper whose top-level key is `resume`.

## Top-level fields

| Field | Type | Meaning |
|---|---|---|
| `personal` | object | Name, contact details, location, and job-search status |
| `education` | array | Education entries |
| `projects` | array | Project or research entries |
| `internships` | array | Internship or work entries |
| `skills` | array | Categorized skill descriptions |
| `awards` | string array | Awards, certificates, and honors |
| `summary` | string | Short professional summary |
| `self_evaluation` | string | Self-evaluation text |
| `other` | object | Parser metadata such as engine, confidence, sources, and fallback reason |
| `photo_base64` | string | Optional base64-encoded photo; keep private |
| `source_filename` | string | Original filename or text-source label |
| `warnings` | string array | Missing or low-confidence facts requiring review |

## Nested objects

`personal` supports `name`, `age`, `birth_date`, `phone`, `email`, `location`, `job_status`, `target_role`, and `availability`.

Each `education` item supports `period`, `school`, `major`, and `degree`.

Each `projects` or `internships` item supports:

- `period`, `organization`, `role`, and `name`
- `technologies` and `background`
- `highlights`: objects with `label` and `content`
- `results`: an array of strings

Each `skills` item contains `category` and `description`.

## Editing rules

- Keep unknown values empty instead of guessing.
- Preserve array ordering because the Word generator uses that order.
- Keep dates as source-backed strings; the generator does not require a single canonical date format.
- Do not remove parser metadata until review is complete. It is useful for tracing uncertain fields and is not printed in the generated resume.
- Validate edited data before generation with:

  ```bash
  python SKILL_DIR/scripts/resume_cli.py validate resume.json
  ```
