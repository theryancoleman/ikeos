# Council Pipeline UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface pending `council-item` vault entries on the `/housekeeping` dashboard with Discuss/Approve/Decline buttons wired to the already-live backend routes (`app/routes/council.py`, merged and deployed) — the missing piece between a working API and something Ryan can actually click.

**Architecture:** `/housekeeping` already has an established "list of actionable things with per-row buttons" pattern — the Tasks table (`app/templates/housekeeping.html`, rows with Enable/Reset/Run/Delete buttons calling `onclick="fn({{ x | tojson | forceescape }}, this)"`, a shared `_captureToken` JS constant injected once at the top of the page's `<script>` block). This plan adds a second table in that same style rather than inventing a new UI pattern: `_housekeeping_context()` gains `council_items` (pending/in-discussion entries) and `council_pending_count`; the template renders them in a new section with Discuss/Approve/Decline buttons; three new JS functions mirror the existing `toggleTask`/`toggleCapability` fetch-and-repaint pattern exactly.

**Tech Stack:** Flask (routes/services — no new routes needed, `app/routes/council.py` already exists and is live), Jinja2 + vanilla JS (matching the page's existing conventions, no new CSS classes needed — `hk-table`, `hk-pill`, `pill`/`pill-primary-filled`/`pill-danger` all already exist), pytest.

**Spec:** `/mnt/c/Server/obsidian-vault/projects/ikeos/ideas/2026-08-18-unified-weekly-review-pipeline-decision-council-di.md` (the grilled design) — this plan implements the dashboard-widget half of spec item 7 (observability). The push-notification half of item 7 lives in the claude-config repo's Phase 7a (already shipped). This plan was deliberately deferred from `docs/superpowers/plans/2026-08-18-council-pipeline-foundation.md` until that plan's API was live and verified — it now is (`council-item` entries exist on disk today, created by both manual testing and this session's live smoke tests).

## Global Constraints

- Routes stay thin; this plan adds **zero new routes** — `POST /council/<slug>/discuss|approve|decline` already exist and are already token- and capability-gated. This plan is template + one context-builder change only.
- No new JS pattern: match `toggleCapability`'s exact shape (disable button → fetch with `X-Capture-Token: _captureToken` → repaint on success → re-enable button, show error in an adjacent message span on failure). Do not introduce a different fetch/error-handling idiom for this feature.
- `council_pipeline` capability defaults disabled (already shipped) — the widget must render sensibly (empty state, not an error) whether the capability is on or off; the existing capabilities toggle already lets a human enable it from this same page.
- Per this project's UI convention: "For UI or frontend changes, start the dev server and use the feature in a browser before reporting the task as complete." Task 2 includes an explicit manual verification step for this — do not skip it.

---

## File Structure

```
app/routes/housekeeping.py      # MODIFY — _housekeeping_context() gains council_items, council_pending_count
app/templates/housekeeping.html # MODIFY — Council table section + 3 new JS functions
tests/test_housekeeping.py      # MODIFY — context + rendering tests
```

---

### Task 1: `_housekeeping_context()` gains council data

**Files:**
- Modify: `app/routes/housekeeping.py`
- Test: `tests/test_housekeeping.py`

**Interfaces:**
- Consumes: `read_entries(project, entry_type, status_filter)` (already exists, from `app.services.vault`), `project_slug()` (already imported in this file).
- Produces: `_housekeeping_context()`'s returned dict gains `council_items: list[dict]` (newest-first, each a full entry dict as `read_entries` returns — includes `slug`, `title`, `body`, `weeks_open`, `status`) and `council_pending_count: int` (`len(council_items)`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_housekeeping.py`:

```python
def test_housekeeping_index_shows_council_pending_count(client, tmp_path, monkeypatch):
    import app.services.vault_cache as vc
    monkeypatch.setattr(vc, "VAULT_PATH", tmp_path)
    council_dir = tmp_path / "projects" / "claude-config" / "council"
    council_dir.mkdir(parents=True)
    (council_dir / "2026-08-18-recover-weak-signals.md").write_text(
        "---\ntype: council-item\ntitle: Recover weak-signals entries\nproject: claude-config\n"
        "status: pending-review\ncreated: 2026-08-18T00:00:00\ntags: []\n"
        "match_slug: recover-weak-signals\nsource: narrative-review\nsource_review: ''\n"
        "weeks_open: '2'\ndiscussion_session_id: ''\ndecision_ref: ''\n---\n## Description\nBody\n"
    )
    resp = client.get("/housekeeping")
    assert resp.status_code == 200
    assert b"Recover weak-signals entries" in resp.data


def test_housekeeping_index_council_excludes_actioned(client, tmp_path, monkeypatch):
    import app.services.vault_cache as vc
    monkeypatch.setattr(vc, "VAULT_PATH", tmp_path)
    council_dir = tmp_path / "projects" / "claude-config" / "council"
    council_dir.mkdir(parents=True)
    (council_dir / "2026-08-18-done-item.md").write_text(
        "---\ntype: council-item\ntitle: Already actioned item\nproject: claude-config\n"
        "status: actioned\ncreated: 2026-08-18T00:00:00\ntags: []\n"
        "match_slug: done-item\nsource: narrative-review\nsource_review: ''\n"
        "weeks_open: '1'\ndiscussion_session_id: ''\ndecision_ref: ''\n---\n## Description\nBody\n"
    )
    resp = client.get("/housekeeping")
    assert resp.status_code == 200
    assert b"Already actioned item" not in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec ikeos pytest tests/test_housekeeping.py -k council_pending -v`
Expected: FAIL — first test fails because "Recover weak-signals entries" isn't in the response (context doesn't fetch council items yet); second test passes vacuously today (nothing renders any council items at all) but will start actually testing the exclusion once Step 3 lands — run it again after Step 3, not just now.

- [ ] **Step 3: Implement**

In `app/routes/housekeeping.py`, add `read_entries` to the existing `from app.services.vault import (...)` block:

```python
from app.services.vault import (
    delete_housekeeping_task,
    read_entries,
    read_housekeeping_heartbeat,
    read_housekeeping_tasks,
)
```

In `_housekeeping_context()`, add before the `return dict(...)`:

```python
    council_items = read_entries(
        project=project_slug(),
        entry_type="council-item",
        status_filter=["pending-review", "in-discussion"],
    )
```

Add `council_items=council_items, council_pending_count=len(council_items),` to the `return dict(...)` call's arguments.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec ikeos pytest tests/test_housekeeping.py -v`
Expected: PASS, all tests in the file including pre-existing ones.

- [ ] **Step 5: Commit**

```bash
git add app/routes/housekeeping.py tests/test_housekeeping.py
git commit -m "feat: council-item data in housekeeping context"
```

---

### Task 2: Council table + Discuss/Approve/Decline buttons

**Files:**
- Modify: `app/templates/housekeeping.html`
- Test: `tests/test_housekeeping.py`

**Interfaces:**
- Consumes: `council_items`, `council_pending_count` (Task 1). Calls the already-live `POST /council/<slug>/discuss`, `/approve`, `/decline` routes (`app/routes/council.py` — no changes needed there). Uses the page's existing `_captureToken` JS constant (defined once near the top of the `<script>` block, do not redeclare it).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_housekeeping.py`:

```python
def test_housekeeping_index_shows_council_action_buttons(client, tmp_path, monkeypatch):
    import app.services.vault_cache as vc
    monkeypatch.setattr(vc, "VAULT_PATH", tmp_path)
    council_dir = tmp_path / "projects" / "claude-config" / "council"
    council_dir.mkdir(parents=True)
    (council_dir / "2026-08-18-recover-weak-signals.md").write_text(
        "---\ntype: council-item\ntitle: Recover weak-signals entries\nproject: claude-config\n"
        "status: pending-review\ncreated: 2026-08-18T00:00:00\ntags: []\n"
        "match_slug: recover-weak-signals\nsource: narrative-review\nsource_review: ''\n"
        "weeks_open: '2'\ndiscussion_session_id: ''\ndecision_ref: ''\n---\n## Description\nBody\n"
    )
    resp = client.get("/housekeeping")
    assert resp.status_code == 200
    assert b"discussCouncilItem" in resp.data
    assert b"approveCouncilItem" in resp.data
    assert b"declineCouncilItem" in resp.data
    assert b"2026-08-18-recover-weak-signals" in resp.data
    assert b"2 weeks open" in resp.data


def test_housekeeping_index_council_empty_state(client, tmp_path, monkeypatch):
    import app.services.vault_cache as vc
    monkeypatch.setattr(vc, "VAULT_PATH", tmp_path)
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)
    resp = client.get("/housekeeping")
    assert resp.status_code == 200
    assert b"No pending council items" in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec ikeos pytest tests/test_housekeeping.py -k council_action_buttons -v`
Run: `docker exec ikeos pytest tests/test_housekeeping.py -k council_empty_state -v`
Expected: FAIL — neither the table, the JS function names, nor the empty-state string exist in the template yet.

- [ ] **Step 3: Add the Council section to the template**

Read `app/templates/housekeeping.html` first — find the closing `</section>` of the "Outputs" grid (the section containing the Blog Draft / Platform Review / Research Findings `hk-output-card` blocks) and the opening `<!-- ── Configuration ── -->` comment right after it. Insert this new section between them:

```html
  <!-- ── Council ── -->
  <section>
    <div class="ike-eyebrow">Council <span class="eyebrow-count">/ {{ council_pending_count }}</span></div>
    {% if council_items %}
    <div class="hk-table-wrap">
      <table class="hk-table">
        <thead>
          <tr>
            <th class="hk-col-name">Recommendation</th>
            <th class="hk-col-status">Status</th>
            <th class="hk-col-date">Age</th>
            <th class="hk-col-actions">Actions</th>
          </tr>
        </thead>
        <tbody>
          {% for item in council_items %}
          <tr>
            <td class="hk-name">{{ item.title }}</td>
            <td><span class="hk-pill hk-pill--{{ item.status }}">{{ item.status }}</span></td>
            <td class="hk-date">
              {% set weeks = item.weeks_open | int(1) %}
              {{ weeks }} week{{ 's' if weeks != 1 else '' }} open
            </td>
            <td class="hk-actions">
              <button class="pill" onclick="discussCouncilItem({{ item.slug | tojson | forceescape }}, this)">Discuss</button>
              <button class="pill pill-primary-filled" onclick="approveCouncilItem({{ item.slug | tojson | forceescape }}, this)">Approve / Action</button>
              <button class="pill pill-danger" onclick="declineCouncilItem({{ item.slug | tojson | forceescape }}, this)">Decline</button>
              <span class="hk-form-msg" id="council-msg-{{ item.slug }}"></span>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <p class="empty">No pending council items.</p>
    {% endif %}
  </section>

```

This mirrors the existing Tasks table exactly: same `hk-table`/`hk-col-*`/`hk-actions` classes, same `onclick="fn({{ x | tojson | forceescape }}, this)"` pattern the codebase already uses for `toggleTask`/`resetTask`/`runTask`/`deleteTask`, and the same `{% else %}...empty state` shape as the Tasks section.

- [ ] **Step 4: Add the three JS functions**

Read the `<script>` block's existing `toggleCapability` function (it's the closest analog — a fetch that disables its button, sends the token header, and repaints on success) to match its exact style. Add these three functions near it (anywhere in the same `<script>` block is fine, but grouping them together is cleaner):

```javascript
async function _councilAction(slug, action, btn) {
  const msgEl = document.getElementById('council-msg-' + slug);
  const row = btn.closest('tr');
  const allButtons = row.querySelectorAll('button');
  allButtons.forEach(b => b.disabled = true);
  msgEl.textContent = '';
  try {
    const resp = await fetch('/council/' + slug + '/' + action, {
      method: 'POST',
      headers: {'X-Capture-Token': _captureToken},
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      msgEl.textContent = err.error || 'Failed';
      allButtons.forEach(b => b.disabled = false);
      return;
    }
    location.reload();
  } catch (e) {
    msgEl.textContent = 'Network error';
    allButtons.forEach(b => b.disabled = false);
  }
}

function discussCouncilItem(slug, btn) { _councilAction(slug, 'discuss', btn); }
function approveCouncilItem(slug, btn) { _councilAction(slug, 'approve', btn); }
function declineCouncilItem(slug, btn) { _councilAction(slug, 'decline', btn); }
```

A full-page reload on success (rather than the in-place repaint `toggleCapability` does) is the right call here: unlike a capability toggle, a successful Discuss/Approve/Decline call spawns a real background session and/or changes the item's status in a way that should disappear from (or change state in) the pending list — a reload keeps this task's JS simple and correct rather than hand-rolling row removal/repainting logic for three different outcomes.

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker exec ikeos pytest tests/test_housekeeping.py -v`
Expected: PASS, all tests in the file.

- [ ] **Step 6: Manual browser verification**

Per project convention, UI changes need a real browser check, not just the test client. From the ikeos project root:

```bash
docker.exe compose up --build -d ikeos
```

Then:
1. Enable the capability for testing: `curl -s -X PATCH http://localhost:5009/housekeeping/capabilities/council_pipeline -H "Content-Type: application/json" -H "X-Capture-Token: $CAPTURE_TOKEN" -d '{"enabled": true}'` (read `$CAPTURE_TOKEN` via the CRLF-guarded pattern from `.env` first: `grep -m1 '^CAPTURE_TOKEN=' .env | cut -d'=' -f2- | tr -d '\r\n'`).
2. Create one real test council-item: `curl -s -X POST http://localhost:5009/capture/json -H "Content-Type: application/json" -d '{"type": "council-item", "project": "claude-config", "title": "Browser verification test item", "body": "Delete me.", "match_slug": "browser-verify-test"}'`.
3. Visit `http://<homelab-host>:5009/housekeeping` in a browser, confirm the Council section renders with the test item, its weeks-open text, and all three buttons.
4. Click Decline, confirm the page reloads and the item no longer appears (it flipped to `declined`, which is excluded from the `pending-review`/`in-discussion` status filter).
5. If any test council-items remain from this or earlier verification, clean them up: `curl -s -X PATCH http://localhost:5009/entries -d "project=claude-config" -d "type=council-item" -d "filename=<slug>" -d "status=declined"`.
6. Disable the capability again if it was off before this test: repeat step 1 with `"enabled": false`.

- [ ] **Step 7: Commit**

```bash
git add app/templates/housekeeping.html tests/test_housekeeping.py
git commit -m "feat: council table with Discuss/Approve/Decline buttons on housekeeping dashboard"
```

---

## Self-Review Notes (for whoever executes this plan)

- **Spec coverage:** completes the dashboard-widget half of the original spec's observability item. The push-notification half already shipped in the claude-config repo's Phase 7a. Not in scope here: a separate top-level `/dashboard` badge (resolved during grilling — `/housekeeping` is where every sibling review widget already lives, this was a deliberate, already-made decision, not an oversight).
- **No backend changes:** confirmed `app/routes/council.py`'s three routes need no modification — they already return `{"ok": true, "session_id": ...}` / `{"error": ...}` shapes this plan's JS already handles correctly (checks `resp.ok`, reads `err.error` on failure).
- **Type consistency:** `_councilAction(slug, action, btn)` is called with `action` as the literal strings `'discuss'`/`'approve'`/`'decline'`, matching the route path segments in `app/routes/council.py` exactly (`/council/<slug>/discuss`, `/approve`, `/decline`).
