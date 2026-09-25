"""Resource limits shared by backup inspection and restoration."""

import io
import json
import re
import zipfile
from collections.abc import Iterable, Iterator
from contextlib import closing, contextmanager, suppress
from decimal import Decimal
from itertools import groupby
from pathlib import Path
from typing import Any

import ijson

MAX_DIRECTORY_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 40_000
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_DATABASE_JSON_BYTES = 2 * 1024 * 1024 * 1024
MAX_KB_DOCUMENT_JSON_BYTES = 256 * 1024 * 1024
MAX_JSON_RECORD_BYTES = 8 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_EXTRACTED_BYTES = 32 * 1024 * 1024 * 1024
_JSON_PUNCTUATION = re.compile(rb'["\\{}\[\],]')


def check_backup_json_field(data: bytes, remaining: int) -> int:
    """Check a raw database JSON field before constructing its containers.

    Count its compact UTF-8 representation without materializing arrays or maps.
    The enclosing dump, table array and row already consume three nesting levels.

    Args:
        data: Bounded raw JSON bytes from the database.
        remaining: Remaining serialized byte budget for the complete row.

    Returns:
        The field's compact serialized byte count.

    Raises:
        ValueError: The field exceeds the row size or nesting budget.
        ijson.JSONError: The field contains malformed JSON.
    """
    size = 0
    # Each pair records whether a container is a map and its member count.
    containers: list[list[int]] = []
    with io.BytesIO(data) as source:
        for event, value in ijson.basic_parse(source, use_float=False):
            if event in ("end_map", "end_array"):
                size += 1
                containers.pop()
            else:
                if containers and (not containers[-1][0] or event == "map_key"):
                    size += int(containers[-1][1] > 0)  # Comma between members.
                    containers[-1][1] += 1
                if event in ("start_map", "start_array"):
                    size += 1
                    containers.append([int(event == "start_map"), 0])
                    if len(containers) + 3 > MAX_JSON_DEPTH:
                        raise ValueError("Backup JSON nesting exceeds the depth limit")
                else:
                    if event == "map_key":
                        size += 1  # Colon after a map key.
                    if isinstance(value, str) and len(value) > remaining - size:
                        raise ValueError("Backup JSON record exceeds the size limit")
                    if isinstance(value, Decimal):
                        value = float(value)
                    size += len(
                        json.dumps(value, ensure_ascii=False, allow_nan=False).encode(
                            "utf-8"
                        )
                    )
            if size > remaining:
                raise ValueError("Backup JSON record exceeds the size limit")
    return size


def backup_row_batches(rows: Iterable[dict]) -> Iterator[list[dict]]:
    """Bound pending database objects by row count and serialized bytes.

    Args:
        rows: Records from a validated table dump.

    Yields:
        Batches of at most 500 rows and approximately one record budget of bytes.

    Raises:
        ValueError: An individual row exceeds the record budget.
    """
    batch: list[dict] = []
    size = 0
    for row in rows:
        row_size = len(
            json.dumps(
                row, ensure_ascii=False, separators=(",", ":"), default=str
            ).encode("utf-8")
        )
        if row_size > MAX_JSON_RECORD_BYTES:
            raise ValueError("Backup JSON record exceeds the size limit")
        if batch and (len(batch) >= 500 or size + row_size > MAX_JSON_RECORD_BYTES):
            yield batch
            batch = []
            size = 0
        batch.append(row)
        size += row_size
    if batch:
        yield batch


def backup_json_limit(name: str) -> int:
    """Return the expanded size limit for a JSON entry.

    Args:
        name: Archive entry name.

    Returns:
        Maximum expanded bytes allowed for this entry type.
    """
    if name == "manifest.json":
        return MAX_MANIFEST_BYTES
    if name in {"databases/main_db.json", "databases/kb_metadata.json"}:
        return MAX_DATABASE_JSON_BYTES
    if name.startswith("databases/kb_") and name.endswith("/documents.json"):
        return MAX_KB_DOCUMENT_JSON_BYTES
    return MAX_JSON_BYTES


class _RecordLimitedReader:
    """Bound individual records and nesting before feeding the JSON parser.

    Streaming parsers still buffer a complete string token. Scanning punctuation
    in bounded chunks prevents a single huge string or record exhausting memory.
    """

    def __init__(self, source: Any) -> None:
        self.source = source
        self.offset = 0
        self.depth = 0
        self.string_start: int | None = None
        self.escaped_at = -1
        self.record_start: int | None = None
        self.segment_start = 0
        self.safe_end = 0
        self.pending = b""

    def read(self, size: int = -1) -> bytes:
        """Read a chunk and check string, record and nesting budgets.

        Args:
            size: Requested number of bytes, capped to the parser's chunk size.

        Returns:
            At most 64 KiB of validated input bytes.

        Raises:
            ValueError: A token, record or nesting depth exceeds its budget.
        """
        size = min(size, 65536) if size >= 0 else 65536
        if size == 0:
            return b""
        if len(self.pending) >= size:
            chunk, self.pending = self.pending[:size], self.pending[size:]
            return chunk
        chunk = self.source.read(size - len(self.pending))
        for match in _JSON_PUNCTUATION.finditer(chunk):
            pos = self.offset + match.start()
            # Also bound scalars outside a valid table (e.g. a huge root number).
            if pos - self.segment_start > MAX_JSON_RECORD_BYTES:
                raise ValueError("Backup JSON token exceeds the size limit")
            self.segment_start = pos + 1
            if (
                self.record_start is not None
                and pos - self.record_start > MAX_JSON_RECORD_BYTES
            ):
                raise ValueError("Backup JSON record exceeds the size limit")
            symbol = match[0]
            if self.string_start is not None:
                if pos - self.string_start > MAX_JSON_RECORD_BYTES:
                    raise ValueError("Backup JSON string exceeds the size limit")
                if pos == self.escaped_at:
                    continue
                if symbol == b"\\":
                    self.escaped_at = pos + 1
                elif symbol == b'"':
                    self.string_start = None
                    self.safe_end = pos + 1
                continue
            if symbol == b'"':
                self.string_start = pos
            elif symbol in (b"{", b"["):
                self.safe_end = pos + 1
                self.depth += 1
                if self.depth > MAX_JSON_DEPTH:
                    raise ValueError("Backup JSON nesting exceeds the depth limit")
                if self.depth == 2 and symbol == b"[":
                    self.record_start = pos + 1
            elif symbol in (b"}", b"]"):
                self.safe_end = pos + 1
                if self.depth == 2:
                    self.record_start = None
                self.depth -= 1
            elif symbol == b",":
                self.safe_end = pos + 1
                if self.depth == 2:
                    self.record_start = pos + 1
        self.offset += len(chunk)
        if any(
            start is not None and self.offset - start > MAX_JSON_RECORD_BYTES
            for start in (self.record_start, self.string_start, self.segment_start)
        ):
            raise ValueError("Backup JSON token or record exceeds the size limit")
        # End on a complete token whenever possible. The pure-Python ijson
        # lexer otherwise retains preceding input when chunks keep ending inside
        # strings, causing its buffer to grow with the entire database dump.
        combined = self.pending + chunk
        boundary = self.safe_end - (self.offset - len(combined))
        if 0 < boundary < len(combined):
            self.pending = combined[boundary:]
            return combined[:boundary]
        self.pending = b""
        return combined


class BackupTableStream:
    """Replay a table dump one row at a time from the still-open backup.

    The importer validates one pass before modifying anything, then replays the
    same archive for restoration. No full table or cross-component cache is held.
    """

    def __init__(self, archive: zipfile.ZipFile, name: str) -> None:
        self.archive = archive
        self.name = name

    def _records(self) -> Iterator[tuple[str, dict | None]]:
        """Parse table headers and bounded rows, enforcing the dump structure.

        Yields:
            A table name and row, or None for a table header (including empty tables).

        Raises:
            ValueError: The dump is malformed or exceeds a resource limit.
        """

        def parse_events(source: Any) -> Iterator[tuple[str, Any]]:
            """Feed bounded chunks and explicitly close the parser on every exit.

            Args:
                source: Uncompressed archive entry.

            Yields:
                JSON parser events.
            """
            pending = ijson.sendable_list()
            # Preserve arbitrary-sized JSON integers; use_float=True overflows
            # on valid integers with the native backend.
            parser = ijson.basic_parse_coro(pending, use_float=False)
            reader = _RecordLimitedReader(source)
            try:
                while chunk := reader.read(65536):
                    parser.send(chunk)
                    for event, value in pending:
                        yield (
                            event,
                            float(value) if isinstance(value, Decimal) else value,
                        )
                    pending.clear()
                parser.close()
                for event, value in pending:
                    yield event, float(value) if isinstance(value, Decimal) else value
            finally:
                # A resource-limit error can stop in the middle of a token.
                # Preserve that error rather than a secondary incomplete-JSON error.
                with suppress(ijson.JSONError):
                    parser.close()

        with (
            self.archive.open(self.name) as source,
            closing(parse_events(source)) as events,
        ):
            if next(events, None) != ("start_map", None):
                raise ValueError(f"{self.name}: table dump must be an object")
            seen = set()
            for event, table in events:
                if event == "end_map":
                    if next(events, None) is not None:
                        raise ValueError(f"{self.name}: trailing JSON data")
                    return
                if event != "map_key" or len(table) > 256 or table in seen:
                    raise ValueError(f"{self.name}: invalid or duplicate table name")
                seen.add(table)
                if len(seen) > MAX_ENTRIES:
                    raise ValueError("Backup table count exceeds the resource limit")
                if next(events, None) != ("start_array", None):
                    raise ValueError(f"{self.name}: table {table} must be an array")
                yield table, None
                for event, value in events:
                    if event == "end_array":
                        break
                    if event != "start_map":
                        raise ValueError(
                            f"{self.name}: table {table} contains a non-object row"
                        )
                    builder = ijson.common.ObjectBuilder()
                    builder.event(event, value)
                    depth = 1
                    for event, value in events:
                        builder.event(event, value)
                        if event in ("start_map", "start_array"):
                            depth += 1
                        elif event in ("end_map", "end_array"):
                            depth -= 1
                        if depth == 0:
                            break
                    if depth:
                        raise ValueError(f"{self.name}: incomplete row")
                    yield table, builder.value
                    del builder
                else:
                    raise ValueError(f"{self.name}: incomplete table")
            raise ValueError(f"{self.name}: incomplete table dump")

    def items(self) -> Iterator[tuple[str, Iterator[dict]]]:
        """Iterate tables in archive order; consume each row iterator before advancing.

        Yields:
            A table name and its row iterator.
        """
        with closing(self._records()) as records:
            for table, group in groupby(records, key=lambda item: item[0]):
                yield table, (row for _, row in group if row is not None)

    def get(self, key: str, default: Any = ()) -> Iterator[dict]:
        """Replay one table without retaining the other tables in memory.

        Args:
            key: Requested table name.
            default: Rows to yield if the table does not exist.

        Yields:
            Rows from the requested table, or the default iterable.
        """
        with closing(self.items()) as tables:
            for table, rows in tables:
                if table == key:
                    yield from rows
                    return
        yield from default


@contextmanager
def open_backup(path: str | Path, mode: str = "r") -> Iterator[zipfile.ZipFile]:
    """Open a backup after bounding ZIP metadata allocation.

    Args:
        path: Backup file on disk.
        mode: Read mode, or append mode for updating the manifest.

    Yields:
        The open archive, with bounded metadata and expanded size.

    Raises:
        ValueError: The archive exceeds a resource limit.
        zipfile.BadZipFile: The archive has no valid end record.
    """
    with Path(path).open("r+b" if mode == "a" else "rb") as stream:
        # ZipFile eagerly allocates the entire central directory. Use its own
        # ZIP64-aware end-record reader to reject oversized metadata first.
        end = zipfile._EndRecData(stream)
        if end is None:
            raise zipfile.BadZipFile("Missing ZIP end record")
        if (
            end[zipfile._ECD_SIZE] > MAX_DIRECTORY_BYTES
            or end[zipfile._ECD_ENTRIES_TOTAL] > MAX_ENTRIES
        ):
            raise ValueError("Backup ZIP directory exceeds the resource limit")
        stream.seek(0)
        with zipfile.ZipFile(stream, mode) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                raise ValueError("Backup ZIP entry count exceeds the resource limit")
            if sum(entry.file_size for entry in entries) > MAX_EXTRACTED_BYTES:
                raise ValueError("Backup expanded size exceeds the resource limit")
            yield archive


def read_backup_json(archive: zipfile.ZipFile, name: str) -> Any:
    """Read small JSON eagerly, or expose a replayable stream for database dumps.

    Args:
        archive: An open backup archive.
        name: JSON entry to read.

    Returns:
        The decoded JSON value, or a lazy stream of database rows.

    Raises:
        ValueError: The entry is oversized or the manifest is not an object.
        KeyError: The entry is missing.
    """
    limit = backup_json_limit(name)
    if archive.getinfo(name).file_size > limit:
        raise ValueError(f"Backup JSON {name} exceeds the size limit ({limit} bytes)")
    if name.startswith("databases/"):
        return BackupTableStream(archive, name)
    with archive.open(name) as source:
        content = source.read(limit + 1)
    if len(content) > limit:
        raise ValueError(f"Backup JSON {name} exceeds the size limit ({limit} bytes)")
    value = json.loads(content)
    if name == "manifest.json" and not isinstance(value, dict):
        raise ValueError("Backup manifest must be a JSON object")
    return value
