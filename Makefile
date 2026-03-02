.PHONY: worktree worktree-add worktree-rm

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
