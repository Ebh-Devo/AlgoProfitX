# AlgoProfitX — Development Workflow

## Git Workflow

```
main
  │
  └── dev
       │
       ├── feature/*
       ├── fix/*
       ├── refactor/*
       └── chore/*
```

### Branch Rules

| Branch | Purpose |
|--------|---------|
| `main` | Stable / release — no direct development |
| `dev` | Integration branch — no direct development |
| `feature/*` | New functionality |
| `fix/*` | Bug fixes |
| `refactor/*` | Code restructuring without behaviour change |
| `chore/*` | Maintenance, tooling, documentation |

1. Every implementation task happens on its own feature/fix/refactor/chore branch.
2. Completed branches are merged into `dev` and then deleted.
3. `dev` is tested as an integrated development branch.
4. Only meaningful milestones are promoted from `dev` to `main`.
5. Never commit directly to `main` or `dev`.
6. Never combine unrelated implementation tasks into one branch.

---

## Release Discipline

1. Implement on a `feature/*` or `fix/*` branch.
2. Open a PR from the feature branch into `dev`.
3. Integration-test the merged `dev` build.
4. When `dev` represents a meaningful milestone, open a PR from `dev` into `main`.

---

## Agent Workflow

Both Claude and Antigravity may be used on this project.

### Claude (Claude Code)

Best suited for:

- Focused frontend implementation (components, pages, CSS/styling)
- Isolated component or feature work
- Tests and documentation
- Small refactors with clear scope
- Type checking and build validation

### Antigravity

Best suited for:

- Repository-wide investigation and codebase-level analysis
- Complex multi-component or multi-layer work
- Browser-based visual smoke testing
- Integration-heavy tasks spanning frontend and backend
- Tasks requiring live server interaction

This is guidance, not a hard restriction. Use judgment based on the task.

---

## Task Discipline

Every implementation task must have:

- Explicit scope (what files/pages are in or out of scope)
- API/backend boundary (frontend-only or full-stack)
- Validation requirements (typecheck, tests, build, smoke test)
- Explicit stop condition (what "done" means)

---

## Frontend Redesign Phases

The frontend redesign is structured in phases:

| Phase | Description | Status |
|-------|-------------|--------|
| Phase A | Foundation — tokens, components, shell, mobile nav | Complete |
| Phase B | High-traffic pages — Home, Auth, Dashboard, Marketplace | In progress |
| Phase C | Creator workspace | Planned |
| Phase D | Investor workspace | Planned |
| Phase E | Secondary pages | Planned |

See `docs/FRONTEND_IMPLEMENTATION_STATUS.md` for detailed tracking.
