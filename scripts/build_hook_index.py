#!/usr/bin/env python3
"""Build .reference/hook_index.json from PrestaShop 9.1.x sources."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hook_utils import (  # noqa: E402
    HOOK_ALIAS_XML,
    HOOK_INDEX_PATH,
    HOOK_XML,
    HookMeta,
    find_occurrences,
    infer_hook_type,
    load_scope_files,
    parse_hook_alias_xml,
    parse_hook_xml,
    parse_title_from_front_matter,
    split_front_matter,
)


def hook_names_from_scope() -> list[str]:
    names: list[str] = []
    for path in load_scope_files():
        text = path.read_text(encoding="utf-8")
        fm, _ = split_front_matter(text)
        if not fm:
            continue
        title = parse_title_from_front_matter(fm)
        if title:
            names.append(title)
    return sorted(set(names))


def build_index() -> dict[str, dict]:
    aliases_by_hook = parse_hook_alias_xml(HOOK_ALIAS_XML)
    hooks_xml = parse_hook_xml(HOOK_XML)
    index: dict[str, dict] = {}

    for hook_name in hook_names_from_scope():
        xml_meta = hooks_xml.get(hook_name, {})
        occurrences = find_occurrences(hook_name)
        meta = HookMeta(
            name=hook_name,
            aliases=aliases_by_hook.get(hook_name, []),
            title=xml_meta.get("title", ""),
            description=xml_meta.get("description", ""),
            hook_type=infer_hook_type(hook_name),
            occurrences=occurrences,
        )
        index[hook_name] = {
            "aliases": meta.aliases,
            "title": meta.title,
            "description": meta.description,
            "type": meta.hook_type,
            "occurrences": [
                {
                    "repo": occ.repo,
                    "file": occ.file,
                    "line": occ.line,
                    "snippet": occ.snippet,
                }
                for occ in meta.occurrences
            ],
        }

    return index


def main() -> int:
    if not HOOK_ALIAS_XML.exists():
        print(
            f"Missing {HOOK_ALIAS_XML}. Clone .reference/prestashop first.",
            file=sys.stderr,
        )
        return 1

    index = build_index()
    HOOK_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOOK_INDEX_PATH.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {HOOK_INDEX_PATH} ({len(index)} hooks)")
    with_occ = sum(1 for item in index.values() if item["occurrences"])
    print(f"Hooks with occurrences: {with_occ}")
    without = [name for name, item in index.items() if not item["occurrences"]]
    if without:
        print(f"Hooks without occurrences: {len(without)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
