#!/usr/bin/env python3
"""Resolve pre-push policy mode for the current branch."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / ".githooks" / "push-policy.json"


def load_policy() -> dict:
    if not POLICY_PATH.exists():
        return {"default_mode": "strict", "transitional_branches": []}
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def resolve_mode(branch: str) -> str:
    policy = load_policy()
    transitional = policy.get("transitional_branches", [])
    if branch in transitional:
        return "transitional"
    return policy.get("default_mode", "strict")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: docs_push_policy.py <branch>", file=sys.stderr)
        return 2
    print(resolve_mode(sys.argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
