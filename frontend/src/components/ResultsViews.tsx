/* Overview (package comparison + math drawer) and Saved Records (Solar Passport) views. */
import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import {
  exportPlan,
  getAssumptions,
  getPassportRecord,
  getSessionResults,
  verifyPassport,
  verifyPastedPassport,
  type AnalysisSummary,
  type AssumptionRecord,
  type PassportRef,
  type ReadinessCheck,
  type Range3,
  type VerifyResult,
} from "../lib/api";

const php = (v: number | null | undefined) =>
  v === null || v === undefined ? "n/a" : `₱${Math.round(v).toLocaleString("en-PH")}`;
const years = (v: number | null) => (v === null ? "not within 10 years" : `${v.toFixed(1)} yrs`);
const errText = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong.");

const SCENARIOS = [
  ["Bad year", "Low-yield weather year (about the 10th percentile), with tariff and export-credit growth at the pessimistic rates (0%)."],
  ["Expected", "Median weather year, with expected growth rates (3% a year)."],
  ["Best case", "High-yield weather year (about the 90th percentile), with optimistic growth rates (5% a year)."],
];

const shell = "flex h-full flex-1 flex-col overflow-y-auto p-6 text-[#111111]";
const card = "rounded-[14px] border border-[#f0f0ee] bg-[#fafaf9] p-4";
const btn = "rounded-[8px] bg-[#111111] px-3.5 py-1.5 text-[12px] font-medium text-white transition-colors hover:bg-[#333333]";
const btnGhost = "rounded-[8px] border border-[#e5e5e3] px-3.5 py-1.5 text-[12px] font-medium text-[#111111] hover:bg-[#fafaf9]";

function Empty({ title, text, onNewChat }: { title: string; text: string; onNewChat: () => void }) {
  return (
    <div className="flex h-full flex-1 flex-col items-center justify-center p-8 text-center">
      <h2 className="text-[18px] font-semibold">{title}</h2>
      <p className="mt-1 max-w-[380px] text-[13px] text-[#787774]">{text}</p>
      <button type="button" onClick={onNewChat} className={`mt-5 ${btn}`}>
        Return to chat
      </button>
    </div>
  );
}

function RangeRow({ label, r, fmt }: { label: string; r: Range3; fmt: (v: number | null) => string }) {
  return (
    <div className="mt-2 text-[12px]">
      <div className="text-[#787774]">{label}</div>
      <div className="font-medium">
        {fmt(r.expected)} <span className="font-normal text-[#787774]">(bad year {fmt(r.bad_year)}, best case {fmt(r.best_case)})</span>
      </div>
    </div>
  );
}

/* ---- Math drawer: formulas, assumptions with sources, scenario definitions ---- */
function MathDrawer({ open, onClose, summary }: { open: boolean; onClose: () => void; summary: AnalysisSummary }) {
  const [items, setItems] = useState<AssumptionRecord[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!open || items) return;
    getAssumptions().then(setItems).catch((e) => setErr(errText(e)));
  }, [open, items]);
  if (!open) return null;
  return (
    <div className="fixed inset-x-0 bottom-0 z-50 max-h-[70vh] overflow-y-auto rounded-t-[18px] border border-[#f0f0ee] bg-white p-5 shadow-[0_-8px_30px_rgba(0,0,0,0.08)]" role="dialog" aria-label="Show the math">
      <div className="flex items-center justify-between">
        <h3 className="text-[15px] font-semibold">Show the math</h3>
        <button type="button" onClick={onClose} className={btnGhost}>Close</button>
      </div>
      <div className="mt-3 grid gap-4 text-[12px] md:grid-cols-2">
        <section>
          <h4 className="font-semibold">How the numbers are made</h4>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-[#787774]">
            <li>Hourly solar output for 16 weather years (PVGIS-ERA5, a modelled estimate), scaled to your system size.</li>
            <li>Each hour: sun covers the load first, extra charges the battery or is exported, any shortfall comes from the grid.</li>
            <li>Net metering: exports earn a credit of about {php(summary.export_credit_php_per_kwh)} per kWh. Credits are banked month to month, offset energy charges only, and are never paid out.</li>
            <li>Savings = bill without solar minus bill with solar. Payback, NPV, IRR and LCOE come from the cash flow after O&amp;M and replacements.</li>
          </ul>
          {summary.weather_is_approximate && <p className="mt-2 text-[#b45309]">Sunlight data is an approximate typical year because PVGIS could not be reached.</p>}
        </section>
        <section>
          <h4 className="font-semibold">Scenarios</h4>
          <dl className="mt-1 space-y-1">
            {SCENARIOS.map(([k, v]) => (
              <div key={k}>
                <dt className="font-medium">{k}</dt>
                <dd className="text-[#787774]">{v}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
      <h4 className="mt-4 text-[12px] font-semibold">Assumptions and sources</h4>
      {err && <p className="text-[12px] text-[#b00020]">{err}</p>}
      {!items && !err && <p className="text-[12px] text-[#787774]">Loading…</p>}
      {items && (
        <table className="mt-1 w-full text-left text-[11px]">
          <thead className="text-[#787774]">
            <tr><th className="py-1 pr-2">Assumption</th><th className="pr-2">Value</th><th className="pr-2">As of</th><th>Source</th></tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.key} className="border-t border-[#f0f0ee] align-top">
                <td className="py-1 pr-2">{a.key.replace(/_/g, " ")}</td>
                <td className="pr-2 whitespace-nowrap">{String(a.value)} {a.unit}</td>
                <td className="pr-2 whitespace-nowrap">{a.as_of}</td>
                <td>
                  {a.source_url ? <a href={a.source_url} target="_blank" rel="noreferrer" className="text-[#ea580c] underline">source</a> : <span className="text-[#787774]">{a.note || "judgement, disclosed"}</span>}
                  {!a.verified && <span className="ml-1 rounded bg-[#fff7ed] px-1 text-[#c2410c]">unverified</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="mt-4 text-[11px] text-[#787774]">{summary.caveat}</p>
    </div>
  );
}

/* Meralco's "four things to know before investing", checked for one option. */
const READY_STYLE = {
  ok: { label: "Looks fine", cls: "text-[#1b7f3b]" },
  watch: { label: "Watch", cls: "text-[#b45309]" },
  confirm: { label: "Confirm", cls: "text-[#787774]" },
} as const;

function Readiness({ checks }: { checks: ReadinessCheck[] }) {
  return (
    <div className="mt-3 border-t border-[#f0f0ee] pt-2.5">
      <div className="text-[11px] font-medium uppercase tracking-wide text-[#787774]">Before you invest</div>
      {checks.map((c) => (
        <details key={c.id} open={c.status === "watch"} className="mt-1.5 text-[12px]">
          <summary className="cursor-pointer select-none">
            <span className={`font-medium ${READY_STYLE[c.status].cls}`}>{READY_STYLE[c.status].label}</span> · {c.title}
          </summary>
          <p className="mt-1 text-[11px] leading-relaxed text-[#787774]">
            {c.text}
            {c.source && (
              <>
                {" "}
                <a href={c.source} target="_blank" rel="noreferrer" className="underline">Meralco</a>
              </>
            )}
          </p>
        </details>
      ))}
    </div>
  );
}

/* ---- Overview ---- */
export function OverviewView({ conversationId, onNewChat }: { conversationId: string | null; onNewChat: () => void }) {
  const [summary, setSummary] = useState<AnalysisSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [mathOpen, setMathOpen] = useState(false);

  useEffect(() => {
    setSummary(null);
    setErr(null);
    if (!conversationId) return;
    setLoading(true);
    getSessionResults(conversationId)
      .then((r) => setSummary(r?.summary ?? null))
      .catch((e) => setErr(errText(e)))
      .finally(() => setLoading(false));
  }, [conversationId]);

  if (loading) return <div className={shell}><p className="text-[13px] text-[#787774]">Loading your results…</p></div>;
  if (err) return <Empty title="Overview & Analytics" text={err} onNewChat={onNewChat} />;
  if (!summary) {
    return <Empty title="Overview & Analytics" text="No results yet. Tell Sol about your installation site, usage, budget and goal in the chat, then ask it to run the numbers." onNewChat={onNewChat} />;
  }
  return (
    <div className={shell}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-[18px] font-semibold">Overview & Analytics</h2>
          <p className="text-[12px] text-[#787774]">Suggested prices come from demo or public listings. Confirm with the seller.</p>
        </div>
        <button type="button" onClick={() => setMathOpen(true)} className={btn}>Show the math</button>
      </div>
      {summary.target_met === false && <p className="mt-3 text-[12px] text-[#b45309]">No option within your budget reaches your bill-cut target. This is the closest one.</p>}
      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        {summary.packages.map((p, i) => (
          <article key={p.package_id} className={card}>
            <div className="text-[11px] font-medium uppercase tracking-wide text-[#ea580c]">{p.label}</div>
            <div className="mt-1 text-[20px] font-semibold">{php(p.capex_php)}</div>
            <div className="text-[12px] text-[#787774]">{p.panel_count} panels · {p.kwp} kWp · {p.variant === "hybrid" ? "hybrid" : "on-grid"}</div>
            <div className="mt-2 text-[12px]">{p.panel}</div>
            <div className="text-[12px]">{p.inverter}</div>
            {p.battery && <div className="text-[12px]">{p.battery}</div>}
            <div className="mt-2 text-[12px]">Bill now about {php(p.grid_only_monthly_bill_php)} a month, down about {p.bill_reduction_pct_year1}% in year 1</div>
            <RangeRow label="Payback" r={p.payback_years} fmt={years} />
            <RangeRow label="10-year net profit" r={p.net_profit_10y_php} fmt={php} />
            <div className="mt-2 text-[11px] text-[#787774]">
              Year 1: {Math.round(p.year1_generation_kwh).toLocaleString()} kWh · LCOE {p.lcoe_php_per_kwh ?? "n/a"} ₱/kWh · CO₂ avoided {p.co2_avoided_t_10y} t over 10 years
            </div>
            {p.readiness && <Readiness checks={p.readiness} />}
            <button
              type="button"
              className={`mt-3 ${btnGhost}`}
              onClick={() => conversationId && exportPlan(conversationId, i).catch((e) => window.alert(errText(e)))}
            >
              Export plan
            </button>
          </article>
        ))}
      </div>
      {summary.unverified_drivers.length > 0 && (
        <p className="mt-3 text-[12px] text-[#b45309]">Unverified placeholders drive these results: {summary.unverified_drivers.join(", ").replace(/_/g, " ")}.</p>
      )}
      <p className="mt-3 text-[11px] text-[#787774]">{summary.caveat}</p>
      <MathDrawer open={mathOpen} onClose={() => setMathOpen(false)} summary={summary} />
    </div>
  );
}

/* ---- Saved Records: Solar Passport ---- */
function Checks({ res }: { res: VerifyResult }) {
  return (
    <div>
      <div className={`text-[14px] font-semibold ${res.valid ? "text-[#1b7f3b]" : "text-[#b00020]"}`}>{res.valid ? "Verified" : "Verification failed"}</div>
      <ul className="mt-2 space-y-1 text-[12px]">
        {res.checks.map((c) => (
          <li key={c.name}>
            <span className={c.status === "pass" ? "text-[#1b7f3b]" : c.status === "fail" ? "text-[#b00020]" : "text-[#787774]"}>{c.status}</span>{" "}
            <b>{c.name.replace(/_/g, " ")}</b>
            {c.detail && <span className="text-[#787774]"> · {c.detail}</span>}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] text-[#787774]">{res.disclosure}</p>
    </div>
  );
}

export function SavedView({ conversationId, onNewChat }: { conversationId: string | null; onNewChat: () => void }) {
  const [passport, setPassport] = useState<PassportRef | null>(null);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pasted, setPasted] = useState("");
  const [pasteResult, setPasteResult] = useState<VerifyResult | null>(null);
  const [pasteErr, setPasteErr] = useState<string | null>(null);

  useEffect(() => {
    setPassport(null);
    setResult(null);
    setErr(null);
    setPasteResult(null);
    if (!conversationId) return;
    setLoading(true);
    getSessionResults(conversationId)
      .then(async (r) => {
        const p = r?.passport ?? null;
        setPassport(p);
        if (p) setResult(await verifyPassport(p.id));
      })
      .catch((e) => setErr(errText(e)))
      .finally(() => setLoading(false));
  }, [conversationId]);

  const download = async () => {
    if (!passport) return;
    try {
      const rec = await getPassportRecord(passport.id);
      const url = URL.createObjectURL(new Blob([JSON.stringify(rec, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${passport.id}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(errText(e));
    }
  };

  const checkPasted = async () => {
    setPasteErr(null);
    setPasteResult(null);
    try {
      setPasteResult(await verifyPastedPassport(pasted));
    } catch (e) {
      setPasteErr(errText(e));
    }
  };

  if (loading) return <div className={shell}><p className="text-[13px] text-[#787774]">Loading…</p></div>;
  if (err) return <Empty title="Saved Records" text={err} onNewChat={onNewChat} />;
  if (!passport) {
    return <Empty title="Saved Records" text="No Solar Passport yet. Run the numbers in the chat, then ask Sol to create your Solar Passport." onNewChat={onNewChat} />;
  }
  const verifyUrl = `${window.location.origin}${passport.verify_path}`;
  return (
    <div className={shell}>
      <h2 className="text-[18px] font-semibold">Solar Passport</h2>
      <div className={`mt-3 ${card}`}>
        <div className="text-[12px] text-[#787774]">Record</div>
        <div className="font-mono text-[14px]">{passport.id}</div>
        <div className="mt-1 text-[12px] text-[#787774]">Hash <span className="font-mono text-[#111111]">{passport.short_hash}</span></div>
        <div className="mt-3 flex flex-wrap gap-2">
          <a href={passport.verify_path} target="_blank" rel="noreferrer" className={btn}>Open verify page</a>
          <button type="button" onClick={download} className={btnGhost}>Download JSON</button>
          <button type="button" onClick={() => navigator.clipboard?.writeText(verifyUrl)} className={btnGhost}>Copy verify link</button>
        </div>
        <div className="mt-3 inline-block rounded-[8px] border border-[#f0f0ee] bg-white p-2">
          <QRCodeSVG value={verifyUrl} size={128} title={`QR code for ${verifyUrl}`} />
        </div>
        <p className="mt-1 text-[11px] text-[#787774]">The QR code opens the verify page for this record.</p>
      </div>
      {result && <div className={`mt-3 ${card}`}><Checks res={result} /></div>}
      <div className={`mt-3 ${card}`}>
        <h3 className="text-[13px] font-semibold">Paste to verify</h3>
        <p className="text-[12px] text-[#787774]">Paste a downloaded Passport. Change one digit to see the check fail.</p>
        <textarea
          value={pasted}
          onChange={(e) => setPasted(e.target.value)}
          rows={5}
          className="mt-2 w-full rounded-[8px] border border-[#e5e5e3] bg-white p-2 font-mono text-[11px]"
          aria-label="Passport JSON"
        />
        <button type="button" onClick={checkPasted} disabled={!pasted.trim()} className={`mt-2 ${btn} disabled:opacity-50`}>Verify</button>
        {pasteErr && <p className="mt-2 text-[12px] text-[#b00020]">{pasteErr}</p>}
        {pasteResult && <div className="mt-3"><Checks res={pasteResult} /></div>}
      </div>
    </div>
  );
}
