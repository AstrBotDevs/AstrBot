# Advanced DOCX and OOXML operations

Read this reference before modifying features that `python-docx` does not fully support.

## Work safely

1. Preserve the original package.
2. Inspect ZIP members, content types, relationships, and the exact XML elements involved.
3. Patch only the necessary parts and relationships.
4. Write a new package without dropping unrelated members.
5. Reopen with `python-docx`, parse every XML part, run structural validation, and render again.

Use namespace-aware XML handling. Never use regular-expression replacement across XML markup.

## Comments

Validate all of these together:

- `word/comments.xml`
- comment relationships and content-type declarations
- `w:commentRangeStart`, `w:commentRangeEnd`, and `w:commentReference` anchors
- unique comment IDs and preserved author/date values

Headless PDF exports frequently omit comments. Structural validation remains mandatory.

## Tracked changes

Tracked insertions and deletions use `w:ins` and `w:del`, with author, date, and ID metadata. Text inside deletions commonly uses `w:delText` rather than `w:t`.

- Do not flatten revisions unless the user asks to accept or reject them.
- Preserve revision metadata when adding or editing tracked changes.
- Inspect headers, footers, footnotes, and comments in addition to the main document.
- Render the revision view when possible, but also inspect the XML because renderer settings can hide revisions.

## Fields and navigation

TOCs, page numbers, cross-references, captions, and many calculated values use field instructions and cached display text.

- Preserve `w:fldSimple` or complex `w:fldChar` begin/separate/end sequences.
- Preserve bookmarks and relationship targets used by internal links.
- Do not replace a dynamic field with static visible text unless the user requests flattening.
- Disclose when Word or LibreOffice must refresh field results.

## Content controls and forms

Content controls use `w:sdt`. Preserve aliases, tags, data binding, locks, placeholder state, and repeating-section structure. Do not convert a content control to plain text merely to edit its visible value unless the user accepts losing the control.

## Protection, macros, and signatures

- Treat editing restrictions as workflow controls, not encryption.
- Preserve macros only in macro-enabled formats and never execute them during inspection.
- Do not remove or bypass protection without explicit authorization.
- Any document edit can invalidate a digital signature. Preserve the signed source and report the consequence.

## Merge and template operations

DOCX parts can reuse style IDs, numbering IDs, relationship IDs, bookmark IDs, image names, and drawing IDs. A safe merge must remap collisions and preserve referenced parts. Prefer template-based creation or a well-tested merge library over appending raw XML from unrelated packages.
