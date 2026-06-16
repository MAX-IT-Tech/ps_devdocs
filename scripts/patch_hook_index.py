#!/usr/bin/env python3
"""Patch hook_index.json with supplemental occurrences without full rebuild."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hook_utils import (  # noqa: E402
    HOOK_INDEX_PATH,
    find_occurrences,
    load_scope_files,
    parse_title_from_front_matter,
    split_front_matter,
)


def main() -> int:
    index = json.loads(HOOK_INDEX_PATH.read_text(encoding="utf-8"))
    for path in load_scope_files():
        text = path.read_text(encoding="utf-8")
        fm, _ = split_front_matter(text)
        if not fm:
            continue
        hook_name = parse_title_from_front_matter(fm)
        if not hook_name:
            continue
        occ = find_occurrences(hook_name)
        if hook_name not in index:
            index[hook_name] = {
                "aliases": [],
                "title": "",
                "description": "",
                "type": "",
                "occurrences": [],
            }
        index[hook_name]["occurrences"] = [
            {"repo": o.repo, "file": o.file, "line": o.line, "snippet": o.snippet}
            for o in occ
        ]
    HOOK_INDEX_PATH.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Patched {HOOK_INDEX_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
