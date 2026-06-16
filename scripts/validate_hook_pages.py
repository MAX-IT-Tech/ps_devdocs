#!/usr/bin/env python3
"""Validate hook pages against hook_index.json and review rules."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hook_utils import (  # noqa: E402
    CLASSIC_THEME_DIR,
    HOOK_INDEX_PATH,
    HUMMINGBIRD_DIR,
    PRESTASHOP_DIR,
    TEMPLATE_HOOK_RE,
    infer_hook_type,
    load_scope_files,
    parse_hook_aliases_from_front_matter,
    parse_title_from_front_matter,
    parse_type_from_front_matter,
    split_front_matter,
)

REMOVED_HOOKS = {"actionBeforeAjaxDie"}


def load_index() -> dict:
    return json.loads(HOOK_INDEX_PATH.read_text(encoding="utf-8"))


def file_exists_in_reference(repo: str, file_path: str) -> bool:
    if repo == "prestashop":
        return (PRESTASHOP_DIR / file_path).exists()
    if repo == "classic-theme":
        rel = file_path.removeprefix("themes/classic/")
        return (CLASSIC_THEME_DIR / rel).exists()
    if repo == "hummingbird":
        rel = file_path.removeprefix("themes/hummingbird/")
        return (HUMMINGBIRD_DIR / rel).exists()
    return False


def extract_files_from_front_matter(fm: str) -> list[tuple[str | None, str]]:
    files: list[tuple[str | None, str]] = []
    current_theme: str | None = None
    current_file: str | None = None
    for line in fm.splitlines():
        theme_match = re.match(r"^\s*theme:\s*(\w+)", line)
        if theme_match:
            current_theme = theme_match.group(1)
            continue
        file_match = re.match(r"^\s*file:\s*(.+)$", line)
        if file_match:
            current_file = file_match.group(1).strip()
            files.append((current_theme, current_file))
            current_theme = None
            current_file = None
    return files


def validate_page(path: Path, index: dict) -> list[str]:
    errors: list[str] = []
    rel = path.name
    text = path.read_text(encoding="utf-8")
    fm, body = split_front_matter(text)
    if not fm:
        errors.append(f"{rel}: missing front matter")
        return errors

    hook_name = parse_title_from_front_matter(fm)
    if not hook_name:
        errors.append(f"{rel}: missing Title")
        return errors

    if TEMPLATE_HOOK_RE.search(hook_name):
        return errors

    entry = index.get(hook_name, {})
    expected_aliases = entry.get("aliases", [])
    actual_aliases = parse_hook_aliases_from_front_matter(fm)
    if actual_aliases != expected_aliases:
        errors.append(
            f"{rel}: hookAliases mismatch expected {expected_aliases} got {actual_aliases}"
        )

    for alias in actual_aliases:
        if alias == hook_name:
            errors.append(f"{rel}: alias must not equal hook name ({alias})")

    hook_type = parse_type_from_front_matter(fm) or ""
    if hook_name.startswith("display") and hook_type != "display":
        errors.append(f"{rel}: display hook has type {hook_type}")
    if hook_name.startswith("action") and hook_type != "action":
        errors.append(f"{rel}: action hook has type {hook_type}")

    indexed = {(item["repo"], item["file"]) for item in entry.get("occurrences", [])}
    has_index_occurrences = bool(indexed)

    if re.search(r"\{hook h=['\"][^'\"]+['\"]\};", body):
        errors.append(f"{rel}: Smarty hook snippet has trailing semicolon")

    if has_index_occurrences:
        listed = extract_files_from_front_matter(fm)
        listed_keys = set()
        for theme, file_path in listed:
            if theme:
                repo = "classic-theme" if theme == "classic" else "hummingbird"
                tpl = file_path.removeprefix(f"themes/{theme}/")
                listed_keys.add(
                    (
                        repo,
                        tpl
                        if tpl.startswith("templates/")
                        else f"templates/{tpl.split('templates/', 1)[-1]}",
                    )
                )
            else:
                listed_keys.add(("prestashop", file_path))
        if len(listed_keys) < len(
            {(o["repo"], o["file"]) for o in entry.get("occurrences", [])}
        ):
            errors.append(
                f"{rel}: files[] lists {len(listed_keys)} origins but index has {len(indexed)}"
            )

    for theme, file_path in extract_files_from_front_matter(fm):
        if not has_index_occurrences:
            continue
        repo = "prestashop"
        check_path = file_path
        if theme == "classic":
            repo = "classic-theme"
            check_path = file_path.removeprefix("themes/classic/")
        elif theme == "hummingbird":
            repo = "hummingbird"
            check_path = file_path.removeprefix("themes/hummingbird/")
        if theme is None and not file_path.startswith("themes/"):
            if file_path.startswith("modules/"):
                continue
            if not file_path.strip():
                continue
            if not (PRESTASHOP_DIR / file_path).exists():
                errors.append(f"{rel}: missing core file {file_path}")
        elif theme and not file_exists_in_reference(repo, file_path):
            errors.append(f"{rel}: missing theme file {file_path}")

    if hook_name in REMOVED_HOOKS:
        errors.append(f"{rel}: removed hook page should be deleted")

    expected_type = infer_hook_type(hook_name)
    if expected_type and hook_type and expected_type != hook_type:
        errors.append(f"{rel}: inferred type {expected_type} != {hook_type}")

    return errors


def main() -> int:
    if not HOOK_INDEX_PATH.exists():
        print("Run build_hook_index.py first.", file=sys.stderr)
        return 1

    index = load_index()
    all_errors: list[str] = []
    for path in load_scope_files():
        if not path.exists():
            hook_name = path.stem
            if hook_name in REMOVED_HOOKS:
                continue
            all_errors.append(f"{path.name}: missing file")
            continue
        all_errors.extend(validate_page(path, index))

    if all_errors:
        print(f"Validation failed with {len(all_errors)} error(s):")
        for err in all_errors[:100]:
            print(err)
        if len(all_errors) > 100:
            print(f"... and {len(all_errors) - 100} more")
        return 1

    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
