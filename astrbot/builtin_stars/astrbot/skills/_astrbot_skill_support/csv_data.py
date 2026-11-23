"""Consistent delimiter detection for spreadsheet inspection and conversion."""

import csv


def parse_delimited_rows(
    text: str, *, suffix: str, delimiter: str | None = None
) -> tuple[str, list[list[str]]]:
    """Parse rows with an optional explicit delimiter or format-specific fallback."""
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",\t;|").delimiter
        except csv.Error:
            delimiter = "\t" if suffix.lower() == ".tsv" else ","
    return delimiter, list(csv.reader(text.splitlines(), delimiter=delimiter))
