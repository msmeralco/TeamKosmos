import { useMemo, useState, type ReactNode } from "react";
import { Icon } from "./icons";
import type { InstallerList, InstallerRow, Listing, PackageList, PackageRow } from "../lib/api";

/* The right-hand panel for lists: DOE-registered installers and ready-made packages.
   It reuses the map panel's slot, so the chat keeps its width and the tables get the room they need. */

const peso = (n: number) => `₱${Math.round(n).toLocaleString("en-PH")}`;

const href = (url: string) => (/^https?:\/\//i.test(url) ? url : `https://${url}`);

/** "https://www.acessolarcorp.com/x" -> "acessolarcorp.com"; social pages get their name. */
function siteLabel(url: string): string {
  const host = href(url).replace(/^https?:\/\/(www\.)?/i, "").split("/")[0].toLowerCase();
  if (host.includes("facebook.com") || host === "fb.com") return "Facebook";
  if (host.includes("linkedin.com")) return "LinkedIn";
  return host;
}

const SWATCHES = [
  ["#fff1e0", "#c2410c"],
  ["#fef3c7", "#a16207"],
  ["#ecfccb", "#4d7c0f"],
  ["#e0f2fe", "#0369a1"],
  ["#f3e8ff", "#7e22ce"],
  ["#ffe4e6", "#be123c"],
] as const;

function swatch(name: string) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return SWATCHES[h % SWATCHES.length];
}

const initials = (name: string) =>
  name
    .replace(/\(.*?\)/g, "")
    .split(/\s+/)
    .filter((w) => /^[A-Za-z0-9]/.test(w))
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("") || "S";

function Header({ icon, title, subtitle, onClose }: { icon: ReactNode; title: string; subtitle: string; onClose: () => void }) {
  return (
    <header className="flex shrink-0 items-start gap-3 border-b border-[#f0f0ee] bg-white px-5 pb-3.5 pt-4">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-[#fff7ed] text-[#ea580c]">{icon}</span>
      <div className="min-w-0 flex-1">
        <h2 className="truncate text-[15px] font-semibold tracking-tight text-[#111111]">{title}</h2>
        <p className="mt-0.5 text-[12px] leading-snug text-[#787774]">{subtitle}</p>
      </div>
      <button
        type="button"
        onClick={onClose}
        aria-label="Close panel"
        title="Close panel"
        className="row-btn press flex h-7 w-7 shrink-0 items-center justify-center rounded-[7px] text-[#787774] transition-colors hover:bg-[#fafaf9] hover:text-[#111111]"
      >
        {Icon.close}
      </button>
    </header>
  );
}

function Notice({ children }: { children: ReactNode }) {
  return (
    <footer className="shrink-0 border-t border-[#f0f0ee] bg-[#fafaf9] px-5 py-3 text-[11px] leading-relaxed text-[#787774]">{children}</footer>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`press rounded-full border px-3 py-1 text-[12px] font-medium transition-colors ${
        active ? "border-[#ea580c] bg-[#fff7ed] text-[#c2410c]" : "border-[#e5e5e4] bg-white text-[#52514e] hover:border-[#ea580c]/50 hover:text-[#111111]"
      }`}
    >
      {children}
    </button>
  );
}

function ContactLink({ href: to, icon, children, external = false, label }: { href: string; icon: ReactNode; children: ReactNode; external?: boolean; label: string }) {
  return (
    <a
      href={to}
      aria-label={label}
      {...(external ? { target: "_blank", rel: "noreferrer" } : {})}
      className="press inline-flex max-w-full items-center gap-1.5 rounded-full border border-[#ecebe8] bg-white px-2.5 py-1 text-[12px] text-[#33322e] transition-colors hover:border-[#ea580c]/60 hover:text-[#c2410c]"
    >
      <span className="shrink-0 text-[#ea580c]">{icon}</span>
      <span className="truncate">{children}</span>
    </a>
  );
}

/* ---------------------------------- Installers ---------------------------------- */

function listBadge(lists: string[]) {
  if (lists.length > 1) return { text: "On both DOE lists", cls: "bg-[#ecfdf3] text-[#15803d]", dot: "bg-[#22c55e]" };
  return { text: `${lists[0]?.replace(/,? 2026/, " 2026")} list only`, cls: "bg-[#f5f4f1] text-[#6b6b66]", dot: "bg-[#a3a3a3]" };
}

function InstallerCard({ x }: { x: InstallerRow }) {
  const [bg, fg] = swatch(x.name);
  const badge = listBadge(x.lists);
  const phone = x.phones[0] ?? x.phone;
  const email = x.emails[0] ?? x.email;
  return (
    <li className="rounded-[14px] border border-[#ecebe8] bg-white p-3.5 shadow-[0_1px_2px_rgba(0,0,0,0.03)] transition-shadow hover:shadow-[0_4px_14px_rgba(0,0,0,0.06)]">
      <div className="flex items-start gap-3">
        <span
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[11px] text-[13px] font-semibold"
          style={{ background: bg, color: fg }}
          aria-hidden="true"
        >
          {initials(x.name)}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-[14px] font-semibold leading-snug text-[#111111]">{x.name}</h3>
          <p className="mt-0.5 flex items-start gap-1 text-[12px] leading-snug text-[#787774]">
            <span className="mt-[1px] shrink-0">{Icon.pin}</span>
            <span>{x.area || x.address}</span>
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${badge.cls}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} />
              {badge.text}
            </span>
            {x.esco && (
              <span className="rounded-full bg-[#eff6ff] px-2 py-0.5 text-[11px] font-medium text-[#1d4ed8]" title="Energy service company that also installs solar">
                ESCO
              </span>
            )}
          </div>
        </div>
      </div>
      {(phone || email || x.website) && (
        <div className="mt-3 flex flex-wrap gap-1.5 border-t border-[#f3f2ef] pt-3">
          {phone && (
            <ContactLink href={`tel:${phone.replace(/[^\d+]/g, "")}`} icon={Icon.phone} label={`Call ${x.name}`}>
              {phone}
            </ContactLink>
          )}
          {email && (
            <ContactLink href={`mailto:${email}`} icon={Icon.mail} label={`Email ${x.name}`}>
              {email}
            </ContactLink>
          )}
          {x.website && (
            <ContactLink href={href(x.website)} icon={Icon.globe} external label={`Open ${x.name}'s website`}>
              {siteLabel(x.website)}
            </ContactLink>
          )}
        </div>
      )}
    </li>
  );
}

function InstallersPanel({ data, onClose }: { data: InstallerList; onClose: () => void }) {
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? data.rows.filter((x) => `${x.name} ${x.address}`.toLowerCase().includes(t)) : data.rows;
  }, [q, data.rows]);
  const nearNote = data.near && data.nearby > 0 ? ` · ${data.nearby} with an address in ${data.near} first` : "";
  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-white">
      <Header
        icon={Icon.pin}
        title="Registered solar installers"
        subtitle={`${data.region_name} · ${data.total} firms from the DOE registry${nearNote}`}
        onClose={onClose}
      />
      <div className="shrink-0 px-5 pb-2 pt-3">
        <label className="flex items-center gap-2 rounded-[10px] border border-[#e5e5e4] bg-white px-3 py-2 text-[#787774] focus-within:border-[#ea580c]">
          {Icon.search}
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name or place"
            aria-label="Search installers"
            className="min-w-0 flex-1 bg-transparent text-[13px] text-[#111111] outline-none placeholder:text-[#a3a3a3]"
          />
          {q && (
            <button type="button" onClick={() => setQ("")} aria-label="Clear search" className="text-[#a3a3a3] hover:text-[#111111]">
              {Icon.close}
            </button>
          )}
        </label>
        <p className="mt-2 text-[11px] text-[#787774]" aria-live="polite">
          {rows.length === data.rows.length ? `${rows.length} installers` : `${rows.length} of ${data.rows.length} match`}
        </p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-4">
        {rows.length === 0 ? (
          <p className="py-10 text-center text-[13px] text-[#787774]">No installer matches “{q}”.</p>
        ) : (
          <ul className="grid gap-2.5">
            {rows.map((x) => (
              <InstallerCard key={x.name} x={x} />
            ))}
          </ul>
        )}
      </div>
      <Notice>
        {data.disclaimer} Sol has not checked their prices, quality or service. Confirm each firm's current registration and get at least two written quotes. ESCO means energy
        service company. Source:{" "}
        <a href={data.source_url} target="_blank" rel="noreferrer" className="font-medium text-[#ea580c] underline underline-offset-2">
          DOE Official Solar PV Installer Registry
        </a>{" "}
        ({data.lists.join(" and ")} lists).
      </Notice>
    </div>
  );
}

/* ---------------------------------- Packages ---------------------------------- */

type Kind = "all" | PackageRow["type"];
type Sort = "match" | "price" | "size";
const KIND_LABEL: Record<PackageRow["type"], string> = { hybrid: "Hybrid", "grid-tied": "Grid-tied", "off-grid": "Off-grid" };
const KIND_CLS: Record<PackageRow["type"], string> = {
  hybrid: "bg-[#fff7ed] text-[#c2410c]",
  "grid-tied": "bg-[#eff6ff] text-[#1d4ed8]",
  "off-grid": "bg-[#f3e8ff] text-[#7e22ce]",
};

function PackageCard({ p, best, budgeted, onAsk }: { p: PackageRow; best: boolean; budgeted: boolean; onAsk?: (text: string) => void }) {
  const [broken, setBroken] = useState(false);
  return (
    <li className="flex flex-col overflow-hidden rounded-[14px] border border-[#ecebe8] bg-white shadow-[0_1px_2px_rgba(0,0,0,0.03)] transition-shadow hover:shadow-[0_6px_18px_rgba(0,0,0,0.07)]">
      <div className="relative aspect-[44/30] w-full overflow-hidden bg-gradient-to-br from-[#fff1e0] to-[#e8f1ff]">
        {p.photo && !broken ? (
          <img
            src={p.photo}
            alt={`${p.installer}: ${p.name}`}
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={() => setBroken(true)}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-[#ea580c]/60">{Icon.panel}</div>
        )}
        <div className="absolute left-2.5 top-2.5 flex flex-wrap gap-1.5">
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold shadow-sm ${KIND_CLS[p.type]}`}>{KIND_LABEL[p.type]}</span>
          {p.synthetic && <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-[#b45309] shadow-sm">Sample</span>}
          {best && <span className="rounded-full bg-[#111111] px-2 py-0.5 text-[11px] font-semibold text-white shadow-sm">Best match</span>}
          {budgeted && p.within_budget === true && <span className="rounded-full bg-[#ecfdf3] px-2 py-0.5 text-[11px] font-semibold text-[#15803d] shadow-sm">Within budget</span>}
          {budgeted && p.within_budget === false && <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-[#6b6b66] shadow-sm">Over budget</span>}
        </div>
      </div>
      <div className="flex flex-1 flex-col p-3.5">
        <p className="truncate text-[11px] font-medium uppercase tracking-wide text-[#787774]">{p.synthetic ? "Made-up example" : p.installer}</p>
        <h3 className="mt-0.5 text-[14px] font-semibold leading-snug text-[#111111]">{p.name}</h3>
        <div className="mt-2 flex items-baseline justify-between gap-2">
          <span className="text-[20px] font-semibold tracking-tight text-[#111111]">{peso(p.price_php)}</span>
          <span className="rounded-full bg-[#f5f4f1] px-2 py-0.5 text-[12px] font-semibold text-[#33322e]">{p.kwp.toLocaleString("en-PH", { maximumFractionDigits: 2 })} kWp</span>
        </div>
        <p className="mt-0.5 text-[11px] text-[#787774]">{p.price_note}</p>
        <ul className="mt-3 space-y-1.5 text-[12px] text-[#33322e]">
          <li className="flex items-start gap-2">
            <span className="mt-[1px] shrink-0 text-[#ea580c]">{Icon.panel}</span>
            <span>{p.panels}</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-[1px] shrink-0 text-[#ea580c]">{Icon.bolt}</span>
            <span>{p.inverter}</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-[1px] shrink-0 text-[#ea580c]">{Icon.battery}</span>
            <span>{p.battery_kwh ? `${p.battery_kwh.toLocaleString("en-PH", { maximumFractionDigits: 2 })} kWh battery` : "No battery"}</span>
          </li>
        </ul>
        <div className="mt-auto flex gap-2 pt-3.5">
          {onAsk && (
            <button
              type="button"
              onClick={() => onAsk(p.synthetic ? `Tell me more about the ${p.name} package` : `Tell me more about the ${p.name} from ${p.installer}`)}
              className="press flex flex-1 items-center justify-center gap-1.5 rounded-[10px] bg-[#111111] px-3 py-2 text-[12px] font-medium text-white transition-colors hover:bg-[#ea580c]"
            >
              {p.synthetic ? "Ask Sol about this" : "Details & contacts"}
            </button>
          )}
          {p.link ? (
            <a
              href={p.link}
              target="_blank"
              rel="noreferrer"
              aria-label={`Open ${p.installer}'s website`}
              title={`Open ${p.installer}'s website`}
              className="press flex items-center justify-center gap-1.5 rounded-[10px] border border-[#e5e5e4] bg-white px-3 py-2 text-[12px] font-medium text-[#111111] transition-colors hover:border-[#ea580c] hover:text-[#c2410c]"
            >
              {onAsk ? "Website" : `View on ${p.installer}`}
              {Icon.external}
            </a>
          ) : (
            !onAsk && <p className="flex-1 rounded-[10px] bg-[#fafaf9] px-3 py-2 text-center text-[11px] text-[#787774]">Not an offer from anyone</p>
          )}
        </div>
      </div>
    </li>
  );
}

function PackagesPanel({ data, onClose, onAsk }: { data: PackageList; onClose: () => void; onAsk?: (text: string) => void }) {
  const [kind, setKind] = useState<Kind>("all");
  const [sort, setSort] = useState<Sort>("match");
  const [showOver, setShowOver] = useState(false);
  const budgeted = data.budget_max != null;
  const over = budgeted ? data.rows.filter((r) => r.within_budget === false).length : 0;
  const nothingFits = budgeted && over === data.rows.length;
  const visible = useMemo(
    () => data.rows.filter((r) => !budgeted || r.within_budget !== false || showOver || nothingFits),
    [data.rows, budgeted, showOver, nothingFits],
  );
  const kinds = useMemo(() => (["grid-tied", "hybrid", "off-grid"] as const).filter((k) => visible.some((r) => r.type === k)), [visible]);
  const shown = useMemo(() => {
    const rows = visible.filter((r) => kind === "all" || r.type === kind);
    if (sort === "price") return [...rows].sort((a, b) => a.price_php - b.price_php);
    if (sort === "size") return [...rows].sort((a, b) => a.kwp - b.kwp);
    return rows; // the server already ranks by closeness to the recommended system
  }, [visible, kind, sort]);
  const real = shown.filter((p) => !p.synthetic);
  const samples = shown.filter((p) => p.synthetic);
  const best = new Set(sort === "match" && data.wanted_kwp ? real.filter((p) => p.within_budget !== false).slice(0, 3).map((p) => p.id) : []);
  const kwpText = data.wanted_kwp ? data.wanted_kwp.toLocaleString("en-PH", { maximumFractionDigits: 2 }) : "";
  const want = !data.wanted_kwp ? "All sizes" : data.basis === "usage" ? `Around ${kwpText} kWp, a rough size for your usage` : `Closest to your ${kwpText} kWp design`;
  const budgetText = budgeted ? ` · up to ${peso(data.budget_max as number)}` : "";
  const grid = "grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(230px,1fr))]";
  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-white">
      <Header
        icon={Icon.panel}
        title="Ready-made packages"
        subtitle={`${want}${budgetText} · ${data.in_your_area ? "installers that serve your area" : "installers in other areas"}`}
        onClose={onClose}
      />
      <div className="flex shrink-0 flex-wrap items-center gap-2 px-5 pb-2 pt-3">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by type">
          <Chip active={kind === "all"} onClick={() => setKind("all")}>
            All
          </Chip>
          {kinds.map((k) => (
            <Chip key={k} active={kind === k} onClick={() => setKind(k)}>
              {KIND_LABEL[k]}
            </Chip>
          ))}
          {over > 0 && !nothingFits && (
            <Chip active={showOver} onClick={() => setShowOver((v) => !v)}>
              {showOver ? "Hide" : "Show"} over budget ({over})
            </Chip>
          )}
        </div>
        <label className="ml-auto flex items-center gap-1.5 text-[12px] text-[#787774]">
          Sort
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as Sort)}
            className="rounded-[8px] border border-[#e5e5e4] bg-white px-2 py-1 text-[12px] text-[#111111] outline-none focus:border-[#ea580c]"
          >
            <option value="match">Best match</option>
            <option value="price">Price, low to high</option>
            <option value="size">Size, small to large</option>
          </select>
        </label>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-4">
        {nothingFits && (
          <p className="mb-3 rounded-[10px] bg-[#fff7ed] px-3 py-2 text-[12px] leading-snug text-[#9a3412]">
            Nothing I have is under {peso(data.budget_max as number)}, so these are the closest, all over budget.
          </p>
        )}
        {real.length > 0 && (
          <>
            <h3 className="mb-2 mt-1 text-[12px] font-semibold uppercase tracking-wide text-[#787774]">From installers · {real.length}</h3>
            <ul className={grid}>
              {real.map((p) => (
                <PackageCard key={p.id} p={p} best={best.has(p.id)} budgeted={budgeted} onAsk={onAsk} />
              ))}
            </ul>
          </>
        )}
        {samples.length > 0 && (
          <>
            <h3 className="mb-1 mt-5 text-[12px] font-semibold uppercase tracking-wide text-[#b45309]">Made-up samples · {samples.length}</h3>
            <p className="mb-2 text-[12px] leading-snug text-[#787774]">
              Invented to fill sizes and types no installer publishes. Their prices only follow the range of the real ones.
            </p>
            <ul className={grid}>
              {samples.map((p) => (
                <PackageCard key={p.id} p={p} best={false} budgeted={budgeted} onAsk={onAsk} />
              ))}
            </ul>
          </>
        )}
        {shown.length === 0 && <p className="py-10 text-center text-[13px] text-[#787774]">No package of this type.</p>}
      </div>
      <Notice>
        Prices are what each installer published on its own website on {data.checked_on}, not quotes. Sol has not vetted these installers. Ask for a written quote based on your own
        installation site and bill. A photo shows the installer's work and a drawing is only an illustration, so neither is this exact package.
      </Notice>
    </div>
  );
}

export function ListingPanel({ listing, onClose, onAsk }: { listing: Listing; onClose: () => void; onAsk?: (text: string) => void }) {
  return listing.type === "installers" ? <InstallersPanel data={listing.data} onClose={onClose} /> : <PackagesPanel data={listing.data} onClose={onClose} onAsk={onAsk} />;
}
