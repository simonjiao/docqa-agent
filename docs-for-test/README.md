# PDF Test Fixtures

This directory holds PDF files used by automated tests and local evaluation.

- `sample_scan.pdf`: current scanned technical-standard sample.
- `sample_text.pdf`: synthetic text-layer PDF.
- `sample_mixed.pdf`: synthetic text + vector drawing PDF.
- `sample_ocr.pdf`: synthetic searchable text + embedded image PDF.
- `sample_form.pdf`: synthetic AcroForm text-field PDF.
- `sample_drawing.pdf`: synthetic vector drawing PDF.
- `sample_protected.pdf`: synthetic password-protected PDF.
- `sample_table_ruled.pdf`: synthetic ruled table with text layer.
- `sample_table_merged_row.pdf`: synthetic ruled table with a row-level merged value cell.
- `sample_table_borderless.pdf`: synthetic borderless table with aligned text columns.
- `sample_text_numbered_notes.pdf`: synthetic numbered narrative page that must not be inferred as a borderless table.
- `sample_chart_image_not_table.pdf`: synthetic embedded chart image with ruling-like grid lines that must remain an image, not a table.
- `sample_table_scanned_low_conf.pdf`: synthetic scanned table with clear grid and intentionally low-confidence text.
- `多智能体平台JD.pdf`: real-world text-layer Chinese/English PDF with Type3/vector glyph signals.

Future fixtures should be added here by PDF type:

- Add domain-specific real-world fixtures when license and privacy constraints allow.
