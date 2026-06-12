// ── State ──────────────────────────────────────────────────────────────────
let sessions   = [];
let selectedId = null;
let gridTimer  = null;
let paneTimer  = null;

// ── URL state ──────────────────────────────────────────────────────────────
function pushSessionToUrl(id) {
  const url = id
    ? location.pathname + '?session=' + encodeURIComponent(id)
    : location.pathname;
  history.replaceState(null, '', url);
}

function readSessionFromUrl() {
  return new URLSearchParams(location.search).get('session');
}

// ── API helper ─────────────────────────────────────────────────────────────
async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  return fetch('/agents' + path, opts);
}

// ── Formatting ─────────────────────────────────────────────────────────────
function fmtAge(startedAt) {
  if (!startedAt) return '—';
  const secs = Math.floor((Date.now() - new Date(startedAt)) / 1000);
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}

function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Card rendering ──────────────────────────────────────────────────────────
function activityChip(s) {
  if (s.status !== 'active' || !s.activity || s.activity === 'idle') return '';
  const cls = s.activity === 'thinking' ? 'activity-thinking' : 'activity-working';
  return `<span class="activity-chip ${cls}">${s.activity}</span>`;
}

function healthBadge(s) {
  if (s.status !== 'active' || !s.health) return '';
  return `<span class="health-badge health-${esc(s.health)}">${esc(s.health)}</span>`;
}

function msgCount(s) {
  const parts = [];
  if (s.message_count) {
    parts.push(`<span class="card-msgs">${s.message_count} msg${s.message_count === 1 ? '' : 's'}</span>`);
  }
  if (s.status === 'active') {
    // != null (not truthy) so that 0% context is still shown
    if (s.context_pct != null) {
      parts.push(`<span class="card-ctx">${s.context_pct}%</span>`);
    } else if (s.tokens_remaining) {
      parts.push(`<span class="card-ctx">${esc(s.tokens_remaining)} left</span>`);
    }
  }
  return parts.join('');
}

function cardFooter(s) {
  if (s.status === 'active') {
    return `
      <button class="pill pill-danger"
              onclick="event.stopPropagation();stopSession('${esc(s.id)}')">Stop</button>
      <button class="pill ${s.remote_control ? 'pill-on' : ''}"
              onclick="event.stopPropagation();toggleRc('${esc(s.id)}')">RC: ${s.remote_control ? 'on' : 'off'}</button>
      <button class="pill ${s.autonomous_mode ? 'pill-on' : ''}"
              onclick="event.stopPropagation();toggleAuto('${esc(s.id)}')">Auto: ${s.autonomous_mode ? 'on' : 'off'}</button>
    `;
  }
  return `
    <button class="pill pill-primary-filled"
            onclick="event.stopPropagation();resetSession('${esc(s.id)}')">Start</button>
    <button class="pill pill-danger pill-ghost"
            onclick="event.stopPropagation();removeSession('${esc(s.id)}')">Remove</button>
  `;
}

function renderCard(s) {
  const activeClass = s.status === 'active' ? ' session-active' : '';
  const selected    = s.id === selectedId ? ' selected' : '';
  const dotClass    = s.status === 'active' ? 'is-active' : 'is-stopped';
  const chip        = activityChip(s);
  return `
    <div class="session-card${activeClass}${selected}"
         data-id="${esc(s.id)}" onclick="openPanel('${esc(s.id)}')">
      ${chip ? `<div class="card-activity">${chip}</div>` : ''}
      <div class="card-body">
        <div class="card-name"><span class="session-dot ${dotClass}"></span>${esc(s.name)}</div>
        <div class="card-project">${esc(s.project)}</div>
        <div class="card-meta">
          <div class="card-meta-left">${healthBadge(s)}</div>
          <div class="card-meta-right">${msgCount(s)}<span class="card-age">${fmtAge(s.started_at)}</span></div>
        </div>
      </div>
      <div class="card-footer">${cardFooter(s)}</div>
    </div>
  `;
}

function updateGrid(newSessions) {
  sessions = [...newSessions].sort((a, b) => (b.status === 'active') - (a.status === 'active'));
  const grid = document.getElementById('card-grid');
  const countEl = document.getElementById('session-count');
  if (countEl) countEl.textContent = '/ ' + String(sessions.length).padStart(2, '0');
  if (!sessions.length) {
    grid.innerHTML = '<div class="empty-state">No sessions yet. Click ＋ New Session to start one.</div>';
    return;
  }
  grid.innerHTML = sessions.map(renderCard).join('');
}

// ── Session polling ─────────────────────────────────────────────────────────
async function pollSessions() {
  try {
    const resp = await fetch('/agents/sessions');
    if (!resp.ok) return;
    const data = await resp.json();
    updateGrid(data);
    if (selectedId) {
      const sel = data.find(s => s.id === selectedId);
      if (sel) renderPanelActions(sel);
    }
  } catch (e) { console.error('pollSessions failed:', e); }
}

// ── Pane polling ────────────────────────────────────────────────────────────
async function pollPane() {
  if (!selectedId) return;
  try {
    const resp = await fetch(`/agents/sessions/${selectedId}/pane`);
    if (!resp.ok) return;
    const data = await resp.json();
    const out = document.getElementById('pane-output');
    const dot = document.getElementById('pane-dot');
    if (!data.active || !data.lines || !data.lines.length) {
      out.textContent = '— session stopped —';
      out.classList.add('pane-stopped');
      dot.style.visibility = 'hidden';
    } else {
      const atBottom = out.scrollHeight - out.scrollTop <= out.clientHeight + 24;
      out.classList.remove('pane-stopped');
      dot.style.visibility = '';
      out.textContent = data.lines.join('\n');
      if (atBottom) out.scrollTop = out.scrollHeight;
    }
  } catch (e) { console.error('pollPane failed:', e); }
}

function startPanePolling() { pollPane(); paneTimer = setInterval(pollPane, 2000); }
function stopPanePolling()  { clearInterval(paneTimer); paneTimer = null; }

// ── Panel ───────────────────────────────────────────────────────────────────
function renderPanelActions(s) {
  const el = document.getElementById('panel-actions');
  if (s.status === 'active') {
    el.innerHTML = `
      <button class="pill ${s.remote_control  ? 'pill-on' : ''}"
              onclick="toggleRc('${esc(s.id)}')">Toggle RC (${s.remote_control  ? 'on' : 'off'})</button>
      <button class="pill ${s.autonomous_mode ? 'pill-on' : ''}"
              onclick="toggleAuto('${esc(s.id)}')">Toggle Auto (${s.autonomous_mode ? 'on' : 'off'})</button>
      <button class="pill" onclick="sendCmd('${esc(s.id)}','/clear')">Clear context</button>
      <button class="pill" onclick="sendCmd('${esc(s.id)}','/compact')">Compact</button>
      <button class="pill" onclick="resetSession('${esc(s.id)}')">Reset session</button>
      <button class="pill pill-danger" onclick="stopSession('${esc(s.id)}')">Stop session</button>
      <button class="pill pill-danger pill-ghost" style="font-size:0.68rem"
              onclick="removeSession('${esc(s.id)}')">Remove</button>
    `;
  } else {
    el.innerHTML = `
      <button class="pill pill-primary-filled" onclick="resetSession('${esc(s.id)}')">Start session</button>
      <button class="pill pill-danger pill-ghost" style="font-size:0.68rem"
              onclick="removeSession('${esc(s.id)}')">Remove</button>
    `;
  }
}

function syncCaptureProject(slug) {
  const sel = document.getElementById('cap-project');
  if (!sel) return;
  const opt = [...sel.options].find(o => o.value === slug);
  if (opt) sel.value = slug;
}

function openPanel(id) {
  const s = sessions.find(x => x.id === id);
  if (!s) return;
  selectedId = id;
  document.getElementById('panel-title').textContent    = s.name;
  document.getElementById('panel-subtitle').textContent = s.project;
  renderPanelActions(s);
  document.getElementById('pane-output').textContent = '…';
  document.getElementById('pane-output').classList.remove('pane-stopped');
  document.getElementById('detail-col').classList.add('open');
  document.querySelectorAll('.session-card')
    .forEach(el => el.classList.toggle('selected', el.dataset.id === id));
  stopPanePolling();
  startPanePolling();
  pushSessionToUrl(id);
  syncCaptureProject(s.project);
}

function closePanel() {
  selectedId = null;
  stopPanePolling();
  document.getElementById('detail-col').classList.remove('open');
  document.querySelectorAll('.session-card').forEach(el => el.classList.remove('selected'));
  pushSessionToUrl(null);
  const sel = document.getElementById('cap-project');
  if (sel && sel.options.length) sel.selectedIndex = 0;
}

// ── Actions ─────────────────────────────────────────────────────────────────
async function stopSession(id) {
  await api('DELETE', '/sessions/' + id);
  await pollSessions();
  if (selectedId === id) closePanel();
}

async function resetSession(id) {
  await api('POST', '/sessions/' + id + '/reset');
  await pollSessions();
}

async function removeSession(id) {
  await api('DELETE', '/sessions/' + id + '/remove');
  await pollSessions();
  if (selectedId === id) closePanel();
}

async function toggleRc(id) {
  await api('PATCH', '/sessions/' + id + '/remote_control');
  await pollSessions();
}

async function toggleAuto(id) {
  await api('PATCH', '/sessions/' + id + '/autonomous_mode');
  await pollSessions();
}

async function sendCmd(id, cmd) {
  await api('POST', '/sessions/' + id + '/command', { command: cmd });
  await pollSessions();
}

async function sendPanelCmd() {
  const input = document.getElementById('panel-cmd');
  const cmd   = input.value.trim();
  if (!cmd || !selectedId) return;
  input.value = '';
  await api('POST', '/sessions/' + selectedId + '/command', { command: cmd });
}

// ── Capture column ──────────────────────────────────────────────────────────
async function submitCapture() {
  const project = document.getElementById('cap-project')?.value;
  const type    = document.getElementById('cap-type')?.value;
  const title   = document.getElementById('cap-title')?.value?.trim();
  const body    = document.getElementById('cap-body')?.value?.trim();
  const msgEl   = document.getElementById('capture-msg');

  if (!title) { showCaptureMsg('Title is required', true); return; }

  const payload = { type, project, title, body: body || '' };
  if (type === 'idea') { payload.priority = 'medium'; payload.effort = 'medium'; }

  try {
    const resp = await fetch('/capture/json', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (resp.ok) {
      document.getElementById('cap-title').value = '';
      document.getElementById('cap-body').value  = '';
      showCaptureMsg('Saved. The vault remembers.', false);
      setTimeout(() => { if (msgEl) msgEl.textContent = ''; }, 3000);
    } else {
      showCaptureMsg(data.error || 'Couldn\'t save — try again in a moment.', true);
    }
  } catch (e) {
    showCaptureMsg('Couldn\'t save — try again in a moment.', true);
  }
}

function showCaptureMsg(text, isError) {
  const el = document.getElementById('capture-msg');
  if (!el) return;
  el.textContent = text;
  el.className = 'capture-msg' + (isError ? ' error' : '');
}

// ── Modal ────────────────────────────────────────────────────────────────────
function openModal()  { document.getElementById('modal-overlay').classList.add('open'); }
function closeModal() {
  document.getElementById('modal-overlay').classList.remove('open');
  document.getElementById('new-session-form').reset();
  updateModalDir(document.getElementById('m-project').value);
}

function updateModalDir(slug) {
  document.getElementById('m-dir').value = '/mnt/c/Server/projects/' + slug;
}

async function submitNewSession(e) {
  e.preventDefault();
  const fd = new FormData(e.target);
  await api('POST', '/sessions', {
    name:           fd.get('name'),
    project:        fd.get('project'),
    project_dir:    fd.get('project_dir'),
    remote_control: false,
  });
  closeModal();
  await pollSessions();
}

// ── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  updateGrid(window.INITIAL_SESSIONS || []);
  gridTimer = setInterval(pollSessions, 4000);

  const urlSession = readSessionFromUrl();
  if (urlSession) {
    const found = (window.INITIAL_SESSIONS || []).find(s => s.id === urlSession);
    if (found) openPanel(urlSession);
  }
});
