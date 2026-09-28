# Formula and validation rules

Use this reference for formula-heavy workbooks and any task where calculated outputs matter.

## Author formulas

1. Create every referenced sheet before assigning cross-sheet formulas.
2. Use formulas for derived values and hardcode only assumptions, raw facts, or explicitly requested fixed outputs.
3. Use `$` anchors deliberately and test the first, middle, and last filled formulas.
4. Quote sheet names in cross-sheet references.
5. Bound lookup and aggregation ranges to the intended data area.
6. Prefer `IFERROR` only when the fallback has a clear business meaning. Do not hide an unexpected error.
7. Keep units consistent across inputs and outputs.

## Understand calculation limits

`openpyxl` preserves and writes formulas but does not calculate them. Loading with `data_only=True` returns cached values last saved by a calculating application; a newly authored formula may have no cached value.

When a calculated result is required:

1. Save the workbook with formulas intact.
2. If LibreOffice or Excel is available, open and save a copy to recalculate it.
3. Reopen the recalculated copy twice: once with `data_only=False` to verify formulas and once with `data_only=True` to inspect cached results.
4. Reconcile important totals independently in Python for high-risk outputs.

Do not treat a missing cached value as proof that a formula is wrong. Do treat a literal error value, `#REF!` inside a formula, a broken chart range, or a missing sheet reference as an error.

## Validate

- Scan all populated cells for Excel error literals.
- Scan formulas and chart series for `#REF!`.
- Confirm table and filter ranges include their headers and intended rows.
- Confirm data validation and conditional-format ranges include future editable rows when requested.
- Check duplicate table and defined-name identifiers.
- Check for formulas that accidentally reference the header row or omit the final data row.
- Review external links and disclose them; do not silently remove them.
- Open macro-enabled files with `keep_vba=True` and preserve their extension.

For financial, legal, medical, or other high-stakes workbooks, independently recalculate representative results and document assumptions and source URLs inside the workbook.
