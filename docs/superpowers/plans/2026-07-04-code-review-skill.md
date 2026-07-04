# Code-Review Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a reusable `/code-review` skill at `adapters/claude-code/skills/code-review.md` that evaluates code against the AIOS Engineering Standard.

**Architecture:** The skill is a markdown instruction file for Claude Code agents. It has four phases: load the standard, identify files to review, run the review, and output a structured report. No Python code — the skill is purely an agent instruction document. The engineering standard (`docs/engineering/CLEAN_CODE_FOR_AIOS.md`) is the evaluation rubric and is read at invocation time, so updates to the standard automatically improve the skill.

**Tech Stack:** Claude Code skill file (Markdown + YAML frontmatter), no runtime dependencies.

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Create | `adapters/claude-code/skills/code-review.md` | The reusable code-review skill |
| Read (reference) | `docs/engineering/CLEAN_CODE_FOR_AIOS.md` | Evaluation rubric; skill reads this at invocation |

---

### Task 1: Write the code-review skill file

**Files:**
- Create: `adapters/claude-code/skills/code-review.md`

The skill must handle two invocation modes:
1. **No argument** — review files changed on the current branch (`git diff main...HEAD --name-only` filtered to Python/Jinja2/JS/CSS files)
2. **Path argument** — review the specified file or directory

The skill output must follow the structured report format:
- Executive Summary (1-2 sentences)
- Strengths (bulleted — what the code does well against the standard)
- Findings (each with: title, file:line, why it matters, suggested fix, effort S/M/L, priority Now/Soon/Later)
- First 3 Tasks (concrete, actionable, the highest-value improvements)

- [ ] **Step 1: Write the skill file**

Create `adapters/claude-code/skills/code-review.md` with this exact content:

```markdown
---
name: code-review
description: Review code against the AIOS Engineering Standard. Pass a file/directory path to review it, or no argument to review changed files on the current branch.
---

# AIOS Code Review

**Standard:** `docs/engineering/CLEAN_CODE_FOR_AIOS.md` in the current project.

---

## Phase 1: Load the engineering standard

Read `docs/engineering/CLEAN_CODE_FOR_AIOS.md`. This is the evaluation rubric for the entire review. If the file does not exist in the current project, output:

> "AIOS Engineering Standard not found at docs/engineering/CLEAN_CODE_FOR_AIOS.md. Is this an AIOS project?"

and stop.

---

## Phase 2: Identify files to review

**If a path argument was passed:** review that file or all files under that directory. Filter to: `*.py`, `*.html`, `*.js`, `*.css`.

**If no argument:** run:

```bash
git diff main...HEAD --name-only
```

Filter the output to files that exist on disk and match `*.py`, `*.html`, `*.js`, `*.css`. If the branch is `main` (no divergence), use `git diff HEAD --name-only` instead. If the result is empty, output "No changed files to review." and stop.

List the files you will review before proceeding.

---

## Phase 3: Review each file

For each file, read the full content and evaluate it against every applicable section of the AIOS Engineering Standard. Not all sections apply to every file type:

| Section | .py | .html | .js | .css |
|---------|-----|-------|-----|------|
| Naming | ✓ | ✓ | ✓ | ✓ |
| Function Design | ✓ | — | ✓ | — |
| File & Module Organization | ✓ | ✓ | ✓ | — |
| Comments & Documentation | ✓ | ✓ | ✓ | ✓ |
| Error Handling | ✓ | — | ✓ | — |
| Testing | ✓ | — | — | — |
| Observability | ✓ | — | — | — |
| Configuration | ✓ | — | — | — |
| Security | ✓ | ✓ | ✓ | — |
| Refactoring | ✓ | ✓ | ✓ | ✓ |
| AI-Native Engineering | ✓ | — | — | — |

For each finding, record:
- **Title:** short description
- **File:** `path/to/file.py:L<line>`
- **Why it matters:** one sentence tied to a principle from the standard
- **Suggested fix:** concrete code or change description
- **Effort:** S (< 30 min) / M (30 min–2 h) / L (> 2 h)
- **Priority:** Now (correctness/security) / Soon (maintainability) / Later (style/cleanup)

**What NOT to flag:**
- Style preferences with no functional impact
- Hypothetical future scenarios ("what if we need to scale?")
- Deviations from general conventions if the project has a documented reason (check DECISIONS.md)
- Pre-existing issues not touched by the changed files (unless reviewing a full path)

---

## Phase 4: Output the structured report

Format the report as:

---

## Code Review: AIOS Engineering Standard

**Files reviewed:** N  
**Findings:** N (Now: N, Soon: N, Later: N)

### Executive Summary

[1-2 sentences: overall quality, most important theme]

### Strengths

- [What the code does well, tied to standard principles]

### Findings

#### Finding 1: [Title] — [Priority]

- **File:** `path/to/file.py:L42`
- **Why it matters:** ...
- **Suggested fix:** ...
- **Effort:** S

[Repeat for each finding, sorted: Now first, then Soon, then Later]

### First 3 Tasks

1. [Highest-value fix — concrete action, specific file and line]
2. [Second-highest-value fix]
3. [Third-highest-value fix]

---

After presenting the report, offer: "Run `/code-review --fix` to apply the Now-priority findings automatically (where safe), or address them manually."
```

- [ ] **Step 2: Verify the file was created**

```bash
ls -la /mnt/c/Server/projects/ikeos/adapters/claude-code/skills/code-review.md
wc -l /mnt/c/Server/projects/ikeos/adapters/claude-code/skills/code-review.md
```

Expected: file exists, 80+ lines.

- [ ] **Step 3: Verify the frontmatter is valid**

```bash
python3 -c "
import re
content = open('/mnt/c/Server/projects/ikeos/adapters/claude-code/skills/code-review.md').read()
assert content.startswith('---'), 'missing frontmatter opening'
end = content.index('---', 3)
fm = content[3:end]
assert 'name: code-review' in fm, 'missing name field'
assert 'description:' in fm, 'missing description field'
print('frontmatter OK')
"
```

Expected: `frontmatter OK`

- [ ] **Step 4: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add adapters/claude-code/skills/code-review.md
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add code-review skill for AIOS Engineering Standard"
```

---

### Task 2: Commit the engineering standard document and spec

**Files:**
- Committed: `docs/engineering/CLEAN_CODE_FOR_AIOS.md`
- Committed: `docs/superpowers/specs/2026-07-04-clean-code-for-aios-design.md`

- [ ] **Step 1: Add and commit both documents**

```bash
git -C /mnt/c/Server/projects/ikeos add \
  docs/engineering/CLEAN_CODE_FOR_AIOS.md \
  docs/superpowers/specs/2026-07-04-clean-code-for-aios-design.md
git -C /mnt/c/Server/projects/ikeos commit -m "docs: add AIOS Engineering Standard and Clean Code initiative spec"
```

- [ ] **Step 2: Verify git log**

```bash
git -C /mnt/c/Server/projects/ikeos log --oneline -3
```

Expected: the two new commits appear at the top.

---

### Task 3: Cross-project vault entries

Create vault entries in affected projects so the next claude-config session picks up the global instruction update work.

- [ ] **Step 1: Create claude-config idea for agent instruction updates**

```bash
CAPTURE_TOKEN=$(grep "^CAPTURE_TOKEN=" /mnt/c/Server/projects/ikeos/.env | cut -d= -f2 | tr -d '\r')
curl -s -o /dev/null -X POST http://localhost:5009/capture \
  -H "X-Capture-Token: ${CAPTURE_TOKEN}" \
  -d "type=idea" \
  -d "project=claude-config" \
  -d "title=Update global agent instructions with AIOS Engineering Standard" \
  -d "body=The AIOS Engineering Standard is now published at docs/engineering/CLEAN_CODE_FOR_AIOS.md in the ikeos repo. Global CLAUDE.md and the rules/ files in claude-config should be reviewed and updated to reference or incorporate the standard. Specifically: (1) link to the standard in the global CLAUDE.md ## Code section, (2) review ~/.claude/rules/best-practices.md for gaps vs the standard, (3) update agent type definitions (architect/reviewer/debugger) to reference the standard's Code Review section. Priority: medium — the standard exists and is usable before these updates." \
  -d "priority=medium" \
  -d "effort=medium"
echo "vault entry created"
```

- [ ] **Step 2: Verify entry was created**

```bash
ls -t /mnt/c/Server/obsidian-vault/projects/claude-config/ideas/ | head -3
```

Expected: a new file with today's date at the top.

---

## Self-Review

**Spec coverage:**
- ✅ Code-review skill (Task 1)
- ✅ Engineering standard document committed (Task 2)
- ✅ Cross-project vault entry for claude-config work (Task 3)
- ✅ No automated tests needed — this is a documentation/skill deliverable, not Python code

**Placeholder scan:** None — all steps have exact commands, expected output, and complete file content.

**Type consistency:** N/A — no Python code.
