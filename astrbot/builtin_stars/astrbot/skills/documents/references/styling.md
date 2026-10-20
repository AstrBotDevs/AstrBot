# DOCX styling and layout

Use this reference for new documents and major rewrites. For existing-document edits, preserve the document's style unless the user requests a redesign.

## Choose a design system

Resolve the following values before authoring:

- page size, orientation, margins, and header/footer distance
- body font, East Asian font, base size, line spacing, and paragraph spacing
- title and heading sizes, colors, and keep-with-next behavior
- bullet and numbered-list indentation
- table width, column widths, cell margins, borders, fills, and repeated headers
- callout, caption, source-note, header, and footer treatments

Apply these values through Word styles and reusable table/list definitions. Use direct formatting only for intentional exceptions.

## Recommended neutral preset

For a general professional document when the user provides no template:

| Element | Suggested values |
|---|---|
| Page | A4 or Letter according to locale, portrait |
| Margins | 20-25 mm / 0.8-1.0 in |
| Body | 10.5-11 pt, 1.15-1.3 line spacing, 6-8 pt after |
| Title | 24-28 pt, dark neutral, 12-18 pt after |
| Heading 1 | 16-18 pt, 12-16 pt before, 6-8 pt after |
| Heading 2 | 13-15 pt, 10-12 pt before, 4-6 pt after |
| Heading 3 | 11-12 pt, 8 pt before, 3-4 pt after |
| Table text | 9-10.5 pt with explicit cell margins |
| Header/footer | 8-9 pt muted text, used only when helpful |

For Chinese documents, set both Latin and East Asian fonts on styles. Prefer a system font that can be rendered in the current environment and inspect the final pages for substitution or missing glyphs.

## Use appropriate form factors

- Use prose for background, explanation, and rationale.
- Use numbered steps for sequences and procedures.
- Use bullets for loose factors, requirements, and grouped considerations.
- Use checklists for acceptance criteria and review tasks.
- Use restrained callouts for decisions, warnings, and key takeaways.
- Use tables for repeated comparable records, schedules, budgets, status grids, and forms.
- Use captions and source notes near the figures or tables they describe.

Avoid consecutive dense tables, walls of text, decorative separators, excessive accent colors, and tables used only to position ordinary prose.

## Tables

- Choose widths based on content rather than equal-width defaults.
- Keep short identifiers, dates, statuses, and numeric fields compact.
- Give narrative columns enough width to wrap naturally.
- Set cell margins and vertical alignment explicitly.
- Never use fixed row heights that can clip text.
- Repeat header rows for multi-page tables.
- Keep captions and short source notes with the table when practical.
- Render and inspect every page containing a dense or multi-page table.

## Existing templates

Treat a user-provided template as the design authority. Inspect its styles, theme fonts, numbering, page sections, table styles, headers, footers, and sample content before editing. Extend the nearest matching styles instead of imposing this default preset.
