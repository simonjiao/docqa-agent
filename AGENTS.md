# Project Agent Rules

## 提交规则

除非用户明确要求不要提交，完成变更并验证通过后应及时自动提交。

每次提交的说明使用中文，且总行数不超过 3 行。

## 本地 Python 命令规则

本项目在非交互 shell 中不要使用裸 `python` 命令；运行 Python 脚本、内联调试片段、编译检查和项目验证时，默认使用 `.venv/bin/python`。

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
