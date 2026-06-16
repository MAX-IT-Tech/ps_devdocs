PYTHON ?= python3

.PHONY: qa-docs qa-docs-all qa-final qa-final-transitional install-guardrails build-hook-index

build-hook-index:
	$(PYTHON) scripts/build_hook_index.py

qa-docs:
	$(PYTHON) scripts/qa_docs_gate.py --scope changed --base-ref upstream/9.x --rebuild-index

qa-docs-all:
	$(PYTHON) scripts/qa_docs_gate.py --scope all --rebuild-index

qa-final:
	$(PYTHON) scripts/qa_docs_gate.py --scope changed --base-ref upstream/9.x --rebuild-index --final --enforce-branch-pattern --mode strict

qa-final-transitional:
	@BRANCH=$$(git rev-parse --abbrev-ref HEAD); \
	if [ -n "$(PUSH_RANGE)" ]; then \
	  RANGE="$(PUSH_RANGE)"; \
	elif git rev-parse --verify "refs/remotes/publish/$$BRANCH" >/dev/null 2>&1; then \
	  RANGE="refs/remotes/publish/$$BRANCH..HEAD"; \
	elif git rev-parse --verify "refs/remotes/origin/$$BRANCH" >/dev/null 2>&1; then \
	  RANGE="refs/remotes/origin/$$BRANCH..HEAD"; \
	else \
	  UPSTREAM=$$(git rev-parse --abbrev-ref --symbolic-full-name $$BRANCH@{upstream} 2>/dev/null || true); \
	  UPSTREAM_BRANCH=$${UPSTREAM##*/}; \
	  if [ -n "$$UPSTREAM" ] && [ "$$UPSTREAM_BRANCH" = "$$BRANCH" ] && git rev-parse --verify "$$UPSTREAM" >/dev/null 2>&1; then \
	    RANGE="$$UPSTREAM..HEAD"; \
	  else \
	    echo "[qa-final-transitional] No same-name remote branch found. Set PUSH_RANGE explicitly."; \
	    exit 1; \
	  fi; \
	fi; \
	echo "[qa-final-transitional] range=$$RANGE"; \
	$(PYTHON) scripts/qa_docs_gate.py --scope range --range "$$RANGE" --rebuild-index --final --mode transitional

install-guardrails:
	@echo "Usage: make install-guardrails PUBLISH_URL=<git_url>"
	@test -n "$(PUBLISH_URL)"
	bash scripts/install_docs_guardrails.sh "$(PUBLISH_URL)"
