"""Exercise real optional metadata and public utility interfaces."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, create_autospec
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from docx import Document
from docx.oxml.ns import qn
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.worksheet.table import Table
from PIL import ImageFont

from astrbot.builtin_stars.astrbot.skills.documents.scripts.inspect_docx import (
    inspect_docx,
)
from astrbot.builtin_stars.astrbot.skills.spreadsheets.scripts import csv_to_xlsx
from astrbot.builtin_stars.astrbot.skills.spreadsheets.scripts.validate_workbook import (
    _validate_xlsx,
)
from astrbot.builtin_stars.builtin_commands.commands.persona import PersonaCommands
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.core.utils.t2i.local_strategy import TextMeasurer


@pytest.mark.parametrize("missing", ["style", "name"])
def test_docx_inspection_accepts_optional_paragraph_style_metadata(
    tmp_path: Path, missing: str
) -> None:
    document = Document()
    document.add_paragraph("Paragraph without complete style metadata")
    normal = document.styles["Normal"]
    if missing == "style":
        normal.delete()
    else:
        name = normal._element.find(qn("w:name"))
        assert name is not None
        normal._element.remove(name)
    source = tmp_path / "optional-style.docx"
    document.save(str(source))

    inspection = inspect_docx(source, sample_paragraphs=1)

    assert inspection["headings"] == []
    assert inspection["paragraph_sample"] == [
        {"style": None, "text": "Paragraph without complete style metadata"}
    ]


def test_csv_conversion_rejects_workbook_without_editable_active_sheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.csv"
    source.write_text("name,value\na,1\n", encoding="utf-8")
    output = tmp_path / "output.xlsx"
    workbook = Workbook(write_only=True)
    monkeypatch.setattr(csv_to_xlsx, "Workbook", lambda: workbook)

    with pytest.raises(ValueError, match="no editable worksheet"):
        csv_to_xlsx.convert_csv_to_xlsx(
            source, output, delimiter=None, sheet_name="Data", has_header=True
        )

    assert not output.exists()
    workbook.close()


def test_xlsx_validator_reports_partial_table_ranges(tmp_path: Path) -> None:
    path = tmp_path / "partial-range.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Name", "Value"])
    sheet.append(["item", 1])
    sheet.add_table(Table(displayName="DataTable", ref="A1:B2"))
    workbook.save(path)
    workbook.close()
    with ZipFile(path) as package:
        members = {name: package.read(name) for name in package.namelist()}
    table = ElementTree.fromstring(members["xl/tables/table1.xml"])
    table.set("ref", "A:B")
    members["xl/tables/table1.xml"] = ElementTree.tostring(table)
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as package:
        for name, content in members.items():
            package.writestr(name, content)
    errors: list[str] = []
    warnings: list[str] = []

    statistics = _validate_xlsx(path, errors, warnings)

    assert statistics["tables"] == 1
    assert errors == ["Table DataTable has an invalid range: A:B"]


@pytest.mark.parametrize("broken", [False, True])
def test_xlsx_chart_sources_remain_validated_after_sdk_narrowing(
    tmp_path: Path, broken: bool
) -> None:
    path = tmp_path / "chart.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([1])
    sheet.append([2])
    chart = BarChart()
    chart.add_data(Reference(sheet, min_col=1, min_row=1, max_row=2))
    if broken:
        chart.series[0].val.numRef.f = "'Sheet'!#REF!"
    sheet.add_chart(chart, "C1")
    workbook.save(path)
    workbook.close()
    errors: list[str] = []
    warnings: list[str] = []

    _validate_xlsx(path, errors, warnings)

    assert errors == (
        ["Chart in 'Sheet' contains a broken source range."] if broken else []
    )


@pytest.mark.asyncio
async def test_persona_list_uses_the_public_manager_contract() -> None:
    manager = create_autospec(PersonaManager, instance=True)
    manager.get_default_persona_v3.return_value = {"name": "Default"}
    manager.get_folder_tree.return_value = [
        {"folder_id": "work", "name": "Work", "children": []}
    ]
    manager.get_all_personas.return_value = [
        SimpleNamespace(persona_id="Writer", folder_id="work"),
        SimpleNamespace(persona_id="General", folder_id=None),
    ]
    context = SimpleNamespace(
        persona_manager=manager,
        conversation_manager=SimpleNamespace(
            get_curr_conversation_id=AsyncMock(return_value=None)
        ),
    )
    event = SimpleNamespace(
        message_str="persona list",
        unified_msg_origin="test:FriendMessage:alice",
        set_result=Mock(),
    )

    await PersonaCommands(context).persona(event)

    manager.get_all_personas.assert_awaited_once_with()
    text = event.set_result.call_args.args[0].chain[0].text
    assert text.index("Work") < text.index("Writer") < text.index("General")
    assert "共 2 个人格" in text


def test_text_measurer_supports_bitmap_fonts_without_getmetrics() -> None:
    font = ImageFont.load_default_imagefont()

    width, height = TextMeasurer.get_text_size("AstrBot", font)

    assert width > 0
    assert height == max(1, font.getbbox("AstrBot")[3] - font.getbbox("AstrBot")[1])


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", [{}, {"kept": "updated", "new": "created"}])
async def test_scope_key_replacement_preserves_unrelated_preferences(
    shared_preferences: SharedPreferences, replacement: dict[str, str]
) -> None:
    store = shared_preferences
    await store.put_async("umo", "old", "route", "removed")
    await store.put_async("umo", "kept", "route", "previous")
    await store.put_async("umo", "old", "theme", "dark")
    await store.put_async("global", "old", "route", "default")

    await store.replace_scope_key("umo", "route", replacement)

    assert await store.get_async("umo", "old", "route") is None
    for scope_id in ("kept", "new"):
        assert await store.get_async("umo", scope_id, "route") == replacement.get(
            scope_id
        )
    assert await store.get_async("umo", "old", "theme") == "dark"
    assert await store.get_async("global", "old", "route") == "default"
    persisted = await store.range_get_async("umo", key="route")
    assert {entry.scope_id: entry.value["val"] for entry in persisted} == replacement
    for scope, key, value in (("umo", "theme", "dark"), ("global", "route", "default")):
        unrelated = await store.db_helper.get_preference(scope, "old", key)
        assert unrelated is not None
        assert unrelated.value == {"val": value}
