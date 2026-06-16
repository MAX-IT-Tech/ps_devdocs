#!/usr/bin/env python3
"""Apply hook metadata fixes for PR #2131 review feedback."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hook_utils import (  # noqa: E402
    HOOK_INDEX_PATH,
    REPO_ROOT,
    Occurrence,
    fix_smarty_semicolons,
    format_files_yaml,
    format_hook_aliases_yaml,
    git_show_upstream,
    infer_hook_type,
    load_scope_files,
    parse_title_from_front_matter,
    parse_type_from_front_matter,
    replace_call_snippet,
    replace_files_block,
    replace_hook_aliases_block,
    replace_type,
    restore_protected_scalar_fields,
    split_front_matter,
)

REMOVED_HOOKS = {"actionBeforeAjaxDie"}


def load_index() -> dict:
    return json.loads(HOOK_INDEX_PATH.read_text(encoding="utf-8"))


def occurrences_from_index(entry: dict) -> list[Occurrence]:
    seen_files: set[tuple[str, str]] = set()
    result: list[Occurrence] = []
    for item in entry.get("occurrences", []):
        key = (item["repo"], item["file"])
        if key in seen_files:
            continue
        seen_files.add(key)
        result.append(
            Occurrence(
                repo=item["repo"],
                file=item["file"],
                line=item["line"],
                snippet=item["snippet"],
            )
        )
    return result


def fix_page(path: Path, index: dict) -> str | None:
    rel = path.relative_to(REPO_ROOT).as_posix()
    text = path.read_text(encoding="utf-8")
    fm, body = split_front_matter(text)
    if not fm:
        return None

    hook_name = parse_title_from_front_matter(fm)
    if not hook_name:
        return None

    entry = index.get(hook_name, {})
    if hook_name in REMOVED_HOOKS and not entry.get("occurrences"):
        return "DELETE"

    upstream_text = git_show_upstream(rel) or ""
    upstream_fm, upstream_body = (
        split_front_matter(upstream_text) if upstream_text else ("", "")
    )

    aliases = entry.get("aliases", [])
    occurrences = occurrences_from_index(entry)

    updated_fm = fm
    updated_fm = replace_hook_aliases_block(
        updated_fm, format_hook_aliases_yaml(aliases, upstream_fm)
    )

    upstream_type = parse_type_from_front_matter(upstream_fm or fm)
    hook_type = infer_hook_type(hook_name, upstream_type or None)
    if hook_type:
        updated_fm = replace_type(updated_fm, hook_type)

    updated_fm = restore_protected_scalar_fields(updated_fm, upstream_fm, ["hookTitle"])
    updated_fm = replace_files_block(
        updated_fm, format_files_yaml(occurrences, upstream_fm)
    )

    updated_body = body
    if occurrences:
        updated_body = replace_call_snippet(updated_body, occurrences[0].snippet)
    elif upstream_body:
        call_match = re.search(
            r"## Call of the Hook in the origin file\n\n```php\n(.*?)\n```",
            upstream_body,
            re.DOTALL,
        )
        if call_match:
            updated_body = replace_call_snippet(
                updated_body, call_match.group(1).strip()
            )

    updated_body = fix_smarty_semicolons(updated_body)
    return updated_fm + updated_body


def main() -> int:
    if not HOOK_INDEX_PATH.exists():
        print("Run build_hook_index.py first.", file=sys.stderr)
        return 1

    index = load_index()
    changed = 0
    deleted = 0

    for path in load_scope_files():
        if not path.exists():
            continue
        result = fix_page(path, index)
        if result == "DELETE":
            path.unlink()
            deleted += 1
            print(f"deleted {path.name}")
            continue
        if not result:
            continue
        original = path.read_text(encoding="utf-8")
        if result != original:
            path.write_text(result, encoding="utf-8")
            changed += 1

    print(f"Updated {changed} files, deleted {deleted} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
