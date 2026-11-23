"""Strict source quality gate with inspectable diagnostics and clone locations.

Clones are identical contiguous AST statement sequences with at least five
distinct source lines starting executable statements. Identifiers and literal
values remain significant; comments and docstrings do not. Imports, signatures,
literal data declarations and formatting cannot supply the five required lines.
The longest matches are selected first. The legacy score charges two points
per additional non-overlapping copy. V2 measures the eligible AST statements in
each extra copy, with the same two-point minimum. Neither score double charges
overlapping windows or nested copies. An incomplete scan has no valid V2 score.
"""

import ast
import io
import os
import re
import tokenize
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Literal

ASTRBOT_ROOT = Path(__file__).parent.parent / "astrbot"
MIN_CLONE_LINES = 5
MIN_SCORE = 80
MAX_DEBT_UNITS = 200
BAD_IGNORE_CODES = frozenset(
    {
        "import",
        "import-not-found",
        "import-untyped",
        "unresolved-import",
        "class-alias",
        "no-name-module",
        "attr-defined",
        "class-var",
        "assignment",
        "type-var",
        "misc",
    }
)
IGNORE_DIRECTIVE = re.compile(r"#\s*type:\s*ignore\b(?:\s*\[([^\]]*)\])?")
DiagnosticKind = Literal["cast_any", "type_ignore", "bad_type_ignore", "bare_except"]


@dataclass(frozen=True, order=True)
class SourceLocation:
    path: str
    line: int
    end_line: int


@dataclass(frozen=True)
class Diagnostic:
    kind: DiagnosticKind
    location: SourceLocation
    detail: str = ""


@dataclass(frozen=True)
class ScanError:
    path: str
    message: str


@dataclass(frozen=True)
class PatternCounts:
    cast_any: int
    type_ignore: int
    bad_type_ignore: int
    bare_except: int
    duplicate_blocks: int


def _require_count(name: str, value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class ScanCoverage:
    discovered_files: int = 0
    read_files: int = 0
    parsed_files: int = 0
    tokenized_files: int = 0
    executable_statements: int = 0
    discovery_complete: bool = True

    def __post_init__(self) -> None:
        for name in (
            "discovered_files",
            "read_files",
            "parsed_files",
            "tokenized_files",
            "executable_statements",
        ):
            _require_count(name, getattr(self, name))
        if not (
            self.tokenized_files
            <= self.parsed_files
            <= self.read_files
            <= self.discovered_files
        ):
            raise ValueError(
                "File counts must satisfy tokenized <= parsed <= read <= discovered"
            )
        if not self.tokenized_files and self.executable_statements:
            raise ValueError("Executable statements require a fully scanned source")
        if type(self.discovery_complete) is not bool:
            raise ValueError("discovery_complete must be a boolean")

    @property
    def complete(self) -> bool:
        return (
            self.discovery_complete
            and self.discovered_files > 0
            and self.discovered_files
            == self.read_files
            == self.parsed_files
            == self.tokenized_files
            and self.executable_statements > 0
        )


@dataclass(frozen=True)
class QualityDebt:
    units: int
    executable_statements: int

    def __post_init__(self) -> None:
        _require_count("units", self.units)
        _require_count("executable_statements", self.executable_statements)
        if not self.executable_statements:
            raise ValueError("A valid score requires executable source statements")

    @property
    def debt(self) -> float:
        return self.units / 10

    @property
    def score(self) -> float:
        return 80000 / (800 + self.units)

    @property
    def density(self) -> float:
        """Debt per 1,000 executable statements, for diagnosis only."""
        return 1000 * self.debt / self.executable_statements

    @property
    def passes(self) -> bool:
        return self.units <= MAX_DEBT_UNITS


@dataclass(frozen=True)
class DuplicateBlock:
    locations: tuple[SourceLocation, ...]
    executable_lines: int
    executable_statements: int

    def __post_init__(self) -> None:
        _require_count("executable_lines", self.executable_lines)
        _require_count("executable_statements", self.executable_statements)
        if not MIN_CLONE_LINES <= self.executable_lines <= self.executable_statements:
            raise ValueError(
                "A clone needs five executable start lines backed by AST statements"
            )
        if len(self.locations) < 2 or any(
            _overlap(first, second) for first, second in combinations(self.locations, 2)
        ):
            raise ValueError("A clone needs at least two non-overlapping locations")

    @property
    def redundant_statements(self) -> int:
        # Admission already implies k >= five distinct starting lines. Keep the
        # explicit floor so no future statement-count convention weakens it.
        return (len(self.locations) - 1) * max(
            MIN_CLONE_LINES, self.executable_statements
        )


@dataclass(frozen=True)
class ScanResult:
    diagnostics: tuple[Diagnostic, ...]
    duplicates: tuple[DuplicateBlock, ...]
    errors: tuple[ScanError, ...]
    coverage: ScanCoverage = field(default_factory=ScanCoverage)

    @property
    def counts(self) -> PatternCounts:
        counts = Counter(diagnostic.kind for diagnostic in self.diagnostics)
        return PatternCounts(
            cast_any=counts["cast_any"],
            type_ignore=counts["type_ignore"],
            bad_type_ignore=counts["bad_type_ignore"],
            bare_except=counts["bare_except"],
            duplicate_blocks=sum(len(block.locations) - 1 for block in self.duplicates),
        )

    @property
    def score(self) -> float:
        counts = self.counts
        return _calculate_score(
            counts.cast_any,
            counts.type_ignore,
            counts.bad_type_ignore,
            counts.bare_except,
            counts.duplicate_blocks,
        )

    @property
    def redundant_statements(self) -> int:
        return sum(block.redundant_statements for block in self.duplicates)

    @property
    def assessment(self) -> QualityDebt | None:
        if self.errors or not self.coverage.complete:
            return None
        if self.redundant_statements > self.coverage.executable_statements:
            raise ValueError(
                "Non-overlapping clone debt cannot exceed scanned statements"
            )
        return QualityDebt(
            _calculate_debt_units(self.counts, self.redundant_statements),
            self.coverage.executable_statements,
        )

    @property
    def score_v2(self) -> float | None:
        assessment = self.assessment
        return assessment.score if assessment is not None else None


def _calculate_debt_units(counts: PatternCounts, redundant_statements: int) -> int:
    """Calculate integer tenths of debt without a source-size denominator."""
    for name in (
        "cast_any",
        "type_ignore",
        "bad_type_ignore",
        "bare_except",
        "duplicate_blocks",
    ):
        _require_count(name, getattr(counts, name))
    _require_count("redundant_statements", redundant_statements)
    if counts.bad_type_ignore > counts.type_ignore:
        raise ValueError("Bad ignores must be a subset of all ignores")
    if redundant_statements < MIN_CLONE_LINES * counts.duplicate_blocks:
        raise ValueError("Every extra clone must contribute at least five statements")
    if not counts.duplicate_blocks and redundant_statements:
        raise ValueError("Redundant statements require an extra clone")
    return (
        10 * counts.cast_any
        + 5 * (counts.type_ignore - counts.bad_type_ignore)
        + 35 * counts.bad_type_ignore
        + 20 * counts.bare_except
        + 4 * redundant_statements
    )


def _calculate_score(
    cast_any: int,
    type_ignore: int,
    bad_type_ignore: int,
    bare_except: int,
    dup_blocks: int,
) -> float:
    """Apply the documented costs, including both costs for a bad ignore."""
    return max(
        0.0,
        100
        - cast_any
        - type_ignore * 0.5
        - bad_type_ignore * 3
        - bare_except * 0.5
        - dup_blocks * 2,
    )


def _location(
    path: str, node: ast.stmt | ast.expr | ast.ExceptHandler
) -> SourceLocation:
    return SourceLocation(path, node.lineno, node.end_lineno or node.lineno)


class _LocalBindings(ast.NodeVisitor):
    """Find lexical locals without entering a nested function or class."""

    def __init__(self) -> None:
        self.names: set[str] = set()
        self.globals: set[str] = set()
        self.nonlocals: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        self.names.update(
            alias.asname or alias.name.split(".")[0] for alias in node.names
        )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.names.update(alias.asname or alias.name for alias in node.names)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.names.add(node.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names.add(node.name)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass

    def visit_Global(self, node: ast.Global) -> None:
        self.globals.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.nonlocals.update(node.names)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.names.add(node.name)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.visit(node.iter)
        for condition in node.ifs:
            self.visit(condition)


@dataclass
class _Scope:
    kind: str
    bindings: dict[str, str | None] = field(default_factory=dict)
    globals: set[str] = field(default_factory=set)
    nonlocals: set[str] = field(default_factory=set)


class _PatternVisitor(ast.NodeVisitor):
    """Resolve imported typing symbols and ordinary lexical rebinding."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.diagnostics: list[Diagnostic] = []
        self.scopes = [_Scope("module")]

    def _lookup(self, name: str) -> str | None:
        current = self.scopes[-1]
        if name in current.globals:
            return self.scopes[0].bindings.get(name)
        for index in range(len(self.scopes) - 1, -1, -1):
            scope = self.scopes[index]
            if scope.kind == "class" and index != len(self.scopes) - 1:
                continue
            if name in scope.bindings:
                return scope.bindings[name]
        return None

    def _resolve(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return self._lookup(node.id)
        if isinstance(node, ast.Attribute):
            base = self._resolve(node.value)
            return f"{base}.{node.attr}" if base else None
        return None

    def _bind(self, name: str, symbol: str | None = None) -> None:
        scope = self.scopes[-1]
        if name in scope.globals:
            scope = self.scopes[0]
        elif name in scope.nonlocals:
            scope = next(
                (
                    outer
                    for outer in reversed(self.scopes[:-1])
                    if outer.kind == "function" and name in outer.bindings
                ),
                scope,
            )
        scope.bindings[name] = symbol

    def _bind_target(self, target: ast.expr, symbol: str | None = None) -> None:
        if isinstance(target, ast.Name):
            self._bind(target.id, symbol)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self._bind_target(item)
        elif isinstance(target, ast.Starred):
            self._bind_target(target.value)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            symbol = "typing" if alias.name in {"typing", "typing_extensions"} else None
            self._bind(alias.asname or alias.name.split(".")[0], symbol)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            symbol = (
                f"typing.{alias.name}"
                if node.level == 0 and node.module in {"typing", "typing_extensions"}
                else None
            )
            self._bind(alias.asname or alias.name, symbol)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        symbol = self._resolve(node.value)
        for target in node.targets:
            self.visit(target)
            self._bind_target(target, symbol)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.target)
        self._bind_target(
            node.target, self._resolve(node.value) if node.value else None
        )

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.generic_visit(node)
        self._bind_target(node.target)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self._bind_target(node.target, self._resolve(node.value))

    def visit_Delete(self, node: ast.Delete) -> None:
        self.generic_visit(node)
        for target in node.targets:
            self._bind_target(target)

    def visit_For(self, node: ast.For | ast.AsyncFor) -> None:
        self.visit(node.iter)
        self._bind_target(node.target)
        for statement in [*node.body, *node.orelse]:
            self.visit(statement)

    visit_AsyncFor = visit_For

    def visit_With(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars:
                self._bind_target(item.optional_vars)
        for statement in node.body:
            self.visit(statement)

    visit_AsyncWith = visit_With

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.diagnostics.append(
                Diagnostic("bare_except", _location(self.path, node))
            )
        else:
            self.visit(node.type)
        if node.name:
            self._bind(node.name)
        for statement in node.body:
            self.visit(statement)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            self._resolve(node.func) == "typing.cast"
            and node.args
            and self._resolve(node.args[0]) == "typing.Any"
        ):
            self.diagnostics.append(Diagnostic("cast_any", _location(self.path, node)))
        self.generic_visit(node)

    def _function_scope(self, args: ast.arguments, body: Iterable[ast.AST]) -> _Scope:
        locals_ = _LocalBindings()
        for node in body:
            locals_.visit(node)
        parameters = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        if args.vararg:
            parameters.append(args.vararg)
        if args.kwarg:
            parameters.append(args.kwarg)
        names = locals_.names | {parameter.arg for parameter in parameters}
        return _Scope(
            "function",
            dict.fromkeys(names - locals_.globals - locals_.nonlocals),
            locals_.globals,
            locals_.nonlocals,
        )

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for value in [*node.decorator_list, node.args, node.returns, *node.type_params]:
            if value is not None:
                self.visit(value)
        self._bind(node.name)
        self.scopes.append(self._function_scope(node.args, node.body))
        for statement in node.body:
            self.visit(statement)
        self.scopes.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.visit(node.args)
        self.scopes.append(self._function_scope(node.args, [node.body]))
        self.visit(node.body)
        self.scopes.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for value in [
            *node.decorator_list,
            *node.bases,
            *node.keywords,
            *node.type_params,
        ]:
            self.visit(value)
        self._bind(node.name)
        self.scopes.append(_Scope("class"))
        for statement in node.body:
            self.visit(statement)
        self.scopes.pop()

    def _visit_comprehension(
        self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
    ) -> None:
        self.visit(node.generators[0].iter)
        self.scopes.append(_Scope("function"))
        for index, generator in enumerate(node.generators):
            if index:
                self.visit(generator.iter)
            self._bind_target(generator.target)
            for condition in generator.ifs:
                self.visit(condition)
        if isinstance(node, ast.DictComp):
            self.visit(node.key)
            self.visit(node.value)
        else:
            self.visit(node.elt)
        self.scopes.pop()

    visit_ListComp = _visit_comprehension
    visit_SetComp = _visit_comprehension
    visit_DictComp = _visit_comprehension
    visit_GeneratorExp = _visit_comprehension


class _WithoutDocstrings(ast.NodeTransformer):
    def visit_Expr(self, node: ast.Expr) -> ast.Expr | None:
        return None if isinstance(node.value, ast.Constant) else node


def _literal_data(node: ast.expr) -> bool:
    """Recognize literal declarations without evaluating source code."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_literal_data(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(key is not None and _literal_data(key) for key in node.keys) and all(
            _literal_data(value) for value in node.values
        )
    return (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, (ast.UAdd, ast.USub, ast.Invert))
        and _literal_data(node.operand)
    )


_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_SCAFFOLDING = (
    ast.Import,
    ast.ImportFrom,
    ast.Pass,
    ast.Global,
    ast.Nonlocal,
    ast.TypeAlias,
)


def _executable_nodes(node: ast.AST) -> Iterable[ast.stmt]:
    if isinstance(node, (*_DEFINITIONS, *_SCAFFOLDING)):
        return
    if isinstance(node, ast.Assign) and _literal_data(node.value):
        return
    if isinstance(node, ast.AnnAssign) and (
        node.value is None or _literal_data(node.value)
    ):
        return
    if isinstance(node, ast.stmt):
        yield node
    for child in ast.iter_child_nodes(node):
        yield from _executable_nodes(child)


@dataclass(frozen=True)
class _Statement:
    fingerprint: str
    location: SourceLocation
    lines: frozenset[int]
    weight: int


def _statement_suites(path: str, tree: ast.AST) -> Iterable[tuple[_Statement, ...]]:
    """Keep suite boundaries: a match cannot cross functions or branches."""
    for _, value in ast.iter_fields(tree):
        if isinstance(value, list):
            statements: list[_Statement] = []
            for item in value:
                if not isinstance(item, ast.AST):
                    continue
                if isinstance(item, _DEFINITIONS) or not isinstance(item, ast.stmt):
                    if statements:
                        yield tuple(statements)
                        statements = []
                else:
                    executable = tuple(_executable_nodes(item))
                    statements.append(
                        _Statement(
                            ast.dump(item, include_attributes=False),
                            _location(path, item),
                            frozenset(statement.lineno for statement in executable),
                            len(executable),
                        )
                    )
                yield from _statement_suites(path, item)
            if statements:
                yield tuple(statements)
        elif isinstance(value, ast.AST):
            yield from _statement_suites(path, value)


def _overlap(first: SourceLocation, second: SourceLocation) -> bool:
    return first.path == second.path and (
        first.line <= second.end_line and second.line <= first.end_line
    )


def _span(suite: tuple[_Statement, ...], start: int, end: int) -> SourceLocation:
    return SourceLocation(
        suite[start].location.path,
        suite[start].location.line,
        suite[end - 1].location.end_line,
    )


def _find_duplicates(
    suites: list[tuple[_Statement, ...]],
) -> tuple[DuplicateBlock, ...]:
    # Node-count seeds are invariant to line wrapping. Actual occurrences must
    # still contain five distinct executable source lines before being charged.
    seeds: dict[tuple[str, ...], list[tuple[int, int, int]]] = defaultdict(list)
    for suite_index, suite in enumerate(suites):
        for start, statement in enumerate(suite):
            if not statement.weight:
                continue
            weight = 0
            for end in range(start, len(suite)):
                weight += suite[end].weight
                if weight >= MIN_CLONE_LINES:
                    key = tuple(item.fingerprint for item in suite[start : end + 1])
                    seeds[key].append((suite_index, start, end + 1))
                    break

    matches: dict[tuple[str, ...], dict[SourceLocation, int]] = defaultdict(dict)
    statement_counts: dict[tuple[str, ...], int] = {}
    for occurrences in seeds.values():
        for first, second in combinations(occurrences, 2):
            left, right = suites[first[0]], suites[second[0]]
            a, b, c, d = first[1], first[2], second[1], second[2]
            if _overlap(_span(left, a, b), _span(right, c, d)):
                continue
            while (
                a > 0 and c > 0 and left[a - 1].fingerprint == right[c - 1].fingerprint
            ):
                if _overlap(_span(left, a - 1, b), _span(right, c - 1, d)):
                    break
                a -= 1
                c -= 1
            while (
                b < len(left)
                and d < len(right)
                and left[b].fingerprint == right[d].fingerprint
            ):
                if _overlap(_span(left, a, b + 1), _span(right, c, d + 1)):
                    break
                b += 1
                d += 1
            while not left[a].weight:
                a += 1
                c += 1
            while not left[b - 1].weight:
                b -= 1
                d -= 1
            first_lines = len(set().union(*(item.lines for item in left[a:b])))
            second_lines = len(set().union(*(item.lines for item in right[c:d])))
            if min(first_lines, second_lines) < MIN_CLONE_LINES:
                continue
            key = tuple(item.fingerprint for item in left[a:b])
            matches[key][_span(left, a, b)] = first_lines
            matches[key][_span(right, c, d)] = second_lines
            statement_counts[key] = sum(item.weight for item in left[a:b])

    # A previously selected block may anchor a shorter match in a new location,
    # but only previously uncovered, non-overlapping copies incur another cost.
    covered: dict[str, list[SourceLocation]] = defaultdict(list)
    result: list[DuplicateBlock] = []
    ordered = sorted(
        matches.items(),
        key=lambda item: (
            -min(item[1].values()),
            -len(item[0]),
            tuple(sorted(item[1])),
        ),
    )
    for key, occurrences in ordered:
        locations: list[SourceLocation] = []
        for location in sorted(occurrences):
            if not any(_overlap(location, previous) for previous in locations):
                locations.append(location)
        fresh = [
            location
            for location in locations
            if not any(
                _overlap(location, previous) for previous in covered[location.path]
            )
        ]
        anchor = next(
            (location for location in locations if location not in fresh), None
        )
        selected = ([anchor] if anchor else []) + fresh
        if len(selected) < 2:
            continue
        result.append(
            DuplicateBlock(
                tuple(selected),
                min(occurrences[location] for location in selected),
                statement_counts[key],
            )
        )
        for location in fresh:
            covered[location.path].append(location)
    return tuple(result)


def scan_sources(sources: Mapping[str, str]) -> ScanResult:
    """Scan supplied Python sources without importing or executing them."""
    diagnostics: list[Diagnostic] = []
    errors: list[ScanError] = []
    suites: list[tuple[_Statement, ...]] = []
    parsed_files = 0
    tokenized_files = 0
    executable_statements = 0
    for path, source in sorted(sources.items()):
        try:
            tree = ast.parse(source, filename=path)
            parsed_files += 1
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                if token.type != tokenize.COMMENT:
                    continue
                match = IGNORE_DIRECTIVE.match(token.string)
                if match is None:
                    continue
                location = SourceLocation(path, token.start[0], token.end[0])
                diagnostics.append(Diagnostic("type_ignore", location, token.string))
                codes = {code.strip() for code in (match[1] or "").split(",")}
                if codes & BAD_IGNORE_CODES:
                    diagnostics.append(
                        Diagnostic("bad_type_ignore", location, token.string)
                    )
            tokenized_files += 1
        except (SyntaxError, tokenize.TokenError, ValueError) as error:
            errors.append(ScanError(path, str(error)))
            continue
        visitor = _PatternVisitor(path)
        visitor.visit(tree)
        diagnostics.extend(visitor.diagnostics)
        _WithoutDocstrings().visit(tree)
        # ast.walk visits each statement once, including bodies of definitions.
        # Eligibility is exactly the predicate already used by clone matching.
        executable_statements += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.stmt)
            and next(iter(_executable_nodes(node)), None) is node
        )
        suites.extend(_statement_suites(path, tree))
    return ScanResult(
        tuple(sorted(diagnostics, key=lambda item: (item.location, item.kind))),
        _find_duplicates(suites),
        tuple(errors),
        ScanCoverage(
            discovered_files=len(sources),
            read_files=len(sources),
            parsed_files=parsed_files,
            tokenized_files=tokenized_files,
            executable_statements=executable_statements,
        ),
    )


def _scan_for_patterns() -> ScanResult:
    sources: dict[str, str] = {}
    errors: list[ScanError] = []
    discovered: list[Path] = []
    discovery_complete = True

    def discovery_error(error: OSError) -> None:
        nonlocal discovery_complete
        discovery_complete = False
        errors.append(ScanError(str(error.filename or ASTRBOT_ROOT), str(error)))

    # Path.rglob can silently suppress directory discovery failures. The same
    # Python file scope is walked without following directory symlinks, and its
    # onerror callback makes an inaccessible subtree invalidate the whole scan.
    try:
        for directory, _, files in os.walk(
            ASTRBOT_ROOT, onerror=discovery_error, followlinks=False
        ):
            discovered.extend(
                Path(directory) / name for name in files if Path(name).match("*.py")
            )
    except OSError as error:
        discovery_error(error)
    for path in sorted(discovered):
        relative = path.relative_to(ASTRBOT_ROOT.parent).as_posix()
        try:
            with tokenize.open(path) as source_file:
                sources[relative] = source_file.read()
        except (OSError, UnicodeError, SyntaxError) as error:
            errors.append(ScanError(relative, str(error)))
    if not sources:
        errors.append(ScanError(str(ASTRBOT_ROOT), "No Python sources found"))
    result = scan_sources(sources)
    return ScanResult(
        result.diagnostics,
        result.duplicates,
        tuple(errors) + result.errors,
        ScanCoverage(
            discovered_files=len(discovered),
            read_files=len(sources),
            parsed_files=result.coverage.parsed_files,
            tokenized_files=result.coverage.tokenized_files,
            executable_statements=result.coverage.executable_statements,
            discovery_complete=discovery_complete,
        ),
    )


def _format_report(result: ScanResult) -> str:
    counts = result.counts
    coverage = result.coverage
    assessment = result.assessment
    lines = [
        (
            f"Source quality V2: {assessment.score:.3f}/100; "
            f"debt={assessment.debt:g}; U={assessment.units}; "
            f"required: U <= {MAX_DEBT_UNITS}"
            if assessment is not None
            else "Source quality V2: INVALID (score=None); gate FAIL"
        ),
        (
            f"Legacy source quality score: {result.score:g}/100; "
            f"separate required minimum: {MIN_SCORE}"
            if assessment is not None
            else "Legacy gate: INVALID; partial counts cannot establish a passing score"
        ),
        f"Coverage: discovered={coverage.discovered_files}; read={coverage.read_files}; "
        f"parsed={coverage.parsed_files}; tokenized={coverage.tokenized_files}; "
        f"executable statements={coverage.executable_statements}; "
        f"discovery complete={coverage.discovery_complete}",
        f"cast(Any): {counts.cast_any}; type ignores: {counts.type_ignore}; "
        f"bad ignores: {counts.bad_type_ignore}; bare except: {counts.bare_except}; "
        f"duplicate copies: {counts.duplicate_blocks}; "
        f"redundant statements R: {result.redundant_statements}",
    ]
    if assessment is not None:
        lines.append(
            f"Debt density: {assessment.density:.3f} per 1,000 executable statements "
            "(diagnostic only; never used by either gate)"
        )
    elif not coverage.complete:
        lines.append(
            "INVALID: complete, non-empty executable source coverage is required"
        )
    lines.extend(f"ERROR {error.path}: {error.message}" for error in result.errors)
    for diagnostic in result.diagnostics:
        location = diagnostic.location
        lines.append(
            f"{diagnostic.kind}: {location.path}:{location.line} {diagnostic.detail}"
        )
    for block in result.duplicates:
        locations = ", ".join(
            f"{location.path}:{location.line}-{location.end_line}"
            for location in block.locations
        )
        lines.append(
            f"clone ({block.executable_lines} executable lines; "
            f"{block.executable_statements} AST statements per copy; "
            f"R={block.redundant_statements}): {locations}"
        )
    return "\n".join(lines)


class TestCodeQualityTyping:
    def test_type_safety_score(self) -> None:
        result = _scan_for_patterns()
        report = _format_report(result)
        print(report)
        assert not result.errors, report
        assessment = result.assessment
        assert assessment is not None, report
        assert result.score >= MIN_SCORE, report
        assert assessment.passes, report
