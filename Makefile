.PHONY: worktree worktree-add worktree-rm test test-unit test-integration test-cov test-quick

WORKTREE_DIR ?= ../astrbot_worktree
BRANCH ?= $(word 2,$(MAKECMDGOALS))
BASE ?= $(word 3,$(MAKECMDGOALS))
BASE ?= master

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

# Swallow extra args (branch/base) so make doesn't treat them as targets
%:
	@true

# ============================================================
# 测试命令
# ============================================================

# 运行所有测试
test:
	uv run pytest -c tests/pytest.ini tests/ -v

# 运行单元测试
test-unit:
	uv run pytest -c tests/pytest.ini tests/ -v -m "unit and not integration"

# 运行集成测试
test-integration:
	uv run pytest -c tests/pytest.ini tests/integration/ -v -m integration

# 运行测试并生成覆盖率报告
test-cov:
	uv run pytest -c tests/pytest.ini tests/ --cov=astrbot --cov-report=term-missing --cov-report=html -v

# 快速测试（跳过慢速测试和集成测试）
test-quick:
	uv run pytest -c tests/pytest.ini tests/ -v -m "not slow and not integration" --tb=short

# 运行特定测试文件
test-file:
	@echo "Usage: uv run pytest tests/path/to/test_file.py -v"
	@echo "Example: uv run pytest tests/test_main.py -v"
