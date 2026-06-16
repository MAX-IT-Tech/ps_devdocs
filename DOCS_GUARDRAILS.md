# Docs Guardrails Workflow

This repository uses a four-layer protection model for documentation quality and safe publishing.

## Layer 1: Git Controls

- Use `origin` as fetch-only.
- Use `publish` as the only push remote.
- Activate repository hooks from `.githooks`.

Install once:

```bash
make install-guardrails PUBLISH_URL=git@github.com:<your-user>/docs.git
```

## Layer 2: QA Gate

Run unified checks:

```bash
make qa-docs
```

Run final push gate and write QA stamp:

```bash
make qa-final
```

For historical branches listed in `.githooks/push-policy.json`, use transitional mode
(push-range checks only; remove the branch from the list after rebasing to a clean `feat/*` branch):

```bash
make qa-final-transitional
# optional explicit range:
make qa-final-transitional PUSH_RANGE=origin/local/wip-docs-artifacts..HEAD
```

## Layer 3: Cursor Workflow

- Always apply `.cursor/rules/devdocs-systematic-quality-gates.mdc`.
- Use `.cursor/rules/devdocs-hook-reference-quality.mdc` for hook pages.
- Follow `.cursor/skills/docs-safe-workflow/SKILL.md`.

## Layer 4: GitHub Protection

Server-side workflow:

- `.github/workflows/docs-qa.yml`

Branch protection checklist:

- Require pull requests before merge.
- Require status checks: `Test Build` and `Docs QA Gate`.
- Block force push on protected branches.

## Daily Sequence

1. Work in `feat/*` or `fix/*` branch.
2. Commit: pre-commit runs docs QA + Hugo build.
3. Run final gate: `make qa-final`.
4. Push to `publish` remote.
