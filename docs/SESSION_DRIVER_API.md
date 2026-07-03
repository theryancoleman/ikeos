# IkeOS Session Driver API — v0

IkeOS never talks to an AI coding engine directly. It talks to a **session driver**:
an HTTP service that owns engine sessions. Anyone can implement this contract to
drive a different engine. The reference implementation drives Claude Code in tmux.

Base URL: `SESSION_MANAGER_URL` (default `http://host.docker.internal:5010`).

## POST /sessions — create (or find) a session

Request body (JSON):

| field             | type          | meaning                                                                 |
|-------------------|---------------|-------------------------------------------------------------------------|
| `name`            | string        | Session identity AND dedup key. Creating a session whose `name` matches a live session returns 409. |
| `project`         | string        | Project slug, used for grouping/display and vault attribution.          |
| `project_dir`     | string        | Working directory the engine session starts in (host path).             |
| `initial_command` | string / null | Free text handed to the engine on start. See "Ephemeral semantics".     |
| `model`           | string / null | OPTIONAL, driver-defined opaque string selecting the engine model. IkeOS never interprets it; drivers without model selection may ignore it. |

Responses:
- `200/201` → `{"id": "<session-id>", ...}` — the new session's id.
- `409` → `{"session": {"id": "<existing-id>", ...}}` — a live session with this `name` already exists. Callers treat this as success-with-reuse.
- Any other non-2xx → error; IkeOS surfaces it and does not retry.

## Ephemeral semantics (contract-level warning)

`initial_command` **present** ⇒ the session is ephemeral/unattended ⇒ the reference
driver launches the engine with permission prompts disabled
(`--dangerously-skip-permissions` for Claude Code). Implementers MUST document their
equivalent, and deployers MUST treat any endpoint that creates command-bearing
sessions as privileged (IkeOS gates them behind capability flags and the capture token).
`initial_command` **absent** ⇒ interactive session, normal permission behavior.

## GET /sessions — list live sessions
Returns a JSON array; each element includes at least `id`, `name` (`tmux_session` in
the reference driver), `project`, `status` (`"active"` when running), `started_at` (ISO 8601).

## GET /sessions/{id} — inspect one session
`200` with the session object (`status` field as above), `404` if unknown.

## POST /sessions/{id}/command — send text to a live session
Body: `{"command": "<text>", "escape_first": bool}`. `escape_first` clears any
partially-typed input before sending. `2xx` on success.

## Lifecycle & UI endpoints (v0, reference-driver shaped)
`DELETE /sessions/{id}` (stop), `DELETE /sessions/{id}/remove`,
`POST /sessions/{id}/reset`, `POST /sessions/{id}/rename`,
`PATCH /sessions/{id}/remote_control`, `PATCH /sessions/{id}/autonomous_mode`,
`PATCH /sessions/{id}/remote_control_state`, `GET /sessions/{id}/pane`.
These power the IkeOS Sessions UI via a pass-through proxy. A minimal driver may
return `501` for any of them; create/list/inspect/command are the required core.

## Versioning
This is v0: shaped by the Claude Code reference driver. Breaking changes will bump
to `/v1/` paths. Additive optional request fields (like `model`) are non-breaking.
