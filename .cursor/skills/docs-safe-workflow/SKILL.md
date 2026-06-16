# Docs Safe Workflow

Use this skill for any PrestaShop documentation update, especially hook metadata, migration work, and review-comment follow-up.

## Goals

- Enforce systemic quality, not point fixes.
- Ensure links, snippets, and metadata stay valid for the target branch.
- Run deterministic QA before commit and before push.

## Push policy modes

- **Strict (default):** all `feat/*` and `fix/*` branches. Full branch diff from `upstream/9.x`, `feat/*`/`fix/*` naming required, `make qa-final`.
- **Transitional:** branches listed in `.githooks/push-policy.json`. Checks only the push range (new commits), allows `local/*` when explicitly listed, uses `make qa-final-transitional`.

## Mandatory Sequence

1. Identify target branch and source-of-truth repositories.
2. Perform a full-scope audit for the changed area.
3. Apply changes only after mapping all similar occurrences.
4. Run:
   - `python3 scripts/qa_docs_gate.py --scope changed --base-ref upstream/9.x --rebuild-index`
   - local Hugo build via pre-commit hook
5. Before push, run final gate:
   - strict branch: `make qa-final`
   - transitional branch (listed in `.githooks/push-policy.json`): `make qa-final-transitional`

## Policies

- No partial fixes: if one pattern is broken, check full scope for the same pattern.
- Review comments are examples, not full scope.
- Do not replace branch names in URLs without path existence checks.
- Do not link module origins to `PrestaShop/PrestaShop/modules/...`.
- Do not keep obsolete hook pages with no valid source.
- Do not keep truncated call snippets or wrong code fence languages.
