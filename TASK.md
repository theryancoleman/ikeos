# Task: Wire up the weekly platform review viewer to the actual output convention

> Replace this file each time you start a new task. Keep it at project root.
> Commit it with your changes so there's a record of what was intended.

---

## Objective

`app/services/reviews.py`'s `read_latest_review()` / `latest_review_name()` looked for
`*-weekly-review.md` files under `WEEKLY_REVIEW_OUTPUT_DIR`, but the claude-config
`platform-review-narrative` housekeeping task (shipped 2026-07-16) actually writes
`docs/platform-reviews/<YYYY-MM-DD>-review.md` in the claude-config repo. Net effect:
the housekeeping page's platform-review widget permanently showed "no review found"
even though reviews were being produced. Fix the glob/path so the viewer finds the
real output, and confirm the `weekly_platform_review` capability description still
matches reality.

---

## Size

S — single-file glob fix plus env/mount path correction; no schema/API/architecture
change; clear requirements from investigation.

---

## Investigation findings

- `capabilities.json` is not a static repo file — it's a per-vault runtime file written
  by `app/services/capabilities.py`'s `update_capability()` to
  `<VAULT_PATH>/projects/<project_slug>/housekeeping/capabilities.json`. The
  `weekly_platform_review` capability's description text (in
  `DEFAULT_CAPABILITIES`) already accurately describes the new narrative-review task —
  no change needed there.
- Actual output location confirmed via `claude-config/docs/superpowers/specs/2026-07-16-platform-review-narrative-design.md`
  and a real file on disk: `/mnt/c/Server/claude-config/docs/platform-reviews/2026-07-16-review.md`
  (git-tracked directory, filename `<YYYY-MM-DD>-review.md`).
- `WEEKLY_REVIEW_OUTPUT_PATH` was never set in this host's `.env` at all — the
  docker-compose volume mount silently fell back to `/tmp/ikeos-no-weekly-reviews`,
  so the widget had nothing to read regardless of the glob bug.
- Existing tests for `reviews.py` live in `tests/test_blog_drafts.py` (not a dedicated
  `test_reviews.py`) — updated in place rather than creating a new file, to match
  existing project convention.

---

## Fix

- `app/services/reviews.py`: glob pattern `*-weekly-review.md` → `*-review.md` in both
  `latest_review_name()` and `read_latest_review()`. Sort logic unchanged (ISO dates
  sort correctly lexicographically).
- `.env`: added `WEEKLY_REVIEW_OUTPUT_PATH=C:\Server\claude-config\docs\platform-reviews`
  (Windows-style path — this repo's volume-mount env vars use Windows paths on this
  Docker-Desktop-on-Windows host).
- `.env.example`: updated placeholder path and comment to reflect the real convention,
  plus a note on the Windows-path requirement for volume-mount vars.
- `tests/test_blog_drafts.py`: updated `review_dir` fixture-based tests to the new
  filename convention; added a newest-file-picked test.
- `.claude/DECISIONS.md`: appended an entry documenting the mismatch and fix.

---

## Verification contract

1. `docker.exe exec ikeos pytest tests/test_blog_drafts.py -q` — all pass.
2. `docker.exe exec ikeos pytest tests/ -q` — full suite passes, no regressions.
3. `docker.exe compose up -d --build ikeos` — container rebuilds and reports healthy.
4. `curl http://localhost:5009/housekeeping/weekly-review` — renders the real
   `2026-07-16-review.md` content instead of "No review report found yet."
5. `curl http://localhost:5009/housekeeping` — widget also reflects the found review.

---

## Agent loop status

- [x] Implementer: changes complete
- [ ] Reviewer: not required (S-size)
- [x] Verification: all contract steps passed (see below)

---

## Follow-up (outside this task)

None identified.
