/* Client for the Sol backend (see backend/docs/agent-contract.md). */
import type { Suggestion } from "../components/ui";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export type Language = "auto" | "english" | "taglish";
export type StepEvent = { id: string; label: string; status: "running" | "done" };
export type Card = { type: "roof" | "analysis" | "passport"; data: unknown };
export type Reply = {
  text: string;
  hasMapArtifact: boolean;
  next: Suggestion[];
  cards?: Card[];
  slot?: string | null;
};

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function toError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    const d = body?.detail;
    return new ApiError(d?.code ?? "http_error", d?.message ?? `Request failed (${res.status})`, res.status);
  } catch {
    return new ApiError("http_error", `Request failed (${res.status})`, res.status);
  }
}

/** Send one chat turn and stream its events. Always resolves with the final reply (or throws before streaming). */
export async function streamChat(opts: {
  conversationId: string;
  message: string;
  personaId: string;
  language: Language;
  files?: File[];
  signal?: AbortSignal;
  onStep: (s: StepEvent) => void;
}): Promise<Reply> {
  const form = new FormData();
  form.set("conversation_id", opts.conversationId);
  form.set("message", opts.message);
  form.set("persona_id", opts.personaId);
  form.set("language", opts.language);
  for (const f of opts.files ?? []) form.append("files", f, f.name);

  const res = await fetch(`${BASE}/api/agent/chat`, { method: "POST", body: form, signal: opts.signal });
  if (!res.ok || !res.body) throw await toError(res);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let reply: Reply | null = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      if (block.startsWith(":")) continue; // keepalive comment
      const event = /^event: (.*)$/m.exec(block)?.[1];
      const raw = /^data: (.*)$/m.exec(block)?.[1];
      if (!event || raw === undefined) continue;
      const data = JSON.parse(raw);
      if (event === "step") opts.onStep(data as StepEvent);
      else if (event === "reply") reply = data as Reply;
    }
  }
  if (!reply) throw new ApiError("no_reply", "The server closed the connection without a reply.", 0);
  return reply;
}

export type RoofModel = {
  id: string;
  source: string;
  polygon_lonlat: [number, number][];
  usable_polygon_m: [number, number][];
  area_m2: number;
  usable_area_m2: number;
  azimuth_deg: number;
  tilt_deg: number;
  confidence: "high" | "medium" | "low";
  warnings: string[];
  notes: string[];
  edges_m: number[];
};

export type RoofState = {
  center: { lat: number; lon: number; zoom: number };
  persona: { id: string; city: string };
  roof: RoofModel | null;
  roofMethod: "address" | "draw" | "sketch" | null;
  nextSlot: string;
  needsRoof: boolean;
  layout: { count: number; panels_lonlat: [number, number][][] } | null;
};

/** Returns null when the conversation does not exist yet (nothing sent so far). */
export async function getRoofState(conversationId: string, signal?: AbortSignal): Promise<RoofState | null> {
  const res = await fetch(`${BASE}/api/agent/sessions/${conversationId}/roof`, { signal });
  if (res.status === 404) return null;
  if (!res.ok) throw await toError(res);
  return (await res.json()) as RoofState;
}

export type RoofSubmission =
  | { mode: "drawn"; polygon_lonlat: [number, number][]; roof_type: "flat" | "single_slope" | "gable"; facing?: string }
  | {
      mode: "sketch";
      points_px: [number, number][];
      px_per_m: number;
      scale_source: "default_grid" | "user_measured";
      north_deg: number;
      facing: string;
      roof_type: "flat" | "single_slope" | "gable";
    };

export async function submitRoof(conversationId: string, personaId: string, body: RoofSubmission): Promise<void> {
  const res = await fetch(`${BASE}/api/agent/sessions/${conversationId}/roof?persona_id=${personaId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await toError(res);
}

export async function deleteSession(conversationId: string): Promise<void> {
  try {
    await fetch(`${BASE}/api/agent/sessions/${conversationId}`, { method: "DELETE" });
  } catch {
    /* the chat is removed from the sidebar either way */
  }
}
