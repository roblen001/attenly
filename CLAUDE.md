# Project Rules

<!-- ============================================================
  PROJECT-SPECIFIC CONTEXT — fill in manually after init
  ============================================================
## Project Overview
[One paragraph describing what this project is and does.]

## Key Files & Entry Points
- `src/main.py` — [description]
- `...`

## Tech Stack
- Language/runtime: ...
- Key dependencies: ...
- Database: ...

## Testing
- How to run tests: `...`
- Test location: `tests/`
  ============================================================ -->

## LSP Plugin

- If the pyright-lsp plugin is available, prefer LSP operations (hover, goToDefinition, findReferences, documentSymbol, workspaceSymbol, incomingCalls, outgoingCalls) over Grep/Glob for type lookups, navigating definitions, and finding references
- Check LSP diagnostics after editing Python files to catch type errors early

## Coding Rules

- For python, use **Poetry** for dependency management — use `poetry run` or `poetry shell` instead of activating `.venv` directly (e.g. `poetry run pytest`, `poetry add --group dev <pkg>`)

## File Hygiene

- Never commit `.agileclaude/`, `logs/`, `.venv/`, `.env`, or other gitignored files

## GitHub CLI (`gh`)

- Always use `--json` format for issue/PR queries (e.g. `gh issue view <N> --json title,body,labels`)
- Truncate `gh` error output: `gh ... 2>&1 | head -5`
- On 502/503 errors, retry once after `sleep 5`; if it fails again, move on

---

## Agileclaude Loop — How It Works

This project uses an autonomous multi-agent development loop. A cron-driven dispatcher picks GitHub Issues by priority and FIFO, then dispatches the assigned agent via tmux + Claude Code. Agents hand off work by swapping GitHub Issue labels.

### Workflow Paths

**Standard**: `coordinator → planner → dev → qa → reviewer → merge`

**Fast-track** (small tasks, docs, single-file trivial changes):
`coordinator → dev → reviewer → merge`
Dev adds both `stage/dev-done` + `stage/qa-done`; reviewer runs tests locally.

**Research**: `coordinator → researcher` (analysis only, no code, closes issue)

### Agents

| Agent | Role |
|-------|------|
| `coordinator` | Sprint planning, task breakdown, issue assignment |
| `planner` | Deep research and implementation planning |
| `backend-dev` | Python/API implementation, tests |
| `frontend-dev` | CLI tools, scripts |
| `qa` | Functional testing and code review (never edits code) |
| `reviewer` | Final PR review and merge (**sole merge authority**) |
| `researcher` | Analysis and research reports (no code) |
| `product-manager` | Roadmap and priority updates |
| `coding-god` | High-complexity / stubborn bugs |

### Available Skills

| Skill | Purpose |
|-------|---------|
| `assign-task` | Create a GitHub issue as a task assignment |
| `create-issue` | Create a GitHub issue for the backlog |
| `reassign-task` | Swap agent label + status on an issue |
| `claim-task` | Claim a pending issue |
| `complete-task` | Mark issue done (does not close) |
| `close-issue` | Close an issue with a comment |
| `my-tasks` | List tasks assigned to me |
| `open-pr` | Open a PR and reassign to QA |
| `qa-review` | Submit QA review result |
| `report-finding` | Escalate out-of-scope issues to coordinator |
| `merge-pr` | Rebase, squash-merge, close issue |
| `create-branch` | Create and track a feature branch |
| `write-alert` | Pause loop with a critical alert |
| `send-message` | Send async inter-agent message |
| `log-decision` | Record an architectural decision |
| `log-lesson` | Record a lesson learned |
| `simplify-code` | Review changed code for quality |
| `sync-backlog` | Sync GitHub Issues backlog |
| `plan-sprint` | Create milestone and assign issues |

### GitHub Issue Labels

**Status** (mutually exclusive): `status/pending` · `status/in-progress` · `status/done` · `status/on-hold`

**Agent** (mutually exclusive): `agent/coordinator` · `agent/planner` · `agent/backend-dev` · `agent/frontend-dev` · `agent/qa` · `agent/reviewer` · `agent/researcher`

**Stage** (additive): `stage/planner-done` · `stage/dev-done` · `stage/qa-done` · `stage/reviewer-done`

**Priority**: `priority/1-critical` · `priority/2-high` · `priority/3-medium` · `priority/4-low`

**Type**: `type/feature` · `type/bug` · `type/chore` · `type/refactor`

**Source**: `source/roadmap` · `source/human-message` · `source/qa-finding` · `source/reviewer-finding`

**Special**:
- `fast-track` — skip planner and QA
- `human-verification-required` — trigger Telegram notification
- `require-plan-approval` / `plan-approved` — pause after planner for human sign-off
- `require-merge-approval` / `merge-approved` — pause before merge for human sign-off
- `changes-requested` — human wants revisions (add label then run `cli.py resume`)

### Creating Issues

```bash
# Via dispatcher cli (assigns to coordinator)
python3 /path/to/dispatcher/cli.py task "Description" --priority 2-high --type feature

# Direct gh with labels
gh issue create --title "Fix X" \
  --label "agent/backend-dev,status/pending,priority/3-medium,type/bug"
```

Issue body template:
```markdown
**Branch**: `feature/xyz`
**Open PR**: yes|no

## Objective
[One sentence]

## Context
[Background, patterns, file paths]

## Scope Boundaries
- In scope: ...
- Out of scope: ...
```

### Agent Rules

- After invoking any skill that changes issue state, verify with `gh issue view <N> --json labels,assignees`
- AC violations are bugs, not tech debt — fail the review
- Break large tasks into smaller ones — every task must be reviewable in one pass
- Implementation plans, QA results, and review findings go as **comments** on the issue
