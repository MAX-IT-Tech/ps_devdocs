#!/usr/bin/env python3
"""Unified docs QA gate for hook documentation workflows."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hook_utils import (  # noqa: E402
    CLASSIC_THEME_DIR,
    HOOK_INDEX_PATH,
    HOOK_LIST_DIR,
    HUMMINGBIRD_DIR,
    PRESTASHOP_DIR,
    infer_hook_type,
    parse_hook_aliases_from_front_matter,
    parse_title_from_front_matter,
    parse_type_from_front_matter,
    split_front_matter,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROHIBITED_PATH_PATTERNS = (
    ".specstory/",
    "tmp_groups/",
    ".cursor/plans/",
    ".reference/",
)
BRANCH_ALLOWED_RE = re.compile(r"^(feat|fix)/")
SMALL_SMARTY_HOOK_RE = re.compile(r"\{hook\s+h=['\"][^'\"]+['\"]\};")
CALL_SECTION_RE = re.compile(
    r"## Call of the Hook in the origin file\s+```([a-zA-Z0-9_+-]+)\n(.*?)\n```",
    re.DOTALL,
)


def run_cmd(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    result = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)
    return result.returncode, result.stdout.strip()


def current_branch() -> str:
    code, out = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO_ROOT)
    return out if code == 0 else "unknown"


def head_sha() -> str:
    code, out = run_cmd(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT)
    return out if code == 0 else "unknown"


def qa_stamp_path(branch: str) -> Path:
    safe_branch = branch.replace("/", "__")
    return REPO_ROOT / ".git" / "qa" / f"docs_gate_final_{safe_branch}.json"


def load_index() -> dict[str, dict]:
    return json.loads(HOOK_INDEX_PATH.read_text(encoding="utf-8"))


def staged_files() -> list[Path]:
    code, out = run_cmd(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"], cwd=REPO_ROOT
    )
    if code != 0 or not out:
        return []
    return [REPO_ROOT / rel for rel in out.splitlines()]


def changed_files(base_ref: str) -> list[Path]:
    diff_range = f"{base_ref}...HEAD"
    code, out = run_cmd(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", diff_range], cwd=REPO_ROOT
    )
    if code != 0 or not out:
        return []
    return [REPO_ROOT / rel for rel in out.splitlines()]


def range_files(diff_range: str) -> list[Path]:
    code, out = run_cmd(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", diff_range], cwd=REPO_ROOT
    )
    if code != 0 or not out:
        return []
    return [REPO_ROOT / rel for rel in out.splitlines()]


def all_hook_files() -> list[Path]:
    return sorted(HOOK_LIST_DIR.glob("*.md"))


def only_hook_pages(paths: list[Path]) -> list[Path]:
    hook_root = HOOK_LIST_DIR.resolve()
    out: list[Path] = []
    for path in paths:
        if not path.suffix == ".md":
            continue
        try:
            path.resolve().relative_to(hook_root)
        except ValueError:
            continue
        out.append(path)
    return sorted(set(out))


def extract_files_entries(front_matter: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    in_files = False
    current: dict[str, str] = {}
    for raw_line in front_matter.splitlines():
        line = raw_line.rstrip()
        if re.match(r"^files:\s*\{\s*\}\s*$", line):
            return []
        if line.startswith("files:"):
            in_files = True
            continue
        if in_files and re.match(r"^[A-Za-z_]+\s*:", line):
            if current:
                entries.append(current)
            break
        if not in_files:
            continue
        if re.match(r"^\s*-\s*$", line):
            if current:
                entries.append(current)
            current = {}
            continue
        kv = re.match(r"^\s*([A-Za-z_]+):\s*(.*)$", line)
        if kv:
            key = kv.group(1).strip()
            value = kv.group(2).strip().strip("'\"")
            current[key] = value
    if in_files and current:
        entries.append(current)
    return entries


def validate_link_entry(path: Path, entry: dict[str, str], errors: list[str]) -> None:
    rel = path.relative_to(REPO_ROOT).as_posix()
    url = (entry.get("url") or "").strip()
    file_path = (entry.get("file") or "").strip()
    module = (entry.get("module") or "").strip()
    theme = (entry.get("theme") or "").strip()
    if module and not url:
        errors.append(f"{rel}: files[].module is set but url is empty")
        return
    if not url:
        return
    if "github.com/PrestaShop/PrestaShop/blob/9.1.x/" in url:
        rel_file = url.split("blob/9.1.x/", 1)[1]
        if rel_file.startswith("modules/"):
            errors.append(f"{rel}: module origin points to core repo ({url})")
            return
        if not (PRESTASHOP_DIR / rel_file).exists():
            errors.append(f"{rel}: broken 9.1.x core url ({url})")
        return
    if "github.com/PrestaShop/classic-theme/blob/develop/" in url:
        rel_file = url.split("blob/develop/", 1)[1]
        if not (CLASSIC_THEME_DIR / rel_file).exists():
            errors.append(f"{rel}: broken classic-theme url ({url})")
        if theme and theme != "classic":
            errors.append(f"{rel}: theme/url mismatch for classic-theme")
        return
    if "github.com/PrestaShop/hummingbird/blob/develop/" in url:
        rel_file = url.split("blob/develop/", 1)[1]
        if not (HUMMINGBIRD_DIR / rel_file).exists():
            errors.append(f"{rel}: broken hummingbird url ({url})")
        if theme and theme != "hummingbird":
            errors.append(f"{rel}: theme/url mismatch for hummingbird")
        return
    if "github.com/PrestaShop/PrestaShop/modules/" in url:
        errors.append(f"{rel}: module origin uses invalid core modules url ({url})")
    if file_path.startswith("modules/") and "github.com/PrestaShop/PrestaShop" in url:
        errors.append(f"{rel}: module file path should not use core repo url ({url})")


def validate_call_block(
    path: Path, hook_name: str, body: str, errors: list[str]
) -> None:
    rel = path.relative_to(REPO_ROOT).as_posix()
    if SMALL_SMARTY_HOOK_RE.search(body):
        errors.append(f"{rel}: Smarty snippet has trailing semicolon")
    match = CALL_SECTION_RE.search(body)
    if not match:
        errors.append(f"{rel}: missing call section code fence")
        return
    fence = match.group(1).strip().lower()
    snippet = match.group(2).strip()
    if "..." in snippet:
        errors.append(f"{rel}: call snippet looks truncated ('...')")
    if "{hook h=" in snippet and fence != "smarty":
        errors.append(f"{rel}: Smarty hook snippet must use smarty fence")
    if (
        "renderhook(" in snippet.lower() or "renderHook(" in snippet
    ) and fence != "twig":
        errors.append(f"{rel}: renderhook call must use twig fence")
    if (
        "hook::exec(" in snippet.lower() or "dispatchwithparameters(" in snippet.lower()
    ) and fence != "php":
        errors.append(f"{rel}: Hook::exec/dispatchWithParameters must use php fence")
    if "Hook::exec(" in snippet and hook_name not in snippet:
        errors.append(f"{rel}: Hook::exec snippet does not include hook name")
    if (
        "dispatchWithParameters(" in snippet
        and hook_name.lower() not in snippet.lower()
    ):
        errors.append(
            f"{rel}: dispatchWithParameters snippet does not include hook name"
        )
    if "Hook::exec(" in snippet and snippet.count("(") > snippet.count(")"):
        errors.append(f"{rel}: Hook::exec snippet has unbalanced parentheses")
    if "[" in snippet and "]" not in snippet:
        errors.append(f"{rel}: call snippet has incomplete array parameters")


def validate_hook_page(path: Path, index: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    front_matter, body = split_front_matter(text)
    rel = path.relative_to(REPO_ROOT).as_posix()
    if not front_matter:
        return [f"{rel}: missing front matter"]
    hook_name = parse_title_from_front_matter(front_matter)
    if not hook_name:
        return [f"{rel}: missing Title in front matter"]
    hook_type = parse_type_from_front_matter(front_matter) or ""
    expected_type = infer_hook_type(hook_name)
    if expected_type and hook_type != expected_type:
        errors.append(f"{rel}: inferred type '{expected_type}' but got '{hook_type}'")
    if hook_name.startswith("display") and hook_type == "action":
        errors.append(f"{rel}: display hook typed as action")
    entry = index.get(hook_name, {})
    expected_aliases = entry.get("aliases", [])
    actual_aliases = parse_hook_aliases_from_front_matter(front_matter)
    if expected_aliases != actual_aliases:
        errors.append(
            f"{rel}: hookAliases mismatch expected {expected_aliases} got {actual_aliases}"
        )
    files_entries = extract_files_entries(front_matter)
    occurrences = entry.get("occurrences", [])
    if not files_entries and occurrences:
        errors.append(f"{rel}: files is empty but index has source occurrences")
    if not files_entries and not occurrences:
        errors.append(
            f"{rel}: no files and no occurrences, delete or fix source mapping"
        )
    for item in files_entries:
        validate_link_entry(path, item, errors)
    validate_call_block(path, hook_name, body, errors)
    return errors


def ensure_reference_mirrors() -> list[str]:
    errors: list[str] = []
    missing = [
        path
        for path in (PRESTASHOP_DIR, CLASSIC_THEME_DIR, HUMMINGBIRD_DIR)
        if not path.exists()
    ]
    for item in missing:
        errors.append(f"Missing reference mirror: {item}")
    return errors


def check_prohibited_paths(paths: list[Path]) -> list[str]:
    issues: list[str] = []
    for path in paths:
        rel = path.relative_to(REPO_ROOT).as_posix()
        for bad in PROHIBITED_PATH_PATTERNS:
            if rel.startswith(bad):
                issues.append(f"Prohibited path in change set: {rel}")
                break
    return issues


def collect_scope(args: argparse.Namespace) -> list[Path]:
    if args.scope == "staged":
        return staged_files()
    if args.scope == "changed":
        return changed_files(args.base_ref)
    if args.scope == "range":
        if not args.diff_range:
            print("--range is required when --scope range", file=sys.stderr)
            return []
        return range_files(args.diff_range)
    if args.scope == "all":
        return all_hook_files()
    if args.scope == "files":
        return [REPO_ROOT / raw for raw in args.files]
    return []


def run_build_hook_index() -> int:
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "build_hook_index.py")]
    code, out = run_cmd(cmd, cwd=REPO_ROOT)
    if out:
        print(out)
    return code


def write_final_stamp(
    branch: str,
    sha: str,
    checked_files: int,
    scope: str,
    *,
    mode: str = "strict",
    diff_range: str | None = None,
) -> None:
    stamp = qa_stamp_path(branch)
    stamp.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "branch": branch,
        "sha": sha,
        "checked_files": checked_files,
        "scope": scope,
        "mode": mode,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if diff_range:
        payload["diff_range"] = diff_range
    stamp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote QA final stamp: {stamp}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run documentation QA gate checks.")
    parser.add_argument(
        "--scope",
        choices=("staged", "changed", "range", "all", "files"),
        default="changed",
        help="Which files to check",
    )
    parser.add_argument(
        "--range",
        dest="diff_range",
        default="",
        help="Git diff range for --scope range (e.g. origin/feat/foo..HEAD)",
    )
    parser.add_argument(
        "--base-ref",
        default="upstream/9.x",
        help="Base ref used for --scope changed",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="Files used for --scope files",
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Rebuild .reference/hook_index.json before validating",
    )
    parser.add_argument(
        "--final",
        action="store_true",
        help="Write final-pass stamp required by pre-push hook",
    )
    parser.add_argument(
        "--enforce-branch-pattern",
        action="store_true",
        help="Fail when current branch does not match feat/* or fix/*",
    )
    parser.add_argument(
        "--mode",
        choices=("strict", "transitional"),
        default="strict",
        help="Stamp mode written by --final (strict or transitional)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    branch = current_branch()
    sha = head_sha()

    if args.scope == "range" and not args.diff_range:
        print("--range is required when --scope range", file=sys.stderr)
        return 1

    all_files = collect_scope(args)
    if not all_files:
        print("No files selected by scope. QA gate passed.")
        if args.final:
            write_final_stamp(
                branch,
                sha,
                0,
                args.scope,
                mode=args.mode,
                diff_range=args.diff_range or None,
            )
        return 0

    if args.enforce_branch_pattern and not BRANCH_ALLOWED_RE.match(branch):
        print(
            f"Branch '{branch}' is not allowed. Use feat/* or fix/* for publishable work.",
            file=sys.stderr,
        )
        return 1

    prohibited_issues = check_prohibited_paths(all_files)
    if prohibited_issues:
        print("Prohibited files detected:")
        for issue in prohibited_issues:
            print(f"- {issue}")
        return 1

    hook_files = only_hook_pages(all_files)
    if not hook_files:
        print("No hook docs in selected scope. QA gate passed.")
        if args.final:
            write_final_stamp(
                branch,
                sha,
                0,
                args.scope,
                mode=args.mode,
                diff_range=args.diff_range or None,
            )
        return 0

    mirror_errors = ensure_reference_mirrors()
    if mirror_errors:
        print("Reference mirror check failed:", file=sys.stderr)
        for issue in mirror_errors:
            print(f"- {issue}", file=sys.stderr)
        return 1

    if args.rebuild_index or not HOOK_INDEX_PATH.exists():
        print("Building hook index...")
        if run_build_hook_index() != 0:
            return 1

    index = load_index()
    errors: list[str] = []
    for path in hook_files:
        if not path.exists():
            errors.append(f"{path.relative_to(REPO_ROOT).as_posix()}: file is missing")
            continue
        errors.extend(validate_hook_page(path, index))

    if errors:
        print(f"QA gate failed with {len(errors)} issue(s):")
        for item in errors[:200]:
            print(f"- {item}")
        if len(errors) > 200:
            print(f"- ... and {len(errors) - 200} more")
        return 1

    print(f"QA gate passed for {len(hook_files)} hook file(s).")
    if args.final:
        write_final_stamp(
            branch,
            sha,
            len(hook_files),
            args.scope,
            mode=args.mode,
            diff_range=args.diff_range or None,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
