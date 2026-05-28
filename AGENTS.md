# Project Agent Rules

## Debug Trace Documentation

When debugging this project, keep durable context in `docs/debug_trace.md`. Update it whenever:

- The user points out a setup issue, dependency issue, OCR/model/runtime problem, or expected behavior that affects debugging.
- You encounter an error, warning, missing dependency, environment mismatch, failing command, or workaround while running the project.
- You install or change local tooling, language packs, model/OCR settings, environment variables, ports, or cache behavior.

The tracking document should briefly record:

- Date/time and working directory.
- User-reported symptom or requirement.
- Commands run and important outputs.
- Root cause or current hypothesis.
- Fix or workaround applied.
- Verification command and result.
- Remaining risk or follow-up.

Append new entries to `docs/debug_trace.md` instead of creating topic-specific trace files, unless the user explicitly asks for a separate document.
