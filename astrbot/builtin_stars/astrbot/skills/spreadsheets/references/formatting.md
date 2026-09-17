# Spreadsheet formatting

Use this reference for new workbooks and substantial redesigns. Preserve an existing workbook's visual language unless the user requests a redesign.

## Establish roles

Choose a small role-based style system before writing cells:

| Role | Default treatment |
|---|---|
| Workbook title | 16-18 pt, bold, dark neutral text, generous spacing |
| Section title | 12-14 pt, bold, restrained accent or neutral fill |
| Table header | Bold, high-contrast fill, centered only when appropriate |
| Input | Light neutral or pale blue fill, unlocked when protection is used |
| Formula | No fill or a subtle neutral fill; keep formulas visible |
| Key output | Bold, explicit number format, light callout fill |
| Note/source | Smaller muted text, URL in cell or comment |
| Warning | Restrained amber or red used only for actionable exceptions |

Use one body font and one optional display font. Prefer fonts commonly available across platforms. For Chinese workbooks, verify the chosen CJK font in the actual render environment (`fc-match "Font Name"` when Fontconfig is available), then inspect the rendered pages for substitution or missing glyphs. Keep body text around 10-11 pt and do not depend on color alone to communicate status.

## Lay out the workbook

- Put a clear title or table header near the top-left of each important sheet.
- Keep assumptions and inputs separate from derived calculations in complex models.
- Place important totals or KPIs where users can find them without scrolling to the bottom.
- Freeze the header row for long tables and freeze identifier columns for wide tables.
- Add filters or an Excel table for editable datasets.
- Avoid merged cells in calculation or filter ranges. Reserve merges for titles or compact presentation labels.
- Set print area, orientation, margins, repeated header rows, and fit-to-width for reports intended to print or render.
- Remove empty default sheets and avoid large formatted-but-empty used ranges.

## Size and align cells

- Left-align descriptive text, right-align numbers, and use intentional alignment for short statuses and dates.
- Widen columns before enabling deep wrapping. Cap descriptive columns around 50-60 characters unless the user requests otherwise.
- Increase row height only enough to reveal wrapped content.
- Use explicit formats such as `#,##0`, `#,##0.00`, `0.0%`, `yyyy-mm-dd`, and currency formats appropriate to the requested currency.
- Preserve identifiers as text when leading zeroes or exact digits matter.

## Tables and conditional formatting

- Use light internal borders and a clearer outside or header boundary.
- Use banded rows only when they materially improve scanning.
- Apply conditional formatting over the intended editable range, not an entire worksheet.
- Verify that formulas used by conditional formatting are anchored correctly at the top-left cell of the applied range.
- Prefer data bars, color scales, or icon sets only when their scale and direction are meaningful.

## Accessibility and usability

- Use descriptive sheet names and unique table names.
- Avoid hidden assumptions and unexplained abbreviations.
- Add comments for important assumptions, unusual formulas, and data provenance.
- Use data validation prompts and error messages for constrained inputs.
- Keep color contrast readable and provide text or numeric cues in addition to color.
