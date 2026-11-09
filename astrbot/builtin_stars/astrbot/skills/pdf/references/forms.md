# AcroForm handling

Use this reference only for interactive PDF form tasks.

## Inspect before editing

Check both representations of every field:

1. Read the canonical tree with `PdfReader.get_fields()`.
2. Enumerate `/Widget` annotations in every page's `/Annots` array.
3. Follow `/Parent` and `/Kids` references when resolving field names and values.

A widget can display a value from its appearance stream while the canonical `/AcroForm/Fields` tree contains a different value. If unrelated canonical fields and widgets reuse the same name, report the ambiguity instead of automatically reattaching fields.

## Fill with pypdf

```python
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

reader = PdfReader(input_path)
writer = PdfWriter()
writer.clone_document_from_reader(reader)

writer.reattach_fields()
fields = writer.get_fields() or {}
missing = set(values) - set(fields)
if missing:
    raise ValueError(f"Form fields not found: {sorted(missing)}")

values_to_write = dict(values)
if flatten:
    values_to_write = {
        name: field.get("/V", "/Off" if field.get("/FT") == "/Btn" else "")
        for name, field in fields.items()
    }
    values_to_write.update(values)

writer.update_page_form_field_values(
    None,
    values_to_write,
    auto_regenerate=False,
    flatten=flatten,
)

if flatten:
    writer.remove_annotations(subtypes="/Widget")
    writer.root_object.pop(NameObject("/AcroForm"), None)

with open(output_path, "wb") as output_file:
    writer.write(output_file)
```

Do not flatten a signed document without an explicit decision from the user. Preserve the source and, when useful, retain an interactive copy alongside the flattened copy.

## Validate after writing

For an interactive result:

- Reopen the output and verify every expected field value in `get_fields()`.
- Enumerate widgets again and verify their effective values, including inherited parent values.
- Require updated widgets to have non-empty normal appearance streams under `/AP` and `/N`.
- Render the affected pages to detect stale, clipped, or invisible appearances.

For a flattened result:

- Require zero `/Widget` annotations.
- Require no remaining `/AcroForm` field tree.
- Render the affected pages and confirm the painted values remain visible.
