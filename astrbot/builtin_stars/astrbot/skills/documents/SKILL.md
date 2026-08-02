---
name: documents
description: Create, read, edit, review, comment on, sanitize, render, and validate Microsoft Word DOCX documents. Use whenever a DOCX or Word document is a primary input or deliverable, including reports, proposals, forms, templates, tracked revisions, comments, tables, images, headers, footers, and style-preserving edits.
---

# Work with DOCX documents

Use `python-docx` for ordinary creation and editing. Use direct OOXML inspection or small targeted patches only for features that `python-docx` cannot represent safely. Preserve the source unless the user explicitly requests an in-place edit.

## Follow the workflow

1. Inspect the source document's text, styles, sections, tables, images, comments, fields, tracked changes, content controls, headers, footers, and metadata as relevant.
2. For edits, preserve the existing design and apply the smallest local change. Do not rebuild the document merely because creating a new one is easier.
3. For new documents and major rewrites, choose a coherent design system before authoring. Read [styling.md](references/styling.md).
4. Save to a new DOCX, reopen it with `python-docx`, validate the OOXML package, and render every page when LibreOffice and a PDF renderer are available.
5. Inspect the rendered pages and iterate until there is no clipping, overlap, broken table geometry, missing glyph, awkward page break, or header/footer problem.

Use the bundled inspector before unfamiliar edits:

```text
python <this-skill-directory>/scripts/inspect_docx.py input.docx
```

For a quick text-only read, `astrbot_file_read_tool` is sufficient. Text extraction does not prove layout, comments, fields, tracked changes, or images are correct.

## Create and edit with real document structure

- Use Word paragraph styles for Normal, Title, Subtitle, Heading 1, Heading 2, and Heading 3 rather than styling every paragraph directly.
- Use real list styles or numbering definitions. Do not type bullet characters, hyphen prefixes, or manual numbers into ordinary paragraphs.
- Use tables only for genuinely tabular, comparable, or form-like content. Do not package long prose into grids.
- Set page size, margins, orientation, header/footer distance, and section breaks explicitly.
- Size table columns deliberately, enable wrapping, avoid fixed row heights, and repeat header rows when a table spans pages.
- Preserve hyperlinks, relationships, bookmarks, captions, fields, comments, and tracked changes that are outside the requested edit.
- Keep headings with following content and avoid leaving a heading alone at the bottom of a page.
- Use comments for review feedback at the relevant text rather than collecting every note at the end.

## Handle fonts and Chinese text

DOCX files normally record font names rather than embedding the actual fonts. Choose common fonts and expect the opening application to substitute when a font is unavailable.

Set all relevant Word font mappings for each styled run or style:

```python
from docx.oxml.ns import qn

run.font.name = "Noto Sans CJK SC"
fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
fonts.set(qn("w:ascii"), "Noto Sans CJK SC")
fonts.set(qn("w:hAnsi"), "Noto Sans CJK SC")
fonts.set(qn("w:eastAsia"), "Noto Sans CJK SC")
```

Prefer the user's template fonts. For a new cross-platform Chinese document, choose a readable system CJK font, verify that it exists in the actual render environment (`fc-match "Font Name"` when Fontconfig is available), and inspect the rendered output. Do not claim font consistency across devices unless the required font is installed or intentionally embedded with a licensed workflow.

## Preserve advanced features

Read [advanced-ooxml.md](references/advanced-ooxml.md) before changing tracked revisions, fields, content controls, protection, footnotes, endnotes, macros, digital signatures, or document relationships.

- `python-docx` can create and read ordinary comments in current versions, but comments still require structural validation because headless renderers may omit them.
- Tracked changes are not a safe first-class editing surface. Use targeted OOXML patches and preserve author/date data.
- A visible table of contents is often cached field content. Preserve the field instructions and disclose when a calculating Word-compatible application must refresh them.
- Preserve VBA only when explicitly working with a macro-enabled format. Do not rename DOCM to DOCX or claim macros are safe.
- Editing a digitally signed document invalidates its signature. Preserve the source and report this before modifying it.

## Inspect privacy and metadata

Review author, last editor, creation/modification time, comments, tracked-change authors, custom properties, hidden text, document variables, external links, and embedded files before publishing sensitive documents.

Use the bundled scrubber only when the user requests metadata removal:

```text
python <this-skill-directory>/scripts/privacy_scrub.py input.docx sanitized.docx
```

Scrubbing metadata is not content redaction. Search visible text, headers, footers, comments, tracked changes, fields, hyperlinks, images, and embedded objects separately when removing sensitive information.

## Validate and render

Run structural validation after every create or edit operation:

```text
python <this-skill-directory>/scripts/validate_docx.py output.docx
```

When LibreOffice and a PDF renderer are available, render the document:

```text
python <this-skill-directory>/scripts/render_docx.py output.docx rendered
```

Inspect every rendered page at normal zoom. Rendering is strong evidence for layout, fonts, spacing, tables, images, headers, footers, and page breaks. It is not sufficient proof for comments, field instructions, content controls, accessibility metadata, or tracked-change structure.

If rendering is unavailable, perform structural validation and disclose that visual QA was skipped. Do not imply that the document passed a render gate.

## Finish

Deliver only the requested DOCX unless the user asks for rendered pages, PDF, or other intermediates. Report the output path, representative changes, structural checks, visual QA status, and any limitation involving fonts, fields, macros, signatures, comments, revisions, or unsupported OOXML features.
