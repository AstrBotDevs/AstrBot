---
name: spreadsheets
description: Create, read, edit, analyze, convert, chart, and validate spreadsheet files including XLSX, XLSM, XLS, CSV, and TSV. Use when a spreadsheet is a primary input or deliverable, or when tabular data must remain editable and auditable in workbook form.
---

# Work with spreadsheets

Use `openpyxl` for XLSX/XLSM authoring, `xlrd` for legacy XLS reading, `pandas` for substantial data cleaning or analysis, and the standard `csv` module for simple CSV/TSV work. Preserve the source unless the user explicitly requests an in-place edit.

## Choose the workflow

1. For a read-only question, inspect only the relevant sheets, labels, values, formulas, tables, charts, and comments. Do not export a modified copy.
2. For an existing workbook, study its structure and formatting before editing. Apply the smallest local change and extend nearby formulas, validation, conditional formatting, tables, and charts when the edited range requires it.
3. For a new workbook, separate inputs, calculations, and outputs when the task contains derived values. Keep calculations visible and auditable.
4. Save to a new file, reopen it, validate formulas and structure, and render every populated sheet when a renderer is available.

Use the bundled inspector before unfamiliar edits:

```text
python <this-skill-directory>/scripts/inspect_workbook.py input.xlsx
```

## Respect format boundaries

- Use `openpyxl.load_workbook(..., keep_vba=True)` for XLSM files and preserve the `.xlsm` extension. Do not claim that macros were inspected or are safe merely because they were preserved.
- Treat XLS as a legacy read-only source. `xlrd` reads values and basic metadata but does not provide reliable modern editing. Convert the result to XLSX or CSV instead of overwriting the XLS file.
- Preserve CSV/TSV delimiter, quoting, encoding, header order, and typed meaning. Keep identifiers such as ZIP codes and account numbers as text.
- Never change a workbook's file extension without actually converting its format.

## Keep formulas auditable

- Write derived values as formulas rather than hardcoded results.
- Place assumptions and raw inputs in visible cells or dedicated sheets.
- Avoid magic numbers inside formulas. Reference an assumption cell instead.
- Use correct absolute and relative references for fill behavior.
- Quote every cross-sheet name: `='Revenue Model'!B4`, even when the current name has no spaces.
- Prefer bounded ranges over full-column references in calculation-heavy formulas.
- Use helper cells when a formula becomes difficult to understand or audit.
- Add comments to important assumptions and source-backed inputs.
- Check for `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, `#NUM!`, `#NULL!`, and unexpected circular references.

`openpyxl` writes formulas but does not calculate them. If formulas must be recalculated, open and save a copy with LibreOffice or Excel when available, then reopen the result with `data_only=False` and `data_only=True`. Never replace formulas with calculated constants merely to make validation pass. Read [formulas.md](references/formulas.md) for the detailed validation contract.

## Format by meaning

Read [formatting.md](references/formatting.md) before creating or substantially redesigning a workbook.

- Store dates, numbers, currency, and percentages as typed values with explicit number formats.
- Distinguish title, header, input, calculation, output, note, and warning roles consistently.
- Prefer restrained fills and light structural borders. Do not decorate every populated cell with a border.
- Freeze useful headers, enable filters, and use named tables for editable datasets.
- Prefer conditional formatting over one-time manual fills when color represents a value or status.
- Use data validation for editable categorical fields when practical.
- Size columns and rows deliberately. Widen before wrapping, cap very wide columns, and avoid formatting unused ranges.
- Hide gridlines only when explicit formatting already provides structure.

## Use charts deliberately

Read [charts.md](references/charts.md) before creating or editing charts. Create a chart only when it improves comparison, trend, distribution, ranking, progress, or relationship understanding.

- Link chart series to worksheet ranges, not duplicated literal values.
- Keep units explicit and titles focused on one takeaway.
- Place charts in reserved areas without covering source data or controls.
- Verify categories, series orientation, source ranges, point counts, axes, and placement after saving.
- Prefer a compact table over a chart when exact values are the main point.

## Convert CSV or TSV

Use the bundled converter for a clean, typed, filterable workbook:

```text
python <this-skill-directory>/scripts/csv_to_xlsx.py input.csv output.xlsx
python <this-skill-directory>/scripts/csv_to_xlsx.py input.tsv output.xlsx --delimiter tab
```

The converter infers conservative scalar types, freezes the header, creates a table, applies number formats, and caps column widths. Inspect identifiers and locale-specific dates before accepting inferred types.

## Validate and render

Run structural validation after every create or edit operation:

```text
python <this-skill-directory>/scripts/validate_workbook.py output.xlsx
```

When LibreOffice and a PDF renderer are available, render the workbook:

```text
python <this-skill-directory>/scripts/render_workbook.py output.xlsx rendered
```

Inspect every rendered page at normal zoom. Check for clipped headers or values, unexpected blank pages, broken charts, unreadable colors, bad page breaks, missing glyphs, formula errors, and content outside the visible area. Rendering does not prove formula correctness; structural and formula validation remain required.

If rendering is unavailable, report that only structural validation was completed. Do not imply that a workbook passed visual QA.

## Finish

Deliver only the requested workbook or tabular output unless the user asks for previews or intermediates. Report the output path, important sheets or changes, formula/recalculation status, validation performed, and any limitation involving macros, legacy XLS, unsupported formulas, fonts, or rendering.
