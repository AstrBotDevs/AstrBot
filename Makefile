.PHONY: worktree worktree-add worktree-rm bootstrap doctor pr-test-neo pr-test-full pr-test-full-fast \
	build build-all build-backend build-dashboard build-docs dev run run-backend run-dashboard \
	stop stop-backend stop-dashboard clean status docs napcat-schema-ob11-event napcat-schema-ob11-event-normalized napcat-models-ob11-event napcat-models-ob11-event-src napcat-codegen napcat-test napcat-check quality quality-report \
	quality-all quality-sync quality-pyright quality-bandit quality-audit quality-web-audit quality-complexity quality-radon-cc quality-radon-mi \
	quality-report-all quality-report-pyright quality-report-bandit quality-report-audit quality-report-radon-cc quality-report-radon-mi \
	check check-all check-all-platforms format format-all test test-all test-blocking \
	check-py check-py-all check-py-format check-py-lint \
	check-web check-web-all check-web-build check-web-eslint check-web-smoke check-web-prettier check-web-i18n \
	check-data check-md check-md-all check-md-prettier check-md-markdownlint check-toml check-toml-all check-toml-format check-toml-lint check-yaml check-yaml-all check-yaml-prettier check-yaml-lint \
	check-shell check-shell-all check-shell-shfmt check-shell-shellcheck check-ps check-docker check-archify \
	format-py format-web format-data format-md format-toml format-yaml format-shell format-ps format-eol

WORKTREE_DIR ?= ../astrbot_worktree
BRANCH ?= $(word 2,$(MAKECMDGOALS))
BASE ?= $(word 3,$(MAKECMDGOALS))
BASE ?= master

RUN_DIR ?= .make
DASHBOARD_DIR ?= dashboard
DOCS_DIR ?= docs
NAPCAT_SCHEMA_OUTPUT_DIR ?= .tmp/napcat-schema
NAPCAT_NORMALIZED_SCHEMA_PATH ?= $(NAPCAT_SCHEMA_OUTPUT_DIR)/ob11-all-event.normalized.schema.json
NAPCAT_MODELS_OUTPUT_PATH ?= $(NAPCAT_SCHEMA_OUTPUT_DIR)/ob11_event_models.py
NAPCAT_MODELS_SOURCE_PATH ?= astrbot/core/platform/sources/napcat/generated/ob11_events.py
PS ?= pwsh -NoProfile -NonInteractive -File
PNPM := pnpm
ROOT_NODE_BIN := ./node_modules/.bin
PRETTIER := $(ROOT_NODE_BIN)/prettier
TAPLO := $(ROOT_NODE_BIN)/taplo
PYTHON ?= uv run python
QUALITY_TYPE_TARGETS := astrbot
QUALITY_SECURITY_TARGETS := astrbot
QUALITY_TARGETS := quality-pyright quality-bandit quality-audit quality-web-audit quality-complexity quality-radon-cc quality-radon-mi
QUALITY_REPORT_TARGETS := quality-report-pyright quality-report-bandit quality-report-audit quality-report-radon-cc quality-report-radon-mi
CHECK_PY_TARGETS := check-py-format check-py-lint
CHECK_WEB_TARGETS := check-web-build check-web-eslint check-web-smoke check-web-prettier check-web-i18n
CHECK_MD_TARGETS := check-md-prettier check-md-markdownlint
CHECK_TOML_TARGETS := check-toml-format check-toml-lint
CHECK_YAML_TARGETS := check-yaml-prettier check-yaml-lint
CHECK_SHELL_TARGETS := check-shell-shfmt check-shell-shellcheck
PARALLEL_JOBS ?= $(if $(NUMBER_OF_PROCESSORS),$(NUMBER_OF_PROCESSORS),4)
HAS_JOBSERVER := $(findstring --jobserver-auth=,$(MAKEFLAGS))
HAS_JOBS_FLAG := $(findstring -j,$(MAKEFLAGS))
PARALLEL_SUBMAKE_FLAGS := $(if $(strip $(HAS_JOBSERVER) $(HAS_JOBS_FLAG)),,-j$(PARALLEL_JOBS)) --output-sync=target --no-print-directory

ifeq ($(OS),Windows_NT)
CHECK_TARGETS := check-py check-web check-data check-md check-toml check-yaml check-ps
FORMAT_TARGETS := format-py format-web format-data format-md format-toml format-yaml format-ps
DEV_RUNNER := $(PS) scripts/make_dev.ps1
PR_TEST_NEO := $(PS) scripts/pr_test_env.ps1 -TestProfile neo
PR_TEST_FULL := $(PS) scripts/pr_test_env.ps1 -TestProfile full
PR_TEST_FULL_FAST := $(PS) scripts/pr_test_env.ps1 -TestProfile full -SkipSync -NoDashboard
else
CHECK_TARGETS := check-py check-web check-data check-md check-toml check-yaml check-shell check-docker
FORMAT_TARGETS := format-py format-web format-data format-md format-toml format-yaml format-shell
DEV_RUNNER := bash scripts/make_dev.sh
PR_TEST_NEO := bash scripts/pr_test_env.sh --profile neo
PR_TEST_FULL := bash scripts/pr_test_env.sh --profile full
PR_TEST_FULL_FAST := bash scripts/pr_test_env.sh --profile full --skip-sync --no-dashboard
endif

worktree:
	@echo "Usage:"
	@echo "  make worktree-add <branch> [base-branch]"
	@echo "  make worktree-rm  <branch>"

worktree-add:
ifeq ($(strip $(BRANCH)),)
	$(error Branch name required. Usage: make worktree-add <branch> [base-branch])
endif
	@mkdir -p $(WORKTREE_DIR)
	git worktree add $(WORKTREE_DIR)/$(BRANCH) -b $(BRANCH) $(BASE)

worktree-rm:
ifeq ($(strip $(BRANCH)),)
	$(error Branch name required. Usage: make worktree-rm <branch>)
endif
	@if [ -d "$(WORKTREE_DIR)/$(BRANCH)" ]; then \
		git worktree remove $(WORKTREE_DIR)/$(BRANCH); \
	else \
		echo "Worktree $(WORKTREE_DIR)/$(BRANCH) not found."; \
	fi

pr-test-neo:
	@$(PR_TEST_NEO)

pr-test-full:
	@$(PR_TEST_FULL)

pr-test-full-fast:
	@$(PR_TEST_FULL_FAST)

doctor:
	@$(PYTHON) scripts/doctor.py --strict

bootstrap: doctor
	uv sync --group dev --locked
	npm ci
	cd $(DASHBOARD_DIR) && $(PNPM) install --frozen-lockfile

build: build-all

build-all: build-backend build-dashboard build-docs

build-backend:
	uv sync --locked

build-dashboard:
	cd $(DASHBOARD_DIR) && CI=true $(PNPM) install --frozen-lockfile
	cd $(DASHBOARD_DIR) && $(PNPM) build
	uv run python scripts/sync_dashboard_dist.py

build-docs: build-dashboard
	cd $(DOCS_DIR) && CI=true $(PNPM) install --frozen-lockfile
	cd $(DOCS_DIR) && ASTRBOT_DOCS_BASE=/help/ $(PNPM) run docs:build
	uv run python scripts/sync_dashboard_dist.py

dev: run-backend run-dashboard status

run: build
	@$(MAKE) --no-print-directory run-backend
	@$(MAKE) --no-print-directory run-dashboard
	@$(MAKE) --no-print-directory status

run-backend:
	@$(DEV_RUNNER) run-backend

run-dashboard:
	@$(DEV_RUNNER) run-dashboard

stop: stop-dashboard stop-backend

stop-backend:
	@$(DEV_RUNNER) stop-backend

stop-dashboard:
	@$(DEV_RUNNER) stop-dashboard

status:
	@$(DEV_RUNNER) status

clean: stop
	@$(DEV_RUNNER) clean

docs:
	cd $(DOCS_DIR) && CI=true $(PNPM) install --frozen-lockfile
	cd $(DOCS_DIR) && $(PNPM) run docs:dev

napcat-schema-ob11-event:
	@$(PYTHON) scripts/napcat/generate_ob11_event_schema.py --output-dir $(NAPCAT_SCHEMA_OUTPUT_DIR)

napcat-schema-ob11-event-normalized: napcat-schema-ob11-event
	@$(PYTHON) scripts/napcat/normalize_ob11_event_schema.py \
		--input $(NAPCAT_SCHEMA_OUTPUT_DIR)/ob11-all-event.schema.json \
		--output $(NAPCAT_NORMALIZED_SCHEMA_PATH)

napcat-models-ob11-event: napcat-schema-ob11-event-normalized
	@$(PYTHON) scripts/napcat/generate_ob11_event_models.py \
		--schema-path $(NAPCAT_NORMALIZED_SCHEMA_PATH) \
		--output-path $(NAPCAT_MODELS_OUTPUT_PATH)

napcat-models-ob11-event-src: napcat-schema-ob11-event-normalized
	@$(PYTHON) scripts/napcat/generate_ob11_event_models.py \
		--schema-path $(NAPCAT_NORMALIZED_SCHEMA_PATH) \
		--output-path $(NAPCAT_MODELS_SOURCE_PATH)

napcat-codegen: napcat-models-ob11-event-src

napcat-test:
	uv run pytest \
		tests/unit/platform/test_napcat_ws_lifecycle.py \
		tests/unit/platform/test_napcat_inbound_parse.py \
		tests/unit/platform/test_napcat_inbound_events.py \
		tests/unit/platform/test_napcat_notices.py \
		tests/unit/platform/test_napcat_outbound.py \
		tests/unit/test_onebot_contracts.py \
		tests/unit/test_onebot_capability.py \
		tests/unit/test_napcat_codegen_scripts.py \
		tests/unit/test_napcat_codegen_powershell.py

napcat-check: napcat-codegen napcat-test
	git diff --exit-code -- astrbot/core/platform/sources/napcat/generated/ob11_events.py

check-archify:
	@echo "==> [archify] checkout-only doctor and example showcase"
	node .agents/skills/archify/scripts/check-checkout.mjs

quality:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) quality-all

quality-all: $(QUALITY_TARGETS)
	@echo "==> focused quality checks passed"

quality-sync:
	uv sync --group dev --locked

quality-pyright: quality-sync
	uv run pyright --project pyrightconfig.quality.json

quality-bandit: quality-sync
	PYTHONIOENCODING=utf-8 uv run bandit -ll -ii -r $(QUALITY_SECURITY_TARGETS) -c pyproject.toml

quality-audit: quality-sync
	# Local checkout is an unpublished editable install. --strict treats that
	# skip as a collection failure, so only skip-editable is used.
	uv run pip-audit --skip-editable

quality-web-audit:
	cd $(DASHBOARD_DIR) && $(PNPM) install --frozen-lockfile
	cd $(DASHBOARD_DIR) && $(PNPM) audit --audit-level=low

quality-complexity: quality-sync
	# Incremental ceiling: existing C901 debt stays visible in reports, while CI
	# rejects newly introduced extreme-complexity functions without enabling C901
	# at the project-wide 15 threshold yet.
	uv run ruff check --select C901 --config "lint.mccabe.max-complexity=35" astrbot

quality-radon-cc: quality-sync
	uv run radon cc $(QUALITY_TYPE_TARGETS) -s -n C

quality-radon-mi: quality-sync
	uv run radon mi $(QUALITY_TYPE_TARGETS) -s

quality-report:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) quality-report-all

quality-report-all: $(QUALITY_REPORT_TARGETS)
	@echo "==> full quality report generated"

quality-report-pyright: quality-sync
	uv run pyright

quality-report-bandit: quality-sync
	PYTHONIOENCODING=utf-8 uv run bandit -ll -ii -r astrbot -c pyproject.toml

quality-report-audit: quality-sync
	uv run pip-audit --skip-editable

quality-report-radon-cc: quality-sync
	uv run radon cc astrbot -s -n C

quality-report-radon-mi: quality-sync
	uv run radon mi astrbot -s

# Swallow extra args (branch/base) so make doesn't treat them as targets
%:
	@true

# ---------------------------------------------------------------------------
# Repo-wide formatting & linting
#
#   make check    verify the Linux/macOS development toolchain (no writes)
#   make check-all-platforms  also verify PowerShell scripts when pwsh is installed
#   make format   auto-fix every file type
#
# Node tools (prettier, markdownlint-cli2, taplo) come from the root
# package.json; install once with `npm ci`. yamllint comes from the uv
# dev group (`uv sync --group dev`). Shell/Dockerfile linters are native
# binaries: run if present, skipped with a notice otherwise (CI installs them).
# ---------------------------------------------------------------------------

check:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) check-all

check-all: $(CHECK_TARGETS)
	@echo "==> all checks passed"

check-all-platforms: check-all check-ps
	@echo "==> all platform checks passed"

format: doctor
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) format-all

format-all: $(FORMAT_TARGETS)
	@$(MAKE) --no-print-directory format-eol
	@echo "==> formatting complete; run 'make check' to verify"

test: test-all

test-all:
	@echo "==> [test] pytest"
	uv run pytest

test-blocking:
	@echo "==> [test] pytest --test-profile blocking"
	uv run pytest --test-profile blocking

check-py:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) check-py-all

check-py-all: $(CHECK_PY_TARGETS)

check-py-format:
	@echo "==> [py] ruff format --check"
	uv run ruff format --check .

check-py-lint:
	@echo "==> [py] ruff check"
	uv run ruff check .

format-py:
	@echo "==> [py] ruff format + ruff check --fix"
	uv run ruff format .
	uv run ruff check --fix .

check-web:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) check-web-all

check-web-all: $(CHECK_WEB_TARGETS)

check-web-build:
	@echo "==> [web] build"
	cd $(DASHBOARD_DIR) && $(PNPM) build

check-web-eslint:
	@echo "==> [web] eslint"
	cd $(DASHBOARD_DIR) && $(PNPM) exec eslint . --concurrency=auto --max-warnings=0

# The Dashboard build regenerates the tracked MDI subset assets.  Run smoke
# tests after that write completes so Vitest cannot observe a half-written
# font/CSS pair when check-web uses parallel submakes.
check-web-smoke: check-web-build
	@echo "==> [web] smoke tests"
	cd $(DASHBOARD_DIR) && $(PNPM) run test:smoke

check-web-prettier:
	@echo "==> [web] prettier --check"
	$(PRETTIER) --check "dashboard/src/**/*.{ts,mts,js,mjs,vue,scss,css}" "dashboard/*.{ts,mts,mjs}"

check-web-i18n:
	@echo "==> [web] i18n"
	cd $(DASHBOARD_DIR) && $(PNPM) run i18n:check

format-web:
	@echo "==> [web] prettier + eslint --fix"
	$(PRETTIER) --write "dashboard/src/**/*.{ts,mts,js,mjs,vue,scss,css}" "dashboard/*.{ts,mts,mjs}"
	cd $(DASHBOARD_DIR) && $(PNPM) exec eslint . --concurrency=auto --fix

check-data:
	@echo "==> [data] prettier --check json/html"
	@$(PYTHON) scripts/run_tracked_node_tool.py prettier \
		--pattern '*.json' --pattern '*.jsonc' --pattern '*.html' -- \
		--check --log-level warn

format-data:
	@echo "==> [data] prettier --write json/html"
	@$(PYTHON) scripts/run_tracked_node_tool.py prettier \
		--pattern '*.json' --pattern '*.jsonc' --pattern '*.html' -- \
		--write --log-level warn

check-md:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) check-md-all

check-md-all: $(CHECK_MD_TARGETS)

check-md-prettier:
	@echo "==> [md] prettier --check"
	@$(PYTHON) scripts/run_tracked_node_tool.py prettier --pattern '*.md' -- \
		--check --log-level warn

check-md-markdownlint:
	@echo "==> [md] markdownlint-cli2"
	@$(PYTHON) scripts/run_tracked_node_tool.py markdownlint-cli2 --pattern '*.md' -- \
		--no-globs

format-md:
	@echo "==> [md] prettier --write + markdownlint-cli2 --fix"
	@$(PYTHON) scripts/run_tracked_node_tool.py prettier --pattern '*.md' -- \
		--write --log-level warn
	@$(PYTHON) scripts/run_tracked_node_tool.py markdownlint-cli2 --pattern '*.md' -- \
		--fix --no-globs

check-toml:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) check-toml-all

check-toml-all: $(CHECK_TOML_TARGETS)

check-toml-format:
	@echo "==> [toml] taplo fmt --check"
	@for f in $$(git ls-files '*.toml' ':(exclude).pyscn.toml'); do \
		[ -f "$$f" ] || continue; \
		$(TAPLO) fmt --check --stdin-filepath "$$f" - < "$$f" || exit 1; \
	done

check-toml-lint:
	@echo "==> [toml] taplo lint"
	@for f in $$(git ls-files '*.toml'); do \
		[ -f "$$f" ] || continue; \
		$(TAPLO) lint - < "$$f" || exit 1; \
	done

format-toml:
	@echo "==> [toml] taplo fmt"
	@for f in $$(git ls-files '*.toml' ':(exclude).pyscn.toml'); do \
		[ -f "$$f" ] || continue; \
		tmp=$$(mktemp); \
		$(TAPLO) fmt --stdin-filepath "$$f" - < "$$f" > "$$tmp" && mv "$$tmp" "$$f"; \
	done

check-yaml:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) check-yaml-all

check-yaml-all: $(CHECK_YAML_TARGETS)

check-yaml-prettier:
	@echo "==> [yaml] prettier --check"
	@$(PYTHON) scripts/run_tracked_node_tool.py prettier \
		--pattern '*.yml' --pattern '*.yaml' -- --check --log-level warn

check-yaml-lint:
	@echo "==> [yaml] yamllint"
	uv run yamllint --strict .

format-yaml:
	@echo "==> [yaml] prettier --write"
	@$(PYTHON) scripts/run_tracked_node_tool.py prettier \
		--pattern '*.yml' --pattern '*.yaml' -- --write --log-level warn

check-shell:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) check-shell-all

check-shell-all: $(CHECK_SHELL_TARGETS)

check-shell-shfmt:
	@command -v shfmt >/dev/null 2>&1 || { echo "shfmt is required; run 'make doctor' for setup guidance." >&2; exit 2; }
	@echo "==> [shell] shfmt -d"
	@shfmt -d -i 2 -ci $$(git ls-files '*.sh')

check-shell-shellcheck:
	@command -v shellcheck >/dev/null 2>&1 || { echo "shellcheck is required; run 'make doctor' for setup guidance." >&2; exit 2; }
	@echo "==> [shell] shellcheck"
	@shellcheck -S style $$(git ls-files '*.sh')

format-shell:
	@command -v shfmt >/dev/null 2>&1 || { echo "shfmt is required; run 'make doctor' for setup guidance." >&2; exit 2; }
	@echo "==> [shell] shfmt -w"
	@shfmt -w -i 2 -ci $$(git ls-files '*.sh')

check-ps:
	@echo "==> [ps] PSScriptAnalyzer"
	@$(PS) scripts/lint_powershell.ps1 -Require

format-ps:
	@echo "==> [ps] Invoke-Formatter"
	@$(PS) scripts/lint_powershell.ps1 -Fix

format-eol:
	@echo "==> [eol] normalize tracked text files to LF"
	@$(PYTHON) scripts/normalize_line_endings.py

check-docker:
	@command -v hadolint >/dev/null 2>&1 || { echo "hadolint is required; run 'make doctor' for setup guidance." >&2; exit 2; }
	@echo "==> [docker] hadolint"
	@hadolint --config .hadolint.yaml Dockerfile
