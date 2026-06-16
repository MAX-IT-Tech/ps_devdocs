#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [[ ! -d ".githooks" ]]; then
  echo "[guardrails] Missing .githooks directory."
  exit 1
fi

chmod +x .githooks/pre-commit .githooks/pre-push scripts/qa_docs_gate.py scripts/docs_push_policy.py

git config --local core.hooksPath .githooks
echo "[guardrails] core.hooksPath set to .githooks"

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "[guardrails] origin remote is missing."
  exit 1
fi

ORIGIN_PUSHURL_BLOCKED="${ORIGIN_PUSHURL_BLOCKED:-no_push://origin-disabled}"
git remote set-url --push origin "$ORIGIN_PUSHURL_BLOCKED"
echo "[guardrails] origin pushurl blocked: $ORIGIN_PUSHURL_BLOCKED"

PUBLISH_URL="${1:-}"
if [[ -z "$PUBLISH_URL" ]]; then
  echo "[guardrails] Usage: scripts/install_docs_guardrails.sh <publish_remote_url>"
  echo "[guardrails] Example: scripts/install_docs_guardrails.sh git@github.com:<user>/docs.git"
  exit 1
fi

if git remote get-url publish >/dev/null 2>&1; then
  git remote set-url publish "$PUBLISH_URL"
else
  git remote add publish "$PUBLISH_URL"
fi

echo "[guardrails] publish remote set to: $PUBLISH_URL"
echo "[guardrails] Done. Use 'git push publish <branch>' for publishing."
