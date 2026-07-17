# Task: Investigate housekeeping-task vault-entry ownership/permissions inconsistency

> Replace this file each time you start a new task. Keep it at project root.
> Commit it with your changes so there's a record of what was intended.

---

## Objective

Investigate a reported bug: `POST /capture/json` for `type=housekeeping-task` allegedly
writes vault files owned `autoserver:autoserver` mode `0777`, unlike other entry types
(`uid 999:999`, mode `0644`). Find the code-level divergence in
`app/services/vault_entries.py`'s `write_entry()` between the `housekeeping-task` branch
and the generic branch, and fix it so both write paths behave identically.

---

## Size

S — investigation-first task; turned out to require no code change (see Outcome below).

---

## Outcome

**No code-level divergence found. No fix applied.**

Line-by-line comparison of `write_entry()`'s `housekeeping-task` branch vs. the generic
(note/idea/bug/experiment/decision) branch in `app/services/vault_entries.py` shows both
use the identical write mechanism: `target_dir.mkdir(parents=True, exist_ok=True)` (no
explicit mode), `frontmatter.Post(...)`, `open(filepath, "w", encoding="utf-8")`,
`f.write(frontmatter.dumps(post))`. No `os.chmod`/`os.chown`/`subprocess` calls exist
anywhere in `app/` (confirmed via grep). `vault.py` re-exports `write_entry` with no
wrapping/post-processing.

Live testing against the running container reproduced the reported symptom — but showed
it affects **both** the housekeeping-task route (`POST /capture/json`) and the
form-based generic route (`POST /capture`, type=note) **identically**: freshly written
files under the current container session show `root:root` (container view) /
`autoserver:autoserver` (WSL host view), mode `0777`, regardless of entry type. Older
files (written before ~2026-07-16T23:08 UTC, i.e. the last container restart) show the
expected `appuser:appuser` (999:999) / `0644` for both entry types too. The dividing
line is *time of the last container restart*, not code path.

Conclusion: this is a Docker Desktop / WSL2 DrvFs metadata-mapping artifact on the
Windows-hosted `VAULT_PATH` bind mount (`C:\Server\obsidian-vault`), not an ikeos code
bug. It started affecting all new vault writes uniformly around the most recent
container restart and has not self-healed after 40+ minutes. Out of scope for an
in-repo Python fix — no source change would alter the outcome, since both code paths
are already identical and both currently exhibit the symptom.

Test probe files created during investigation were written to
`projects/claude-config/housekeeping/` and `projects/ikeos/notes/` and have been
deleted via `docker exec ikeos rm` (confirmed removed).

---

## Agent loop status

- [x] Implementer: changes complete (no-op — investigation concluded no code fix applies)
- [ ] Reviewer: not required (S-size, no code changed)
- [x] Verification: investigation steps completed; live reproduction performed; no commit made (nothing to commit)

---

## Follow-up (outside ikeos code)

File a vault note/idea for infra follow-up: check Docker Desktop's Windows-drive file
sharing (gRPC FUSE vs VirtioFS) and/or WSL2 `/etc/wsl.conf` DrvFs `metadata` mount
options — something changed around the last `ikeos` container restart that broke
uid/mode metadata reporting for new writes to the Windows-hosted vault path.
