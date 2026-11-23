"""Behavioral contracts for the strict, source-based quality gate."""

import errno
from dataclasses import replace
from textwrap import dedent, indent

import pytest

from tests import test_code_quality_typing as gate

FIVE_STEPS = """\
text = str(value)
text = text.strip()
text = text.casefold()
text = text.replace("-", "_")
return text
"""

TEN_STEPS = """\
text = str(value)
text = text.strip()
text = text.casefold()
text = text.replace("-", "_")
text = text.replace(" ", "_")
text = text.removeprefix("_")
text = text.removesuffix("_")
text = text.rstrip(".")
text = text.lstrip(".")
return text
"""


def function_source(name: str, body: str) -> str:
    """Wrap an explicit test fixture in a typed function."""
    return f"def {name}(value: object) -> str:\n" + indent(
        dedent(body).strip() + "\n", "    "
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "from typing import Any, cast\n"
            "def convert(value: object):\n"
            "    return cast(Any, value)\n",
            1,
        ),
        (
            "import typing as t\n"
            "def convert(value: object):\n"
            "    return t.cast(t.Any, value)\n",
            1,
        ),
        (
            "from typing import Any as Dynamic, cast as unchecked\n"
            "def convert(value: object):\n"
            "    return unchecked(Dynamic, value)\n",
            1,
        ),
        (
            "from typing import Any, cast\n"
            "example = 'cast(Any, value)'\n"
            "# cast(Any, example)\n",
            0,
        ),
        (
            "from typing import Any\n"
            "def cast(kind: object, value: object):\n"
            "    return value\n"
            "result = cast(Any, object())\n",
            0,
        ),
        (
            "from typing import Any, cast\n"
            "def local(cast, value: object):\n"
            "    return cast(Any, value)\n"
            "def global_call(value: object):\n"
            "    return cast(Any, value)\n",
            1,
        ),
        (
            "from typing import Any, cast\n"
            "def convert(value: object):\n"
            "    Any = str\n"
            "    return cast(Any, value)\n",
            0,
        ),
        (
            "import typing as t\n"
            "def convert(t, value: object):\n"
            "    return t.cast(t.Any, value)\n",
            0,
        ),
        (
            "from typing_extensions import Any as Dynamic, cast as unchecked\n"
            "def convert(value: object):\n"
            "    return unchecked(Dynamic, value)\n",
            1,
        ),
        (
            "from typing import Any, cast\n"
            "def convert(value: object):\n"
            "    result = cast(Any, value)\n"
            "    cast = lambda kind, item: item\n"
            "    return result\n",
            0,
        ),
        (
            "from typing import Any as Dynamic, cast as unchecked\n"
            "def convert(value: object):\n"
            "    result = unchecked(Dynamic, value)\n"
            "    Dynamic = str\n"
            "    return result\n",
            0,
        ),
        (
            "from typing import Any, cast\n"
            "first = cast(Any, object())\n"
            "cast = lambda kind, item: item\n"
            "second = cast(Any, object())\n",
            1,
        ),
        (
            "import typing as t\nt = object()\nresult = t.cast(t.Any, object())\n",
            0,
        ),
        (
            "from typing import Any, cast\n"
            "def cast(kind: object, value: object):\n"
            "    return value\n"
            "result = cast(Any, object())\n",
            0,
        ),
    ],
)
def test_cast_any_uses_real_typing_bindings(source, expected):
    result = gate.scan_sources({"bindings.py": source})
    assert not result.errors
    assert result.counts.cast_any == expected


def test_ignore_directives_are_comments_and_multi_codes_count_once():
    result = gate.scan_sources(
        {
            "directives.py": dedent(
                """\
                first = object()  # type: ignore[attr-defined, assignment]
                second = object()  # type: ignore[arg-type]
                # type: ignore[unresolved-import, class-alias]
                example = "# type: ignore[attr-defined]"
                # Documentation mentions type: ignore[attr-defined].
                """
            )
        }
    )
    assert not result.errors
    assert result.counts.type_ignore == 3
    assert result.counts.bad_type_ignore == 2
    assert result.score == 92.5


def test_bare_except_uses_exception_handlers_not_text():
    result = gate.scan_sources(
        {
            "exceptions.py": dedent(
                """\
                example = "except:"
                # except:
                try:
                    run()
                except:  # This real handler must still be counted.
                    recover()
                try:
                    run()
                except Exception:
                    recover()
                """
            )
        }
    )
    assert not result.errors
    assert result.counts.bare_except == 1


@pytest.mark.parametrize("same_file", [False, True])
def test_five_executable_lines_are_detected_within_and_across_files(same_file):
    first = function_source("first", FIVE_STEPS)
    second = function_source("second", FIVE_STEPS)
    sources = (
        {"both.py": first + "\n" + second}
        if same_file
        else {"first.py": first, "second.py": second}
    )
    result = gate.scan_sources(sources)
    assert not result.errors
    assert result.counts.duplicate_blocks == 1
    assert result.score == 98
    assert len(result.duplicates) == 1
    duplicate = result.duplicates[0]
    assert duplicate.executable_lines == 5
    assert len(duplicate.locations) == 2
    assert {location.path for location in duplicate.locations} == set(sources)
    for location in duplicate.locations:
        assert 1 <= location.line <= location.end_line


@pytest.mark.parametrize("copies", [2, 3])
def test_maximal_ten_line_clone_is_charged_once_per_extra_copy(copies):
    result = gate.scan_sources(
        {
            f"copy_{index}.py": function_source(f"copy_{index}", TEN_STEPS)
            for index in range(copies)
        }
    )
    assert not result.errors
    assert result.counts.duplicate_blocks == copies - 1
    assert result.score == 100 - 2 * (copies - 1)
    assert len(result.duplicates) == 1
    assert result.duplicates[0].executable_lines == 10
    assert len(result.duplicates[0].locations) == copies


def test_nested_executable_block_is_not_charged_again_for_its_body():
    nested = "if value is not None:\n" + indent(FIVE_STEPS, "    ")
    result = gate.scan_sources(
        {
            "first.py": function_source("first", nested + 'return "first fallback"\n'),
            "second.py": function_source(
                "second", nested + 'return "second fallback"\n'
            ),
        }
    )
    assert not result.errors
    assert result.counts.duplicate_blocks == 1
    assert len(result.duplicates) == 1
    assert result.duplicates[0].executable_lines >= 5


def test_nested_function_logic_is_scanned_without_its_definition_wrapper():
    nested = "def helper(value: object) -> str:\n" + indent(FIVE_STEPS, "    ")
    nested += "return helper(value)\n"
    result = gate.scan_sources(
        {
            "first.py": function_source("first", nested),
            "second.py": function_source("second", nested),
        }
    )
    assert not result.errors
    assert result.counts.duplicate_blocks == 1
    assert len(result.duplicates) == 1
    block = result.duplicates[0]
    assert block.executable_lines == 5
    assert all(
        location.line == 3 and location.end_line == 7 for location in block.locations
    )


def test_short_nested_definitions_do_not_combine_into_one_executable_block():
    nested = "".join(
        f"def helper_{index}() -> int:\n    return {index}\n" for index in range(5)
    )
    nested += "return str(value)\n"
    result = gate.scan_sources(
        {
            "first.py": function_source("first", nested),
            "second.py": function_source("second", nested),
        }
    )
    assert not result.errors
    assert result.counts.duplicate_blocks == 0
    assert not result.duplicates


@pytest.mark.parametrize(
    "source",
    [
        "import abc\nimport asyncio\nimport collections\nimport json\nimport typing\n",
        'VALUES = {\n    "a": 1,\n    "b": 2,\n    "c": 3,\n    "d": 4,\n}\n',
        '"""\nparse()\nvalidate()\ntransform()\nstore()\nfinish()\n"""\n',
        function_source(
            "render",
            "return format_payload(\n"
            '    value,\n    "a",\n    "b",\n    "c",\n    "d",\n)\n',
        ),
        "def convert(\n    first: int,\n    second: int,\n    third: int,\n"
        "    fourth: int,\n    fifth: int,\n) -> None:\n    pass\n",
        function_source(
            "convert",
            '"""Documented conversion.\nWith several\nlines of\ndetails.\n"""\n'
            "import json\n"
            'options = {"a": 1, "b": 2, "c": 3}\n'
            "# A comment does not make this a fifth executable line.\n"
            "text = str(value)\ntext = text.strip()\n"
            "text = text.casefold()\nreturn text\n",
        ),
    ],
    ids=[
        "imports",
        "static-data",
        "docstring",
        "multiline-call",
        "signature",
        "four-lines",
    ],
)
def test_scaffolding_and_formatting_do_not_create_five_lines_of_logic(source):
    result = gate.scan_sources({"first.py": source, "second.py": source})
    assert not result.errors
    assert result.counts.duplicate_blocks == 0
    assert not result.duplicates


def test_embedded_data_values_remain_part_of_exact_fingerprint():
    body = (
        "text = str(value)\n"
        'options = {"separator": "-"}\n'
        "text = text.strip()\n"
        "text = text.casefold()\n"
        'text = text.replace(options["separator"], "_")\n'
        "return text\n"
    )
    result = gate.scan_sources(
        {
            "first.py": function_source("first", body),
            "second.py": function_source("second", body.replace('"-"', '"/"')),
        }
    )
    assert not result.errors
    assert result.counts.duplicate_blocks == 0


def test_fingerprints_do_not_collide_after_a_shared_sixty_character_prefix():
    shared = FIVE_STEPS.replace(
        "str(value)",
        "normalize_with_a_deliberately_long_and_identical_function_name_for_testing(value)",
    )
    first = shared.replace("return text", 'return text + "first"')
    second = shared.replace("return text", 'return text + "second"')
    result = gate.scan_sources(
        {
            "a.py": function_source("a", first),
            "b.py": function_source("b", first),
            "c.py": function_source("c", second),
            "d.py": function_source("d", second),
        }
    )
    assert not result.errors
    assert result.counts.duplicate_blocks == 2
    assert len(result.duplicates) == 2
    assert all(len(block.locations) == 2 for block in result.duplicates)


def test_same_line_statements_do_not_meet_five_source_line_threshold():
    one_line = "; ".join(FIVE_STEPS.strip().splitlines())
    result = gate.scan_sources(
        {
            "first.py": function_source("first", one_line),
            "second.py": function_source("second", one_line),
        }
    )
    assert not result.errors
    assert result.counts.duplicate_blocks == 0


def test_overlapping_windows_inside_one_occurrence_are_not_extra_copies():
    result = gate.scan_sources(
        {"repeated.py": function_source("repeat", "consume(value)\n" * 6)}
    )
    assert not result.errors
    assert result.counts.duplicate_blocks == 0


def test_duplicate_reporting_is_independent_of_input_mapping_order():
    sources = {
        "z.py": function_source("last", TEN_STEPS),
        "a.py": function_source("first", TEN_STEPS),
        "m.py": function_source("middle", TEN_STEPS),
    }
    forward = gate.scan_sources(sources)
    reverse = gate.scan_sources(dict(reversed(list(sources.items()))))
    assert forward.counts.duplicate_blocks == reverse.counts.duplicate_blocks == 2
    assert forward.score == reverse.score == 96
    reports = [
        [
            (
                block.executable_lines,
                tuple(
                    (location.path, location.line, location.end_line)
                    for location in block.locations
                ),
            )
            for block in result.duplicates
        ]
        for result in (forward, reverse)
    ]
    assert reports[0] == reports[1]
    assert forward.errors == reverse.errors == ()


@pytest.mark.parametrize(
    ("cast_any", "type_ignore", "bad_ignore", "bare_except", "duplicates", "expected"),
    [
        (0, 0, 0, 0, 0, 100.0),
        (0, 0, 0, 0, 10, 80.0),
        (0, 0, 0, 0, 11, 78.0),
        (0, 1, 0, 0, 10, 79.5),
        (1, 1, 1, 1, 1, 93.0),
        (101, 0, 0, 0, 0, 0.0),
    ],
)
def test_score_uses_full_documented_costs(
    cast_any, type_ignore, bad_ignore, bare_except, duplicates, expected
):
    assert (
        gate._calculate_score(
            cast_any, type_ignore, bad_ignore, bare_except, duplicates
        )
        == expected
    )


@pytest.mark.parametrize(
    ("casts", "ignore", "expected_score", "passes"),
    [(20, False, 80.0, True), (22, False, 78.0, False), (20, True, 79.5, False)],
)
def test_gate_requires_eighty_without_skipping(
    monkeypatch, casts, ignore, expected_score, passes
):
    source = "from typing import Any, cast\n" + "\n".join(
        f"value_{index} = cast(Any, object())" for index in range(casts)
    )
    if ignore:
        source += "\nvalue = object()  # type: ignore[arg-type]\n"
    result = gate.scan_sources({"threshold.py": source})
    assert not result.errors
    assert result.score == expected_score
    monkeypatch.setattr(gate, "_scan_for_patterns", lambda: result)
    check = gate.TestCodeQualityTyping().test_type_safety_score
    try:
        if passes:
            check()
        else:
            with pytest.raises(AssertionError):
                check()
    except pytest.skip.Exception as error:
        pytest.fail(f"The quality gate must not skip: {error}", pytrace=False)


def test_syntax_errors_are_reported_and_fail_the_gate(monkeypatch):
    result = gate.scan_sources({"broken.py": "def broken(:\n    pass\n"})
    assert result.errors
    assert all(error.path == "broken.py" and error.message for error in result.errors)
    monkeypatch.setattr(gate, "_scan_for_patterns", lambda: result)
    try:
        with pytest.raises(AssertionError):
            gate.TestCodeQualityTyping().test_type_safety_score()
    except pytest.skip.Exception as error:
        pytest.fail(
            f"Invalid source must fail the quality gate: {error}", pytrace=False
        )


def call_steps(length: int) -> str:
    return "".join(f"step_{index}(value)\n" for index in range(length))


def clone_sources(length: int, copies: int = 2) -> dict[str, str]:
    return {
        f"copy_{index}.py": function_source(f"copy_{index}", call_steps(length))
        for index in range(copies)
    }


def assert_invalid_gate(monkeypatch, result):
    assert result.assessment is None
    assert result.score_v2 is None
    report = gate._format_report(result)
    assert "INVALID (score=None)" in report
    assert "Coverage: discovered=" in report
    monkeypatch.setattr(gate, "_scan_for_patterns", lambda: result)
    with pytest.raises(AssertionError):
        gate.TestCodeQualityTyping().test_type_safety_score()


@pytest.mark.parametrize(
    ("length", "ordinary_ignore", "units", "passes"),
    [
        (20, False, 200, True),
        (19, True, 201, False),
    ],
)
def test_v2_integer_boundary_ignores_rounded_display(
    monkeypatch, length, ordinary_ignore, units, passes
):
    sources = clone_sources(length)
    sources["debt.py"] = "from typing import Any, cast\n" + "".join(
        f"unchecked_{index} = cast(Any, object())\n" for index in range(12)
    )
    if ordinary_ignore:
        sources["debt.py"] += "value = object()  # type: ignore[arg-type]\n"
    result = gate.scan_sources(sources)
    assessment = result.assessment
    assert assessment is not None
    assert result.score >= 80
    assert assessment.units == units
    assert round(assessment.score) == 80
    assert assessment.passes is passes
    monkeypatch.setattr(gate, "_scan_for_patterns", lambda: result)
    if passes:
        gate.TestCodeQualityTyping().test_type_safety_score()
    else:
        with pytest.raises(AssertionError):
            gate.TestCodeQualityTyping().test_type_safety_score()


def test_legacy_threshold_remains_an_independent_assertion(monkeypatch):
    result = gate.scan_sources({"clean.py": "perform_work()\n"})
    assert result.assessment is not None and result.assessment.passes
    monkeypatch.setattr(gate, "_calculate_score", lambda *_counts: 79.0)
    monkeypatch.setattr(gate, "_scan_for_patterns", lambda: result)
    with pytest.raises(AssertionError):
        gate.TestCodeQualityTyping().test_type_safety_score()


@pytest.mark.parametrize(
    ("directive", "units"),
    [
        ("arg-type", 5),
        ("attr-defined", 35),
        ("attr-defined, assignment", 35),
    ],
)
def test_bad_ignore_is_a_subset_with_one_total_cost(directive, units):
    result = gate.scan_sources(
        {"ignore.py": f"value = object()  # type: ignore[{directive}]\n"}
    )
    assert result.counts.type_ignore == 1
    assert result.assessment is not None
    assert result.assessment.units == units


@pytest.mark.parametrize(
    ("changes", "extra_statements", "increase"),
    [
        ({"cast_any": 3}, 0, 10),
        ({"type_ignore": 4}, 0, 5),
        ({"bad_type_ignore": 2}, 0, 30),
        ({"type_ignore": 4, "bad_type_ignore": 2}, 0, 35),
        ({"bare_except": 2}, 0, 20),
        ({}, 1, 4),
        ({"duplicate_blocks": 2}, 5, 20),
    ],
)
def test_each_additional_debt_event_increases_integer_cost(
    changes, extra_statements, increase
):
    counts = gate.PatternCounts(2, 3, 1, 1, 1)
    initial = gate._calculate_debt_units(counts, 5)
    changed = gate._calculate_debt_units(
        replace(counts, **changes), 5 + extra_statements
    )
    assert changed - initial == increase
    assert gate.QualityDebt(changed, 100).score < gate.QualityDebt(initial, 100).score


def test_v2_pass_cannot_relax_the_legacy_debt_budget():
    for casts in (0, 1, 10, 20):
        for ignores in (0, 1, 4):
            for bad in range(ignores + 1):
                for bare in (0, 1, 10):
                    for copies in (0, 1, 5):
                        for extent in (5, 12):
                            counts = gate.PatternCounts(
                                casts, ignores, bad, bare, copies
                            )
                            units = gate._calculate_debt_units(counts, copies * extent)
                            legacy = gate._calculate_score(
                                casts, ignores, bad, bare, copies
                            )
                            assert units / 10 >= 100 - legacy
                            if units <= gate.MAX_DEBT_UNITS:
                                assert legacy >= gate.MIN_SCORE


@pytest.mark.parametrize("length", [5, 10, 19])
@pytest.mark.parametrize("copies", [2, 3, 4])
def test_clone_debt_scales_with_actual_extent_and_extra_copies(length, copies):
    result = gate.scan_sources(clone_sources(length, copies))
    assert result.counts.duplicate_blocks == copies - 1
    assert len(result.duplicates) == 1
    block = result.duplicates[0]
    assert block.executable_statements == length
    assert result.redundant_statements == (copies - 1) * length
    assert result.coverage.executable_statements == copies * length
    assert result.assessment is not None
    assert result.assessment.units == 4 * (copies - 1) * length
    assert result.assessment.debt >= 2 * (copies - 1)


def test_compound_clone_counts_eligible_nested_statements_once():
    body = "if value is not None:\n" + indent(call_steps(5), "    ")
    sources = {
        "first.py": function_source("first", body + 'return "first"\n'),
        "second.py": function_source("second", body + 'return "second"\n'),
    }
    result = gate.scan_sources(sources)
    assert len(result.duplicates) == 1
    assert result.duplicates[0].executable_lines == 6
    assert result.duplicates[0].executable_statements == 6
    assert result.redundant_statements == 6
    assert result.coverage.executable_statements == 14


def test_ast_weight_is_stable_across_layouts_that_meet_existing_admission():
    lines = call_steps(10).splitlines()
    compact = "\n".join(
        "; ".join(lines[index : index + 2]) for index in range(0, 10, 2)
    )
    plain = gate.scan_sources(clone_sources(10))
    mixed = gate.scan_sources(
        {
            "first.py": function_source("first", call_steps(10)),
            "second.py": function_source("second", compact),
        }
    )
    assert plain.duplicates[0].executable_lines == 10
    assert mixed.duplicates[0].executable_lines == 5
    assert plain.redundant_statements == mixed.redundant_statements == 10
    assert (
        plain.coverage.executable_statements
        == mixed.coverage.executable_statements
        == 20
    )
    assert plain.assessment == mixed.assessment


def test_comments_docstrings_literals_and_line_wrapping_do_not_inflate_weight():
    plain = gate.scan_sources(clone_sources(5))
    padded = (
        '"""A descriptive\nmultiline\ndocstring.\n"""\n'
        "import json\n"
        'OPTIONS = {"constant": [1, 2, 3]}\n'
        "# Padding contributes no executable statement.\n\n"
        + call_steps(5).replace("step_0(value)", "step_0(\n    value,\n)")
    )
    result = gate.scan_sources(
        {
            "first.py": function_source("first", padded),
            "second.py": function_source("second", padded),
        }
    )
    assert result.redundant_statements == plain.redundant_statements == 5
    assert (
        result.coverage.executable_statements
        == plain.coverage.executable_statements
        == 10
    )
    assert result.assessment == plain.assessment


def test_partitioning_an_admitted_clone_preserves_its_total_statement_debt():
    whole = gate.scan_sources(clone_sources(10))
    steps = call_steps(10).splitlines(keepends=True)
    partitioned = gate.scan_sources(
        {
            f"copy_{index}.py": (
                function_source(f"first_{index}", "".join(steps[:5]))
                + "\n"
                + function_source(f"second_{index}", "".join(steps[5:]))
            )
            for index in range(2)
        }
    )
    assert whole.counts.duplicate_blocks == 1
    assert partitioned.counts.duplicate_blocks == 2
    assert whole.redundant_statements == partitioned.redundant_statements == 10
    assert whole.assessment == partitioned.assessment


def test_shorter_fresh_copy_reuses_anchor_without_charging_covered_regions():
    sources = clone_sources(10)
    sources["short.py"] = function_source("short", call_steps(5))
    result = gate.scan_sources(sources)
    assert result.counts.duplicate_blocks == 2
    assert len(result.duplicates) == 2
    assert result.redundant_statements == 15
    assert result.coverage.executable_statements == 25
    assert result.assessment is not None and result.assessment.units == 60


def test_overlapping_and_nested_candidates_cannot_increase_clone_debt():
    overlap = gate.scan_sources(
        {"one.py": function_source("one", "consume(value)\n" * 6)}
    )
    assert overlap.redundant_statements == 0
    nested = "if value:\n" + indent(call_steps(5), "    ")
    result = gate.scan_sources(
        {
            "one.py": function_source("one", nested),
            "two.py": function_source("two", nested),
        }
    )
    assert len(result.duplicates) == 1
    assert result.redundant_statements == 6


def test_adding_unrelated_clean_code_only_changes_diagnostic_density():
    sources = clone_sources(51)
    before = gate.scan_sources(sources)
    sources["clean.py"] = "".join(
        f"clean_result_{index} = distinct_operation_{index}()\n" for index in range(100)
    )
    after = gate.scan_sources(sources)
    assert before.assessment is not None and after.assessment is not None
    assert before.assessment.units == after.assessment.units == 204
    assert before.score_v2 == after.score_v2
    assert not before.assessment.passes and not after.assessment.passes
    assert before.score == after.score
    assert (
        after.coverage.executable_statements
        == before.coverage.executable_statements + 100
    )
    assert after.assessment.density < before.assessment.density


@pytest.mark.parametrize(
    "sources",
    [
        {},
        {"empty.py": ""},
        {"declarations.py": '"""Documentation."""\nimport json\nVALUES = [1, 2, 3]\n'},
    ],
)
def test_empty_executable_coverage_has_no_v2_score(monkeypatch, sources):
    result = gate.scan_sources(sources)
    assert result.coverage.discovered_files == len(sources)
    assert result.coverage.parsed_files == len(sources)
    assert result.coverage.executable_statements == 0
    assert_invalid_gate(monkeypatch, result)


def test_parse_failure_invalidates_score_of_other_clean_sources(monkeypatch):
    result = gate.scan_sources({"clean.py": "work()\n", "broken.py": "def broken(:\n"})
    assert result.coverage == gate.ScanCoverage(2, 2, 1, 1, 1)
    assert result.errors and result.errors[0].path == "broken.py"
    assert_invalid_gate(monkeypatch, result)


def test_tokenization_failure_is_reported_even_after_successful_parse(monkeypatch):
    original = gate.tokenize.generate_tokens

    def interrupt_tokens(readline):
        for token in original(readline):
            if token.type == gate.tokenize.COMMENT and "interrupt" in token.string:
                raise gate.tokenize.TokenError("Interrupted tokenization", token.start)
            yield token

    monkeypatch.setattr(gate.tokenize, "generate_tokens", interrupt_tokens)
    result = gate.scan_sources(
        {
            "clean.py": "work()\n",
            "interrupted.py": "pending = object()  # interrupt\n",
        }
    )
    assert result.coverage == gate.ScanCoverage(2, 2, 2, 1, 1)
    assert result.errors and "Interrupted tokenization" in result.errors[0].message
    assert_invalid_gate(monkeypatch, result)


def test_failed_file_read_remains_in_discovered_coverage(monkeypatch, tmp_path):
    (tmp_path / "clean.py").write_text("work()\n")
    (tmp_path / "unreadable.py").write_text("pending()\n")
    original = gate.tokenize.open

    def read_source(path):
        if path.name == "unreadable.py":
            raise PermissionError(errno.EACCES, "Access denied", str(path))
        return original(path)

    monkeypatch.setattr(gate, "ASTRBOT_ROOT", tmp_path)
    monkeypatch.setattr(gate.tokenize, "open", read_source)
    result = gate._scan_for_patterns()
    assert result.coverage == gate.ScanCoverage(2, 1, 1, 1, 1)
    assert result.errors and "unreadable.py" in result.errors[0].path
    assert_invalid_gate(monkeypatch, result)


def test_unknown_file_encoding_invalidates_coverage(monkeypatch, tmp_path):
    (tmp_path / "clean.py").write_text("work()\n")
    (tmp_path / "encoding.py").write_bytes(
        b"# coding: invalid-python-encoding\nwork()\n"
    )
    monkeypatch.setattr(gate, "ASTRBOT_ROOT", tmp_path)
    result = gate._scan_for_patterns()
    assert result.coverage == gate.ScanCoverage(2, 1, 1, 1, 1)
    assert result.errors and "encoding.py" in result.errors[0].path
    assert_invalid_gate(monkeypatch, result)


def test_directory_discovery_failure_invalidates_other_successful_files(
    monkeypatch, tmp_path
):
    (tmp_path / "clean.py").write_text("work()\n")

    def partial_walk(root, *, onerror, followlinks):
        assert root == tmp_path and followlinks is False
        onerror(PermissionError(errno.EACCES, "Access denied", str(root / "blocked")))
        yield str(root), ["blocked"], ["clean.py"]

    monkeypatch.setattr(gate, "ASTRBOT_ROOT", tmp_path)
    monkeypatch.setattr(gate.os, "walk", partial_walk)
    result = gate._scan_for_patterns()
    assert result.coverage == gate.ScanCoverage(1, 1, 1, 1, 1, discovery_complete=False)
    assert result.errors and "blocked" in result.errors[0].path
    assert_invalid_gate(monkeypatch, result)


@pytest.mark.parametrize("missing", [False, True])
def test_missing_or_empty_production_tree_cannot_earn_a_score(
    monkeypatch, tmp_path, missing
):
    root = tmp_path / "missing" if missing else tmp_path
    monkeypatch.setattr(gate, "ASTRBOT_ROOT", root)
    result = gate._scan_for_patterns()
    assert result.coverage.discovered_files == result.coverage.parsed_files == 0
    assert result.errors
    assert result.coverage.discovery_complete is not missing
    assert_invalid_gate(monkeypatch, result)


@pytest.mark.parametrize(
    ("counts", "redundant"),
    [
        (gate.PatternCounts(-1, 0, 0, 0, 0), 0),
        (gate.PatternCounts(0, -1, 0, 0, 0), 0),
        (gate.PatternCounts(0, 0, -1, 0, 0), 0),
        (gate.PatternCounts(0, 0, 0, -1, 0), 0),
        (gate.PatternCounts(0, 0, 0, 0, -1), 0),
        (gate.PatternCounts(0, 0, 0, 0, 0), -1),
        (gate.PatternCounts(0, 0, 1, 0, 0), 0),
        (gate.PatternCounts(0, 1, 2, 0, 0), 0),
        (gate.PatternCounts(0, 0, 0, 0, 1), 4),
        (gate.PatternCounts(0, 0, 0, 0, 0), 5),
    ],
)
def test_negative_or_impossible_debt_counts_are_rejected(counts, redundant):
    with pytest.raises(ValueError):
        gate._calculate_debt_units(counts, redundant)


@pytest.mark.parametrize("value", [True, 1.5, float("nan"), float("inf"), "1", None])
def test_debt_units_require_real_integer_counts(value):
    with pytest.raises(ValueError):
        gate._calculate_debt_units(gate.PatternCounts(value, 0, 0, 0, 0), 0)


@pytest.mark.parametrize(
    "changes",
    [
        {"discovered_files": -1},
        {"read_files": 2},
        {"parsed_files": 2},
        {"tokenized_files": 2},
        {"executable_statements": -1},
        {"discovery_complete": 1},
    ],
)
def test_impossible_coverage_counts_are_rejected(changes):
    with pytest.raises(ValueError):
        replace(gate.ScanCoverage(1, 1, 1, 1, 1), **changes)


def test_executable_count_requires_a_fully_scanned_source():
    with pytest.raises(ValueError):
        gate.ScanCoverage(1, 1, 1, 0, 1)
    with pytest.raises(ValueError):
        gate.QualityDebt(0, 0)
    with pytest.raises(ValueError):
        gate.QualityDebt(-1, 1)


def test_clone_metadata_cannot_undercount_its_admitted_executable_lines():
    locations = (gate.SourceLocation("a.py", 1, 5), gate.SourceLocation("b.py", 1, 5))
    with pytest.raises(ValueError):
        gate.DuplicateBlock(locations, 5, 4)
    with pytest.raises(ValueError):
        gate.DuplicateBlock(locations, 4, 5)
    with pytest.raises(ValueError):
        gate.DuplicateBlock(locations[:1], 5, 5)
    with pytest.raises(ValueError):
        gate.DuplicateBlock((locations[0], locations[0]), 5, 5)
    assert gate.DuplicateBlock(locations, 5, 5).redundant_statements == 5
