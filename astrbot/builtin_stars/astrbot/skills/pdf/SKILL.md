---
name: pdf
description: Read, create, inspect, merge, split, rotate, encrypt, fill, and validate PDF files. Use when the user asks to work with a PDF or convert supported Markdown into a polished PDF in AstrBot.
---

# Work with PDFs

Use `pypdf` for PDF structure operations and validation. Use ReportLab for new page layout. Do not install another PDF library unless the requested feature cannot be implemented safely with the bundled dependencies.

## Follow the workflow

1. Preserve source files unless the user explicitly requests an in-place change.
2. Inspect the input with `pypdf.PdfReader`: page count, metadata, encryption, page sizes, text, annotations, and form fields as relevant.
3. Perform the smallest operation that satisfies the request.
4. Reopen every output with `pypdf` and verify its page count, expected text or fields, and encryption state.
5. Render representative pages when a PDF renderer is available. Inspect the rendered images for clipping, overlap, missing glyphs, broken spacing, and blank pages. If rendering is unavailable, state that only structural validation was completed.

Work in the current workspace unless the user provides another writable location. Keep intermediate files separate from final outputs and remove them when they are no longer needed.

## Read and inspect

Use `astrbot_file_read_tool` for a quick text extraction when it is sufficient. Use Python with `pypdf` when page structure or exact metadata matters:

```python
from pypdf import PdfReader

reader = PdfReader(input_path)
print(len(reader.pages), reader.metadata)
for page_number, page in enumerate(reader.pages, start=1):
    print(page_number, page.mediabox, page.rotation)
    print(page.extract_text() or "")
```

Text extraction does not prove that visual layout is correct. Render with `pdftoppm` when it is available:

```text
pdftoppm -png -r 144 input.pdf rendered/page
```

## Create from Markdown

Prefer the bundled deterministic converter:

```text
python <this-skill-directory>/scripts/markdown_to_pdf.py input.md output.pdf
```

The converter intentionally supports a limited Markdown subset:

- ATX headings (`#` through `######`)
- paragraphs
- flat ordered and unordered lists
- block quotes
- fenced code blocks
- horizontal rules
- `<!-- pagebreak -->`
- bold, italic, inline code, and HTTP(S) or mail links

It does not interpret raw HTML, images, tables, nested lists, footnotes, or arbitrary Markdown extensions. Simplify unsupported content or explain the limitation instead of silently changing meaning.

Font selection follows this order:

1. Use an explicit readable font passed with `--font path/to/font.ttf` or `--font path/to/font.ttc`.
2. Otherwise, search common system locations for a readable Chinese font and verify that it contains every character used by the document.
3. If no suitable system font is available, use ReportLab's built-in Simplified Chinese fallback for supported Latin and Chinese text. The converter stops instead of silently emitting missing glyphs when the fallback cannot represent the input.

When a broader or embedded font is required and no suitable system font is readable, download it into the workspace and pass its path with `--font`. Prefer an official source over an arbitrary font mirror or CDN:

- [MiSans from Xiaomi](https://hyperos.mi.com/font/zh/download/) is an official source that is generally accessible from mainland China. Review its license before use and do not redistribute the font package unless the license permits it.
- [Noto Sans CJK](https://github.com/notofonts/noto-cjk/blob/main/Sans/README.md) is an official open-source fallback with documented download options.

If an official GitHub font URL times out for a user in mainland China, the user may choose one of these third-party proxy prefixes:

- `https://edgeone.gh-proxy.com/`
- `https://hk.gh-proxy.com/`
- `https://gh-proxy.com/`
- `https://gh.dpik.top/`

Append the complete official GitHub URL directly after the prefix. For example:

```text
Official: https://github.com/googlefonts/noto-cjk/raw/main/Sans/Variable/TTF/Subset/NotoSansSC-VF.ttf
Proxy:   https://edgeone.gh-proxy.com/https://github.com/googlefonts/noto-cjk/raw/main/Sans/Variable/TTF/Subset/NotoSansSC-VF.ttf
```

These proxies are not operated by the font project or AstrBot. Their availability and returned content can change. Never send credentials, private repository URLs, or other sensitive data through them. After downloading, verify that the final response used HTTPS, inspect the file type, and compare a checksum with an official checksum when one is published.

Do not download a font silently. Obtain user approval when network access or a new file is required, use HTTPS, and keep the downloaded font in a workspace or temporary directory rather than installing it system-wide.

After conversion, use `pypdf` to confirm the output opens, contains pages, and exposes representative expected text. Render and inspect the first page plus any page with dense content, code, or a page break.

## Transform existing PDFs

Use small `pypdf` scripts directly for ordinary operations.

Merge documents in the requested order:

```python
from pypdf import PdfWriter

writer = PdfWriter()
for path in input_paths:
    writer.append(path)
writer.write(output_path)
```

Split selected pages without modifying the source:

```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader(input_path)
writer = PdfWriter()
for page_index in selected_zero_based_indexes:
    writer.add_page(reader.pages[page_index])
writer.write(output_path)
```

Rotate by a multiple of 90 degrees with `page.rotate(angle)`. Encrypt with `writer.encrypt(password)` only when the user asks, and never echo a password into logs or the final response. Reopen encrypted outputs with the password before reporting success.

## Fill forms

Read [forms.md](references/forms.md) before modifying AcroForms. Preserve interactivity unless the user requests a flattened result. Validate both the canonical field tree and page widget annotations; a successful render alone is not proof that field values were saved.

## Finish

Report the final path, the operation performed, and the validation completed. Mention any unsupported content, unavailable renderer, password requirement, or form ambiguity. Do not claim visual verification unless rendered pages were actually inspected.
