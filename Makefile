.PHONY: worktree worktree-add worktree-rm pr-test-neo pr-test-full pr-test-full-fast update-test-sandbox

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

pr-test-neo:
	./scripts/pr_test_env.sh --profile neo

pr-test-full:
	./scripts/pr_test_env.sh --profile full

pr-test-full-fast:
	./scripts/pr_test_env.sh --profile full --skip-sync --no-dashboard

clean-temp-deployment:
	@set -eu; \
	update_sandbox="$$(mktemp -d "$${TMPDIR:-/tmp}/astrbot-update-test.XXXXXX")"; \
	echo "Copying the current workspace to $$update_sandbox"; \
	rsync -a \
		--exclude='.git/' \
		--exclude='.venv/' \
		--exclude='data/' \
		--exclude='node_modules/' \
		--exclude='.pnpm-store/' \
		--exclude='.pytest_cache/' \
		--exclude='.ruff_cache/' \
		--exclude='__pycache__/' \
		./ "$$update_sandbox/"; \
	cd "$$update_sandbox"; \
	uv sync; \
	echo; \
	echo "Update test sandbox is ready: $$update_sandbox"; \
	echo "Start it with:"; \
	printf '  cd "%s" && uv run main.py\n' "$$update_sandbox"

# Swallow extra args (branch/base) so make doesn't treat them as targets
%:
	@true
