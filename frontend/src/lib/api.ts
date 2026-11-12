/* Client for the Sol backend (see backend/docs/agent-contract.md). */
import type { Suggestion } from "../components/ui";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export type Language = "auto" | "english" | "taglish";
export type StepEvent = { id: string; label: string; status: "running" | "done" };
export type Card = { type: "roof" | "analysis" | "passport" | "installers" | "packages" | "export"; data: unknown };

/* ---- lists shown in the side panel ---------------------------------- */
export type InstallerRow = {
  name: string;
  esco: boolean;
  area: string;
  address: string;
  phone: string;
  email: string;
  phones: string[];
  emails: string[];
  website: string;
  lists: string[];
};
export type InstallerList = {
  open?: boolean;
  region: string;
  region_name: string;
  total: number;
  near: string;
  nearby: number;
  rows: InstallerRow[];
  lists: string[];
  disclaimer: string;
  source_url: string;
};
export type PackageRow = {
  id: string;
  installer: string;
  name: string;
  kwp: number;
  panels: string;
  inverter: string;
  battery_kwh: number | null;
  type: "hybrid" | "grid-tied" | "off-grid";
  price_php: number;
  price_note: string;
  area: string;
  link: string | null;
  photo: string | null;
  synthetic: boolean;
  /** false when the price is above the budget maximum; absent when no budget is set */
  within_budget?: boolean;
};
export type PackageList = {
  open?: boolean;
  wanted_kwp: number | null;
  wanted_kind: string | null;
  /** where wanted_kwp came from: the recommended design, or a rough guess from the household's usage */
  basis?: "design" | "usage";
  budget_min?: number | null;
  budget_max?: number | null;
  in_your_area: boolean;
  checked_on: string;
  note: string;
  rows: PackageRow[];
};
export type Listing = { type: "installers"; data: InstallerList } | { type: "packages"; data: PackageList };

/** Pick the list cards out of a reply. */
export function listingsOf(cards: Card[] | undefined): Listing[] {
  return (cards ?? []).filter((c) => c.type === "installers" || c.type === "packages") as Listing[];
}
/** The "download your plan" card of a reply, if there is one. */
export function exportOf(cards: Card[] | undefined): { package_index: number; label: string } | null {
  const c = (cards ?? []).find((x) => x.type === "export");
  return c ? (c.data as { package_index: number; label: string }) : null;
}
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
  if (res.status === 401) signOutListeners.forEach((fn) => fn());
  try {
    const body = await res.json();
    const d = body?.detail;
    return new ApiError(d?.code ?? "http_error", d?.message ?? `Request failed (${res.status})`, res.status);
  } catch {
    // The dev proxy answers with an empty 5xx body when the backend is not running.
    if (res.status >= 502 && res.status <= 504) {
      return new ApiError("server_unreachable", "I couldn't reach the Sol server. Make sure the backend is running on port 8000, then try again.", res.status);
    }
    return new ApiError("http_error", `Request failed (${res.status})`, res.status);
  }
}

/* ---- auth token ---------------------------------------------------- */
const TOKEN_KEY = "sol.token";
const signOutListeners = new Set<() => void>();

export const getToken = (): string | null => {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
};
const setToken = (t: string | null) => {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the user just has to sign in again next visit */
  }
};

/** Called whenever the server rejects the saved token (expired or revoked). */
export function onUnauthorized(fn: () => void): () => void {
  signOutListeners.add(fn);
  return () => signOutListeners.delete(fn);
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const t = getToken();
  return t ? { ...extra, Authorization: `Bearer ${t}` } : extra;
}

export type Household = {
  name: string;
  city: string | null;
  lat: number | null;
  lon: number | null;
  monthlyKwh: number | null;
  template: "night_heavy" | "balanced" | "day_heavy" | null;
};
export type User = { id: string; email: string; name: string; initials: string; household: Household };

async function authRequest(path: string, body: unknown): Promise<User> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api/auth/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch {
    throw new ApiError("server_unreachable", "I couldn't reach the Sol server. Make sure the backend is running on port 8000, then try again.", 0);
  }
  if (!res.ok) throw await toError(res);
  const data = (await res.json()) as { token: string; user: User };
  setToken(data.token);
  return data.user;
}

export const login = (email: string, password: string) => authRequest("login", { email, password });
export const signup = (name: string, email: string, password: string) => authRequest("signup", { name, email, password });

/** The signed-in user, or null when there is no valid saved session. */
export async function fetchMe(): Promise<User | null> {
  if (!getToken()) return null;
  try {
    const res = await fetch(`${BASE}/api/auth/me`, { headers: authHeaders() });
    if (res.status === 401) {
      setToken(null);
      return null;
    }
    if (!res.ok) throw await toError(res);
    return ((await res.json()) as { user: User }).user;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError("server_unreachable", "I couldn't reach the Sol server. Make sure the backend is running on port 8000, then try again.", 0);
  }
}

export async function logout(): Promise<void> {
  const headers = authHeaders();
  setToken(null);
  try {
    await fetch(`${BASE}/api/auth/logout`, { method: "POST", headers });
  } catch {
    /* the token is already forgotten locally */
  }
}

/* ---- chat sessions -------------------------------------------------- */
export type SessionInfo = { id: string; title: string; turnCount: number; updatedAt: number };

export async function listSessions(): Promise<SessionInfo[]> {
  const res = await fetch(`${BASE}/api/agent/sessions`, { headers: authHeaders() });
  if (!res.ok) throw await toError(res);
  return ((await res.json()) as { sessions: SessionInfo[] }).sessions;
}

export async function getSessionHistory(conversationId: string): Promise<{ role: "user" | "model"; text: string }[]> {
  const res = await fetch(`${BASE}/api/agent/sessions/${conversationId}`, { headers: authHeaders() });
  if (!res.ok) throw await toError(res);
  return ((await res.json()) as { history: { role: "user" | "model"; text: string }[] }).history;
}

/** Send one chat turn and stream its events. Always resolves with the final reply (or throws before streaming). */
export async function streamChat(opts: {
  conversationId: string;
  message: string;
  language: Language;
  files?: File[];
  signal?: AbortSignal;
  onStep: (s: StepEvent) => void;
}): Promise<Reply> {
  const form = new FormData();
  form.set("conversation_id", opts.conversationId);
  form.set("message", opts.message);
  form.set("language", opts.language);
  for (const f of opts.files ?? []) form.append("files", f, f.name);

  const res = await fetch(`${BASE}/api/agent/chat`, { method: "POST", body: form, signal: opts.signal, headers: authHeaders() });
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
  roofMethod: "draw" | "sketch" | "address" | null; // "address" only appears in chats saved before address lookup was removed
  nextSlot: string;
  needsRoof: boolean;
  pin?: { lat: number; lon: number } | null;
  layout: {
    count: number;
    panels_lonlat: [number, number][][];
    /** Panel positions the roof could still hold beyond the chosen design. */
    spots_lonlat?: [number, number][][];
    /** Total panels that fit (count + unused spots). */
    capacity?: number;
  } | null;
};

/** Returns null when the conversation does not exist yet (nothing sent so far). */
export async function getRoofState(conversationId: string, signal?: AbortSignal): Promise<RoofState | null> {
  const res = await fetch(`${BASE}/api/agent/sessions/${conversationId}/roof`, { signal, headers: authHeaders() });
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

export type GeoCandidate = { label: string; lat: number; lon: number; source: string };

/** Address search for the map's search box. `degraded` means the lookup service could not be reached. */
export async function geocode(q: string): Promise<{ candidates: GeoCandidate[]; degraded: boolean }> {
  const res = await fetch(`${BASE}/api/geocode`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ q }) });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as { candidates: GeoCandidate[]; degraded: boolean };
}

export async function submitRoof(conversationId: string, body: RoofSubmission): Promise<void> {
  const res = await fetch(`${BASE}/api/agent/sessions/${conversationId}/roof`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await toError(res);
}

/** Download the chosen package (installation area, budget, package and numbers) as a PDF. */
export async function exportPlan(conversationId: string, packageIndex: number): Promise<void> {
  const res = await fetch(`${BASE}/api/agent/sessions/${conversationId}/export?package_index=${packageIndex}`, { headers: authHeaders() });
  if (!res.ok) throw await toError(res);
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? "sol-plan.pdf";
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export async function deleteSession(conversationId: string): Promise<void> {
  try {
    await fetch(`${BASE}/api/agent/sessions/${conversationId}`, { method: "DELETE", headers: authHeaders() });
  } catch {
    /* the chat is removed from the sidebar either way */
  }
}

/* ---- results, assumptions and Solar Passport --------------------------- */
export type Range3 = { bad_year: number | null; expected: number | null; best_case: number | null };
export type ReadinessCheck = {
  id: "size" | "location" | "provider" | "requirements";
  title: string;
  status: "ok" | "watch" | "confirm";
  text: string;
  source: string | null;
};
export type PackageSummary = {
  label: string;
  package_id: string;
  variant: "on_grid" | "hybrid";
  net_metering: boolean;
  kwp: number;
  panel_count: number;
  panel: string;
  inverter: string;
  battery: string | null;
  capex_php: number;
  grid_only_monthly_bill_php: number;
  bill_reduction_pct_year1: number;
  payback_years: Range3;
  net_profit_10y_php: Range3;
  year1_savings_php: number;
  lcoe_php_per_kwh: number | null;
  year1_generation_kwh: number;
  co2_avoided_t_10y: number;
  readiness?: ReadinessCheck[];
};
export type AnalysisSummary = {
  goal: string;
  target_met: boolean | null;
  weather_source: string | null;
  weather_is_approximate: boolean;
  packages: PackageSummary[];
  notes: string[];
  export_credit_php_per_kwh: number;
  unverified_drivers: string[];
  caveat: string;
};
export type PassportRef = { id: string; short_hash: string; verify_path: string; hash: string };
export type SessionResults = { summary: AnalysisSummary | null; passport: PassportRef | null };

export async function getSessionResults(conversationId: string): Promise<SessionResults | null> {
  const res = await fetch(`${BASE}/api/agent/sessions/${conversationId}`, { headers: authHeaders() });
  if (res.status === 404) return null;
  if (!res.ok) throw await toError(res);
  const d = (await res.json()) as SessionResults;
  return { summary: d.summary ?? null, passport: d.passport ?? null };
}

export type AssumptionRecord = {
  key: string;
  value: number | string;
  unit: string;
  source_url: string;
  as_of: string;
  verified: boolean;
  note: string;
};

export async function getAssumptions(): Promise<AssumptionRecord[]> {
  const res = await fetch(`${BASE}/api/assumptions`);
  if (!res.ok) throw await toError(res);
  const d = (await res.json()) as AssumptionRecord[] | { assumptions: AssumptionRecord[] };
  return Array.isArray(d) ? d : d.assumptions;
}

export type VerifyCheck = { name: string; status: "pass" | "fail" | "n/a"; detail: string };
export type VerifyResult = { valid: boolean; checks: VerifyCheck[]; id: string | null; short_hash: string; public_key: string; disclosure: string };

export async function verifyPassport(id: string): Promise<VerifyResult> {
  const res = await fetch(`${BASE}/api/passport/${encodeURIComponent(id)}/verify`);
  if (!res.ok) throw await toError(res);
  return (await res.json()) as VerifyResult;
}

export async function getPassportRecord(id: string): Promise<unknown> {
  const res = await fetch(`${BASE}/api/passport/${encodeURIComponent(id)}`);
  if (!res.ok) throw await toError(res);
  return res.json();
}

/** Paste-to-verify: send the pasted JSON text as is. A changed digit comes back as valid: false. */
export async function verifyPastedPassport(text: string): Promise<VerifyResult> {
  let record: unknown;
  try {
    record = JSON.parse(text);
  } catch {
    throw new ApiError("invalid_record", "That is not valid JSON. Paste the full downloaded Passport.", 422);
  }
  const res = await fetch(`${BASE}/api/passport/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(record),
  });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as VerifyResult;
}

/* ---- Solar Passport rewards (demo): only the seeded solar owner has a Passport ------------------- */
export type RewardPassport = {
  id: string;
  short_hash: string;
  created_at: string;
  verify_path: string;
  installation: { installer: string; installed_on: string; sample: boolean } | null;
  option: string;
  panels: number | null;
  kwp: number | null;
  capex_php: number | null;
  valid: boolean;
};
export type Voucher = {
  id: string;
  title: string;
  value: string;
  partner: string;
  terms: string;
  redeemed: boolean;
  code: string | null;
  redeemed_at: number | null;
};
export type Rewards = { passport: RewardPassport | null; vouchers: Voucher[] };

export async function getRewards(): Promise<Rewards> {
  const res = await fetch(`${BASE}/api/rewards`, { headers: authHeaders() });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as Rewards;
}

export async function redeemVoucher(id: string): Promise<Rewards> {
  const res = await fetch(`${BASE}/api/rewards/${encodeURIComponent(id)}/redeem`, { method: "POST", headers: authHeaders() });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as Rewards;
}
