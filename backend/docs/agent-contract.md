> **Auth:** every `/api/agent/*` call needs `Authorization: Bearer <token>` from `POST /api/auth/login` or `/api/auth/signup`. The household (name, city, usage) comes from the account, so `persona_id` no longer exists. `GET /api/agent/sessions` lists the signed-in user's chats; other users' conversation ids return 404.

# Sol agent API: frontend contract

Everything here is implemented in `backend/`. The payloads mirror the types in `frontendv2/src` (`AgentStep`, `Suggestion`, `AgentMsg.reply`), so the existing UI state can be filled directly. Interactive docs: `http://127.0.0.1:8000/docs`.

Run the backend (from `backend/`): `..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000`
CORS allows `http://localhost:5173` and `http://127.0.0.1:5173` (change with `CORS_ORIGINS`).

## 1. Send a message

`POST /api/agent/chat` with `multipart/form-data` (use `FormData`):

| Field | Required | Notes |
|---|---|---|
| `conversation_id` | yes | A random UUID created by the client for each new chat. 16 to 64 characters of letters, digits, `-`, `_`. **It is the access key to that conversation, so do not use short or guessable ids.** |
| `message` | yes unless files | Up to 4000 characters. A files-only message may send `""` or the literal `Attached files`. |
| `language` | no (`auto`) | `auto`, `english`, `taglish`. |
| `files` | no | Up to 6 of JPEG, PNG, WebP, PDF, 5 MB each. Type is checked from the file bytes. Files are read in memory and never stored. |

Query `?stream=false` returns the finished message as JSON instead of SSE.

### Streaming (default): server-sent events

`EventSource` cannot POST, so read the response body with `fetch`:

```ts
async function sendTurn(form: FormData, on: { step(s: AgentStep): void; reply(r: Reply): void }) {
  const res = await fetch("http://127.0.0.1:8000/api/agent/chat", { method: "POST", body: form });
  if (!res.ok) throw await res.json();               // {detail:{code,message,hint}}
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, i); buf = buf.slice(i + 2);
      if (block.startsWith(":")) continue;           // keepalive comment
      const event = /^event: (.*)$/m.exec(block)?.[1];
      const data = JSON.parse(/^data: (.*)$/m.exec(block)![1]);
      if (event === "step") on.step(data);           // {id, label, status: "running" | "done"}
      if (event === "reply") on.reply(data);
    }
  }
}
```

Events, in order: `turn` → `step`\* → `reply` → `done`. A `: keepalive` comment is sent every 10 s while the server waits.

- **`step`** `{id, label, status}`. `id` is stable (`s0`, `s1`, ...): each id arrives once as `running` and once as `done`. Update the step with the same id (same as `AgentStep`). `s0` is always "Reading your message".
- **`reply`** `{text, hasMapArtifact, next, cards, slot}`:
  - `text`: plain text, no markdown.
  - `hasMapArtifact`: show the Roof Map card and open the right panel.
  - `next`: up to 4 suggestions `{id, label, hint?, text}`; clicking one sends its `text` as the next message (same as `Suggestion`).
  - `cards` (extra, safe to ignore): structured results for later UI: `{type: "roof" | "analysis" | "passport", data}`.
  - `slot` (extra): what the agent is asking about now (`roof_method`, `roof_address`, `roof_pick`, `roof_draw`, `load`, `budget`, `goal`, `goal_param`, `confirm`, `change`, `run`, `done`).
- **Always-reply guarantee:** a turn never ends without `reply` then `done`, even if Gemini fails, a tool fails, or the turn times out (75 s). Failures become a normal reply, so the UI never needs an error state for a stream that dies mid-way. HTTP errors only happen **before** streaming starts (see section 5).

### JSON mode (`?stream=false`)

Returns `{conversationId, phase: "done", steps: [...], reply: {...}}`, i.e. an `AgentMsg` you can store as is (all steps `done`).

## 2. The map panel and roof hand-off

The roof is chosen in chat (type an address, draw, or sketch). The agent sets `hasMapArtifact: true` when the map panel should open. Data for the panel:

- `GET /api/agent/sessions/{id}/roof` returns `{roof, roofMethod, nextSlot, needsRoof, layout, roofSummary}`.
  - `roof.polygon_lonlat` is a closed GeoJSON ring `[lon, lat]`; `roof.usable_polygon_m` and `roof.polygon_m` are local metres (x east, y north, origin at the roof centroid).
  - `layout.panels_lonlat` (after an analysis) is a list of 4-corner rings for the recommended option, ready to overlay.
- When the user **draws on the map** or **sketches on the canvas**, send the result here, then send a normal chat message (for example `"I've finished my roof"`); the agent acknowledges it on that turn:

`POST /api/agent/sessions/{id}/roof`, JSON, one of:

```jsonc
{ "mode": "drawn",  "polygon_lonlat": [[121.04,14.67], ...], "roof_type": "flat|single_slope|gable",
  "tilt_deg": 12, "azimuth_deg": 180, "facing": "auto|N|NE|E|SE|S|SW|W|NW", "setback_m": 0.5 }
{ "mode": "sketch", "points_px": [[0,0],[220,0],[220,160],[0,160]], "px_per_m": 20,
  "scale_source": "default_grid|user_measured", "north_deg": 0, "facing": "auto", "roof_type": "flat" }
{ "mode": "address", "lat": 14.676, "lon": 121.0437 }
```

- Sketch: `px_per_m` is the canvas scale; `scale_source` says whether the user measured it (`user_measured` gives `medium` confidence, `default_grid` gives `low`). `north_deg` is how far the top of the canvas is rotated from true north. The sketch is placed at the address the user already chose, otherwise at the household's city.
- Precedence for direction: `azimuth_deg`, then `facing`, then a guess from the roof shape. Compass degrees: 0 north, 90 east, 180 south, 270 west.
- Returns `{roof, nextSlot}`; `409 turn_in_progress` if a chat turn is running for that conversation.

The same roof services are also plain endpoints (no agent): `POST /api/geocode`, `/api/roof/from-address`, `/api/roof/finalize`, `/api/roof/from-sketch`, `/api/roof/layout`.

## 3. Other session endpoints

- `GET /api/agent/sessions/{id}`: profile, `nextSlot`, summary, passport, history (404 if unknown).
- `DELETE /api/agent/sessions/{id}`: matches the UI's "delete chat".
- The conversation lives on the server by `conversation_id`; the client does not resend history. After a page reload the client can read it back from `GET .../sessions/{id}`.

## 4. Passport and results (for later cards)

- `POST /api/passport` `{session_id, package_index?}` issues a Solar Passport. `GET /api/passport/{id}` fetches it, `GET /api/passport/{id}/verify` verifies it, `GET /verify/{id}` is a no-JS page (green or red) the QR code can point to.
- `POST /api/passport/verify` takes a pasted record (`body`, `hash`, `prev_hash`, `signature`) and checks it against Sol's own key and ledger, so changing one digit fails. This powers the tamper test in the demo.
- Forms path without the agent: `POST /api/load/estimate`, `/api/optimize`, `/api/simulate`, `GET /api/products`, `POST /api/products/search` (SSE), `GET /api/assumptions`.

## 5. Errors

HTTP errors are always `{"detail": {"code", "message", "hint"}}`:

| Status | code | When |
|---|---|---|
| 409 | `turn_in_progress` | A turn is already running for that `conversation_id` |
| 422 | `invalid_conversation_id`, `unauthorized`, `invalid_language`, `empty_message`, `message_too_long`, `too_many_files`, `invalid_request`, `invalid_polygon`, ... | Bad input |
| 413 / 415 | `file_too_large` / `unsupported_file_type` | Attachment rejected |
| 429 | `rate_limited` | More than 20 messages a minute for one conversation |
| 404 | `not_found` | Unknown conversation or Passport |

## 6. Behaviour worth knowing

- The agent asks one question at a time and always returns clickable choices in `next`. Known choice texts are matched exactly, so clicking is deterministic and works without Gemini.
- With `GEMINI_API_KEY` set, Gemini phrases replies and understands free text. On a rate limit or outage the same turn is answered by the built-in rule-based agent (a step "Switching to quick mode" appears). In that mode results are in English and photos cannot be read.
- Every number in the text comes from tool results. If Gemini writes a number that cannot be traced, the text is replaced by a template built from the tool results.
- All results are estimates for a licensed installer to confirm. Demo data (households, demo roofs, product catalog) is synthetic. Several assumptions are **unverified placeholders** (export credit, installation cost, fixed charges, emission factor); see `GET /api/assumptions?verified=false`.
- The `cards` and `slot` fields, `GET .../roof` and the Passport endpoints are available now, but the current UI renders only `text`, the Roof Map card and `next`.
