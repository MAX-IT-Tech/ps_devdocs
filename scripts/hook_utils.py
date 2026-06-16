#!/usr/bin/env python3
"""Shared helpers for PrestaShop hook documentation sync."""

from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = REPO_ROOT / ".reference"
PRESTASHOP_DIR = REFERENCE_DIR / "prestashop"
CLASSIC_THEME_DIR = REFERENCE_DIR / "classic-theme"
HUMMINGBIRD_DIR = REFERENCE_DIR / "hummingbird"
HOOK_LIST_DIR = REPO_ROOT / "modules/concepts/hooks/list-of-hooks"
SCOPE_FILE = REPO_ROOT / "tmp_groups/01_hooks_metadata_sync.txt"
HOOK_INDEX_PATH = REFERENCE_DIR / "hook_index.json"

HOOK_ALIAS_XML = PRESTASHOP_DIR / "install-dev/data/xml/hook_alias.xml"
HOOK_XML = PRESTASHOP_DIR / "install-dev/data/xml/hook.xml"

GITHUB_PS = "https://github.com/PrestaShop/PrestaShop/blob/9.1.x"
GITHUB_CLASSIC = "https://github.com/PrestaShop/classic-theme/blob/develop"
GITHUB_HUMMINGBIRD = "https://github.com/PrestaShop/hummingbird/blob/develop"

TEMPLATE_HOOK_RE = re.compile(r"[<>]")


@dataclass
class Occurrence:
    repo: str
    file: str
    line: int
    snippet: str
    lang: str = "php"


@dataclass
class HookMeta:
    name: str
    aliases: list[str] = field(default_factory=list)
    title: str = ""
    description: str = ""
    hook_type: str = ""
    occurrences: list[Occurrence] = field(default_factory=list)


def load_scope_files() -> list[Path]:
    if not SCOPE_FILE.exists():
        return sorted(HOOK_LIST_DIR.glob("*.md"))
    lines = SCOPE_FILE.read_text(encoding="utf-8").splitlines()
    paths: list[Path] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        candidate = Path(line)
        if candidate.is_absolute():
            paths.append(candidate)
        elif line.startswith("modules/"):
            paths.append(REPO_ROOT / line)
        else:
            paths.append(HOOK_LIST_DIR / line)
    return paths


def split_front_matter(text: str) -> tuple[str | None, str]:
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines(keepends=True)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "".join(lines[: i + 1]), "".join(lines[i + 1 :])
    return None, text


def parse_simple_yaml_value(block: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", block, re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    if value in ("", "null"):
        return ""
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def parse_title_from_front_matter(fm: str) -> str | None:
    return parse_simple_yaml_value(fm, "Title")


def parse_hook_aliases_from_front_matter(fm: str) -> list[str]:
    if re.search(r"^hookAliases:\s*$", fm, re.MULTILINE):
        aliases: list[str] = []
        in_aliases = False
        for line in fm.splitlines():
            if line.startswith("hookAliases:"):
                rest = line.split(":", 1)[1].strip()
                if rest and rest not in ("", "null"):
                    return [rest.strip("'\"")]
                in_aliases = True
                continue
            if in_aliases:
                if re.match(r"^\s+-\s+", line):
                    aliases.append(line.split("-", 1)[1].strip().strip("'\""))
                    continue
                if re.match(r"^[A-Za-z_]", line):
                    break
        return aliases
    scalar = parse_simple_yaml_value(fm, "hookAliases")
    if scalar is None:
        return []
    return [scalar] if scalar else []


def parse_type_from_front_matter(fm: str) -> str | None:
    return parse_simple_yaml_value(fm, "type")


def infer_hook_type(hook_name: str, fallback: str | None = None) -> str:
    if hook_name.startswith("display"):
        return "display"
    if hook_name.startswith("action"):
        return "action"
    return fallback or ""


def parse_hook_alias_xml(path: Path) -> dict[str, list[str]]:
    tree = ET.parse(path)
    aliases_by_hook: dict[str, list[str]] = {}
    for entity in tree.findall(".//hook_alias"):
        alias = (entity.findtext("alias") or "").strip()
        name = (entity.findtext("name") or "").strip()
        if not name or not alias or alias == name:
            continue
        aliases_by_hook.setdefault(name, []).append(alias)
    return aliases_by_hook


def parse_hook_xml(path: Path) -> dict[str, dict[str, str]]:
    tree = ET.parse(path)
    hooks: dict[str, dict[str, str]] = {}
    for entity in tree.findall(".//hook"):
        name = (entity.findtext("name") or "").strip()
        if not name:
            continue
        hooks[name] = {
            "title": (entity.findtext("title") or "").strip(),
            "description": (entity.findtext("description") or "").strip(),
        }
    return hooks


def git_show_upstream(rel_path: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "show", f"upstream/9.x:{rel_path}"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None


def prestashop_search_roots() -> list[Path]:
    roots = [
        PRESTASHOP_DIR / "classes",
        PRESTASHOP_DIR / "controllers",
        PRESTASHOP_DIR / "src",
        PRESTASHOP_DIR / "admin-dev",
        PRESTASHOP_DIR / "templates",
    ]
    return [root for root in roots if root.exists()]


def run_rg(
    pattern: str,
    search_roots: list[Path],
    repo_root: Path,
    globs: list[str],
) -> list[tuple[str, int, str]]:
    matches: list[tuple[str, int, str]] = []
    base = repo_root.resolve()
    for search_root in search_roots:
        if not search_root.exists():
            continue
        cmd = ["rg", "-n", "-F", "-e", pattern, str(search_root)]
        for glob in globs:
            cmd.extend(["--glob", glob])
        for exclude in ("vendor/**", "node_modules/**", "var/**", "cache/**"):
            cmd.extend(["--glob", f"!{exclude}"])
        try:
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        except FileNotFoundError:
            return []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            path_part, line_no, content = line.split(":", 2)
            rel = Path(path_part).resolve().relative_to(base).as_posix()
            matches.append((rel, int(line_no), content.strip()))
    return matches


def extract_snippet(
    repo_root: Path, rel_file: str, line_no: int, max_lines: int = 6
) -> tuple[str, str]:
    path = repo_root / rel_file
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    idx = max(line_no - 1, 0)
    chunk = lines[idx : idx + max_lines]
    snippet = "\n".join(chunk).strip()
    if rel_file.endswith((".tpl", ".twig")) and "{hook" in snippet:
        for line in chunk:
            if "{hook" in line:
                return line.strip().split(";")[0].strip(), "smarty"
        return snippet.split(";")[0].strip(), "smarty"
    if "renderhook" in snippet or "renderHook" in snippet:
        return snippet.rstrip(";"), "twig"
    if "Hook::exec" in snippet or "dispatchWithParameters" in snippet:
        joined = " ".join(s.strip() for s in chunk).strip()
        if ");" in joined:
            joined = joined[: joined.index(");") + 2]
        joined = joined.rstrip(";")
        return joined, "php"
    return snippet, "php"


def search_patterns(hook_name: str) -> list[str]:
    quote_pairs = [("'", "'"), ('"', '"')]
    patterns: list[str] = []
    for left, right in quote_pairs:
        patterns.extend(
            [
                f"Hook::exec({left}{hook_name}{right}",
                f"dispatchWithParameters({left}{hook_name}{right}",
                f"renderHook({left}{hook_name}{right}",
                f"renderhook({left}{hook_name}{right}",
                f"{{hook h={left}{hook_name}{right}",
                f"{left}{hook_name}{right}",
            ]
        )
    return patterns


HOOK_LINE_KEYWORDS = (
    "Hook::exec",
    "dispatchWithParameters",
    "renderHook",
    "renderhook",
    "hookName",
    "{hook h=",
    "DASHBOARD_ALLOWED_HOOKS",
)


def supplemental_occurrences(hook_name: str) -> list[Occurrence]:
    extras: list[Occurrence] = []

    if "ListingFieldsModifier" in hook_name or "ListingResultsModifier" in hook_name:
        needle = (
            "ListingFieldsModifier"
            if "ListingFieldsModifier" in hook_name
            else "ListingResultsModifier"
        )
        admin_file = "classes/controller/AdminController.php"
        admin_path = PRESTASHOP_DIR / admin_file
        if admin_path.exists():
            lines = admin_path.read_text(encoding="utf-8").splitlines()
            for idx, line in enumerate(lines, start=1):
                if needle in line and "Hook::exec" in line:
                    snippet, _ = extract_snippet(
                        PRESTASHOP_DIR, admin_file, idx, max_lines=8
                    )
                    extras.append(Occurrence("prestashop", admin_file, idx, snippet))
                    break

    hook_finder_patterns = [
        f"hookName = '{hook_name}'",
        f'hookName = "{hook_name}"',
        f"protected $hookName = '{hook_name}'",
    ]
    for pattern in hook_finder_patterns:
        for rel_file, line_no, _ in run_rg(
            pattern, prestashop_search_roots(), PRESTASHOP_DIR, ["*.php"]
        ):
            snippet, _ = extract_snippet(PRESTASHOP_DIR, rel_file, line_no)
            extras.append(Occurrence("prestashop", rel_file, line_no, snippet))

    if hook_name == "displayProductExtraContent":
        extras.extend(
            [
                Occurrence(
                    "prestashop",
                    "src/Core/Product/ProductExtraContentFinder.php",
                    19,
                    "protected $hookName = 'displayProductExtraContent';",
                ),
                Occurrence(
                    "prestashop",
                    "src/Core/Product/ProductExtraContent.php",
                    1,
                    "class ProductExtraContent",
                ),
            ]
        )

    return extras


def find_occurrences(hook_name: str) -> list[Occurrence]:
    if TEMPLATE_HOOK_RE.search(hook_name):
        return []

    seen: set[tuple[str, str, int]] = set()
    occurrences: list[Occurrence] = []

    search_targets = [
        (
            prestashop_search_roots(),
            PRESTASHOP_DIR,
            "prestashop",
            ["*.php", "*.tpl", "*.twig"],
        ),
        (
            [CLASSIC_THEME_DIR / "templates"],
            CLASSIC_THEME_DIR,
            "classic-theme",
            ["*.tpl"],
        ),
        ([HUMMINGBIRD_DIR / "templates"], HUMMINGBIRD_DIR, "hummingbird", ["*.tpl"]),
    ]

    for roots, repo_root, repo, globs in search_targets:
        if not roots:
            continue
        for pattern in search_patterns(hook_name):
            for rel_file, line_no, content in run_rg(pattern, roots, repo_root, globs):
                if pattern in {f"'{hook_name}'", f'"{hook_name}"'}:
                    if not any(keyword in content for keyword in HOOK_LINE_KEYWORDS):
                        if hook_name not in content:
                            continue
                key = (repo, rel_file, line_no)
                if key in seen:
                    continue
                seen.add(key)
                snippet, _lang = extract_snippet(repo_root, rel_file, line_no)
                occurrences.append(
                    Occurrence(repo=repo, file=rel_file, line=line_no, snippet=snippet)
                )

    for occ in supplemental_occurrences(hook_name):
        key = (occ.repo, occ.file, occ.line)
        if key in seen:
            continue
        seen.add(key)
        occurrences.append(occ)

    occurrences.sort(key=lambda item: (item.repo != "prestashop", item.file, item.line))
    return occurrences


def format_hook_aliases_yaml(aliases: list[str], upstream_fm: str | None) -> str:
    if not aliases:
        if upstream_fm and "hookAliases:" in upstream_fm:
            if re.search(r"^hookAliases:\s*$", upstream_fm, re.MULTILINE):
                return "hookAliases: \n"
        return "hookAliases: \n"

    if upstream_fm:
        upstream_aliases = parse_hook_aliases_from_front_matter(upstream_fm)
        if upstream_aliases == aliases:
            block = re.search(
                r"^hookAliases:.*?(?=^[A-Za-z_])", upstream_fm, re.MULTILINE | re.DOTALL
            )
            if block:
                return block.group(0)

    lines = ["hookAliases:"]
    for alias in aliases:
        lines.append(f"    - {alias} ")
    return "\n".join(lines) + "\n"


def theme_doc_paths(repo: str, rel_file: str) -> tuple[str, str]:
    rel = rel_file.removeprefix("templates/")
    if repo == "classic-theme":
        return (
            f"{GITHUB_CLASSIC}/templates/{rel}",
            f"themes/classic/templates/{rel}",
        )
    return (
        f"{GITHUB_HUMMINGBIRD}/templates/{rel}",
        f"themes/hummingbird/templates/{rel}",
    )


def format_files_yaml(occurrences: list[Occurrence], upstream_fm: str) -> str:
    if not occurrences:
        existing = extract_files_block(upstream_fm)
        if existing:
            updated = re.sub(
                r"https://github.com/PrestaShop/PrestaShop/blob/[^/]+/",
                "https://github.com/PrestaShop/PrestaShop/blob/9.1.x/",
                existing,
            )
            updated = re.sub(
                r"https://github.com/PrestaShop/PrestaShop/blob/8\.[^/]+/",
                "https://github.com/PrestaShop/PrestaShop/blob/9.1.x/",
                updated,
            )
            updated = updated.replace("product.tml", "product.tpl")
            return updated
        return "files:\n    -\n        url: ''\n        file: ''\n"

    lines = ["files:"]
    for occ in occurrences:
        if occ.repo == "prestashop":
            lines.extend(
                [
                    "    -",
                    f"        url: '{GITHUB_PS}/{occ.file}'",
                    f"        file: {occ.file}",
                ]
            )
        elif occ.repo in {"classic-theme", "hummingbird"}:
            theme = "classic" if occ.repo == "classic-theme" else "hummingbird"
            url, file_path = theme_doc_paths(occ.repo, occ.file)
            lines.extend(
                [
                    "    -",
                    f"      theme: {theme}",
                    f"      url: {url}",
                    f"      file: {file_path}",
                ]
            )
    return "\n".join(lines) + "\n"


def extract_files_block(fm: str) -> str | None:
    match = re.search(r"^files:\n(?:.*?\n)*?(?=^[A-Za-z_])", fm, re.MULTILINE)
    return match.group(0) if match else None


def replace_front_matter_field(fm: str, key: str, new_block: str) -> str:
    pattern = rf"^{re.escape(key)}:.*?(?=^[A-Za-z_])"
    if re.search(pattern, fm, re.MULTILINE | re.DOTALL):
        return re.sub(pattern, new_block, fm, count=1, flags=re.MULTILINE | re.DOTALL)
    return fm


def replace_files_block(fm: str, new_files_block: str) -> str:
    return replace_front_matter_field(fm, "files", new_files_block)


def replace_hook_aliases_block(fm: str, new_aliases_block: str) -> str:
    return replace_front_matter_field(fm, "hookAliases", new_aliases_block)


def replace_type(fm: str, hook_type: str) -> str:
    if re.search(r"^type:\s*", fm, re.MULTILINE):
        return re.sub(
            r"^type:\s*.+$", f"type: {hook_type}", fm, count=1, flags=re.MULTILINE
        )
    return fm


def fix_smarty_semicolons(body: str) -> str:
    return re.sub(r"(\{hook h=['\"][^'\"]+['\"]\});", r"\1", body)


def replace_call_snippet(body: str, snippet: str) -> str:
    if not snippet:
        return body
    pattern = r"(## Call of the Hook in the origin file\n\n```php\n)(.*?)(\n```)"
    if not re.search(pattern, body, re.DOTALL):
        return body
    return re.sub(
        pattern,
        lambda m: m.group(1) + snippet + m.group(3),
        body,
        count=1,
        flags=re.DOTALL,
    )


def restore_protected_scalar_fields(fm: str, upstream_fm: str, keys: list[str]) -> str:
    updated = fm
    for key in keys:
        upstream_val = parse_simple_yaml_value(upstream_fm, key)
        current_val = parse_simple_yaml_value(updated, key)
        if upstream_val and (current_val == "" or current_val is None):
            if re.search(rf"^{re.escape(key)}:\s*", updated, re.MULTILINE):
                if "'" in upstream_val or " " in upstream_val:
                    replacement = f"{key}: '{upstream_val}'"
                else:
                    replacement = f"{key}: {upstream_val}"
                updated = re.sub(
                    rf"^{re.escape(key)}:.*$",
                    replacement,
                    updated,
                    count=1,
                    flags=re.MULTILINE,
                )
    if "hasExample: true" in upstream_fm and "hasExample:" not in updated:
        updated = re.sub(
            r"^(type: .+)$",
            r"\1\nhasExample: true",
            updated,
            count=1,
            flags=re.MULTILINE,
        )
    return updated
