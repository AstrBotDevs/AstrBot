"""Structured table parser for the table knowledge base.

Unlike the document parsers that flatten a spreadsheet into a single Markdown
text blob, this parser keeps the row/column structure so each row can be turned
into an independent knowledge unit (Coze-like table knowledge base).
"""

import io
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

SUPPORTED_TABLE_EXTS = {".csv", ".xlsx", ".xls"}


@dataclass
class TableParseResult:
    """Structured parse result for a table file.

    Attributes:
        headers: Column header names (de-duplicated, never empty strings).
        rows: Row data, each row is a list of cell values aligned to ``headers``.
    """

    headers: list[str]
    rows: list[list[str]]


def is_table_file(file_name: str) -> bool:
    """Return whether the given file name is a supported table format."""
    return Path(file_name).suffix.lower() in SUPPORTED_TABLE_EXTS


def _normalize_headers(raw_headers: list[object]) -> list[str]:
    """Build clean, unique header names from raw header cells.

    Args:
        raw_headers: Raw header values parsed from the file.

    Returns:
        A list of non-empty, de-duplicated header strings.
    """
    headers: list[str] = []
    seen: set[str] = set()
    for idx, raw in enumerate(raw_headers):
        name = str(raw).strip() if raw is not None else ""
        if not name or name.lower().startswith("unnamed:"):
            name = f"column_{idx + 1}"

        base_name = name
        counter = 1
        while name in seen:
            name = f"{base_name}_{counter}"
            counter += 1

        seen.add(name)
        headers.append(name)
    return headers


def _read_dataframe(
    file_content: bytes,
    file_name: str,
    header_row: int,
) -> "pd.DataFrame":
    """Read a table file into a DataFrame with all cells as strings.

    Args:
        file_content: Raw file bytes.
        file_name: Original file name used to infer the format.
        header_row: 0-based index of the row that holds the column headers.

    Returns:
        A pandas DataFrame where every cell is a string and blanks are "".

    Raises:
        ValueError: If the file extension is not a supported table format.
    """
    ext = Path(file_name).suffix.lower()
    if ext not in SUPPORTED_TABLE_EXTS:
        raise ValueError(f"暂时不支持的表格格式: {ext}")

    if ext == ".csv":
        # Try common encodings so Chinese spreadsheets exported from Excel work.
        last_error: Exception | None = None
        for encoding in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
            try:
                return pd.read_csv(
                    io.BytesIO(file_content),
                    header=header_row,
                    dtype=str,
                    keep_default_na=False,
                    encoding=encoding,
                )
            except Exception as exc:
                last_error = exc
                continue
        raise ValueError(f"无法解析 CSV 文件，可能是编码问题: {last_error}")

    return pd.read_excel(
        io.BytesIO(file_content),
        header=header_row,
        dtype=str,
        keep_default_na=False,
    )


def parse_table(
    file_content: bytes,
    file_name: str,
    header_row: int = 0,
) -> TableParseResult:
    """Parse a csv/xls/xlsx file into structured headers and rows.

    Args:
        file_content: Raw file bytes.
        file_name: Original file name used to infer the format.
        header_row: 0-based index of the row that holds the column headers.

    Returns:
        TableParseResult: Parsed headers and row values.

    Raises:
        ValueError: If the file format is unsupported or no columns are found.
    """
    df = _read_dataframe(file_content, file_name, header_row)
    if df.shape[1] == 0:
        raise ValueError("未能从表格中解析出任何列。")

    headers = _normalize_headers(list(df.columns))
    rows: list[list[str]] = []
    for record in df.itertuples(index=False, name=None):
        rows.append(["" if cell is None else str(cell).strip() for cell in record])

    return TableParseResult(headers=headers, rows=rows)
