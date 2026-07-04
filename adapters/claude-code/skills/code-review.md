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

This shows all files changed on this branch versus main (three-dot syntax uses merge-base semantics and works correctly whether on main or a feature branch). Filter the output to files that exist on disk and match `*.py`, `*.html`, `*.js`, `*.css`. Skip symlinks and generated files (e.g., files under `__pycache__/`, `.git/`, or `.build/`). If the result is empty, output "No changed files to review." and stop.

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

After presenting the report, offer to help the user address specific findings manually if they'd like to work through them one by one.
