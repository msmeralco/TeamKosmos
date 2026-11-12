import { useMemo, useState, type ReactNode } from "react";
import { AnimatePresence, LazyMotion, MotionConfig, m } from "framer-motion";
import { Icon } from "./icons";
import {
  EASE_ENTER,
  Fact,
  GROUP_CLS,
  PanelHeader,
  Photo,
  PRIMARY_BTN_CLS,
  ROW_BTN_CLS,
  rowVariants,
  SECONDARY_BTN_CLS,
  SECTION_LABEL_CLS,
  Segmented,
  Sheet,
  SortMenu,
} from "./ListingParts";
import { packagePhoto, pricePerKwp } from "../lib/packagePhoto";
import type { InstallerList, InstallerRow, Listing, PackageList, PackageRow } from "../lib/api";

/* The right-hand panel for lists: DOE-registered installers and ready-made packages.
   It reuses the map panel's slot, so the chat keeps its width and the lists get the room they need.
   Each list is a grouped list; tapping a row opens a bottom sheet with the details. */

const peso = (n: number) => `₱${Math.round(n).toLocaleString("en-PH")}`;
const num = (n: number) => n.toLocaleString("en-PH", { maximumFractionDigits: 2 });

const href = (url: string) => (/^https?:\/\//i.test(url) ? url : `https://${url}`);

/** "https://www.acessolarcorp.com/x" -> "acessolarcorp.com"; social pages get their name. */
function siteLabel(url: string): string {
  const host = href(url).replace(/^https?:\/\/(www\.)?/i, "").split("/")[0].toLowerCase();
  if (host.includes("facebook.com") || host === "fb.com") return "Facebook";
  if (host.includes("linkedin.com")) return "LinkedIn";
  return host;
}

const initials = (name: string) =>
  name
    .replace(/\(.*?\)/g, "")
    .split(/\s+/)
    .filter((w) => /^[A-Za-z0-9]/.test(w))
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("") || "S";

const Chevron = <span className="shrink-0 text-[#c4c4c0]">{Icon.chevronRight}</span>;

/* ---------------------------------- Installers ---------------------------------- */

function PrimaryContact({ x }: { x: InstallerRow }) {
  const c = x.phones[0] || x.phone || x.emails[0] || x.email || x.website;
  return <span className="min-w-0 truncate text-[12px] font-medium text-[#346538]">{c || "No contact listed"}</span>;
}

function Monogram({ name, size }: { name: string; size: "sm" | "lg" }) {
  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center bg-[#f1f1ef] font-semibold text-[#52514e] ${
        size === "lg" ? "h-12 w-12 rounded-[12px] text-[16px]" : "h-10 w-10 rounded-[10px] text-[13px]"
      }`}
    >
      {initials(name)}
    </span>
  );
}

function ContactRow({ to, icon, label, children, external = false }: { to: string; icon: ReactNode; label: string; children: ReactNode; external?: boolean }) {
  return (
    <li>
      <a
        href={to}
        aria-label={label}
        {...(external ? { target: "_blank", rel: "noreferrer" } : {})}
        className="flex items-center gap-3 px-4 py-3 text-[13px] transition-colors hover:bg-[#fafaf9] active:bg-[#f4f4f2] focus-visible:outline-offset-[-2px]"
      >
        <span className="shrink-0 text-[#787774]">{icon}</span>
        <span className="min-w-0 flex-1 truncate text-[#111111]">{children}</span>
        {Chevron}
      </a>
    </li>
  );
}

function InstallerDetail({ x, sourceUrl }: { x: InstallerRow; sourceUrl: string }) {
  const phones = x.phones.length ? x.phones : x.phone ? [x.phone] : [];
  const emails = x.emails.length ? x.emails : x.email ? [x.email] : [];
  const none = phones.length === 0 && emails.length === 0 && !x.website;
  return (
    <>
      <div className="flex items-center gap-3 pr-10">
        <Monogram name={x.name} size="lg" />
        <div className="min-w-0">
          <h3 className="text-[20px] font-semibold leading-tight tracking-[-0.01em] text-[#111111]">{x.name}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            {x.esco && (
              <span className="text-[11px] text-[#787774]" title="Energy service company that also installs solar">
                ESCO
              </span>
            )}
          </div>
        </div>
      </div>
      {(x.area || x.address) && (
        <p className="mt-4 flex items-start gap-2 text-[13px] leading-snug text-[#52514e]">
          <span className="mt-[1px] shrink-0 text-[#787774]">{Icon.pin}</span>
          <span>{x.address || x.area}</span>
        </p>
      )}
      {none ? (
        <p className="mt-4 text-[13px] text-[#787774]">The registry lists no phone, email or website for this firm.</p>
      ) : (
        <ul className={`${GROUP_CLS} mt-4`}>
          {phones.map((p) => (
            <ContactRow key={p} to={`tel:${p.replace(/[^\d+]/g, "")}`} icon={Icon.phone} label={`Call ${x.name} on ${p}`}>
              {p}
            </ContactRow>
          ))}
          {emails.map((e) => (
            <ContactRow key={e} to={`mailto:${e}`} icon={Icon.mail} label={`Email ${x.name} at ${e}`}>
              {e}
            </ContactRow>
          ))}
          {x.website && (
            <ContactRow to={href(x.website)} icon={Icon.globe} external label={`Open ${x.name}'s website`}>
              {siteLabel(x.website)}
            </ContactRow>
          )}
        </ul>
      )}
      <p className="mt-4 text-[11px] leading-relaxed text-[#787774]">
        Sol has not checked this firm's prices, quality or service. Confirm its current registration and get at least two written quotes.{" "}
        <a href={sourceUrl} target="_blank" rel="noreferrer" className="font-medium text-[#c2410c] underline underline-offset-2">
          DOE registry
        </a>
      </p>
    </>
  );
}

function InstallersPanel({ data, onClose }: { data: InstallerList; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<InstallerRow | null>(null);
  const rows = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? data.rows.filter((x) => `${x.name} ${x.address}`.toLowerCase().includes(t)) : data.rows;
  }, [q, data.rows]);
  const nearNote = data.near && data.nearby > 0 ? ` · ${data.nearby} with an address in ${data.near} first` : "";
  return (
    <div className="relative flex h-full min-h-0 w-full flex-col overflow-hidden bg-[#f7f6f3]">
      <PanelHeader
        title="Registered installers"
        subtitle={`${data.region_name} · ${data.total} firms from the DOE registry${nearNote}`}
        onClose={onClose}
        info={
          <>
            <p>{data.disclaimer}</p>
            <p className="mt-2">
              Sol has not checked their prices, quality or service. Confirm each firm's current registration and get at least two written quotes. ESCO means energy service company.
            </p>
            <p className="mt-2">
              Source:{" "}
              <a href={data.source_url} target="_blank" rel="noreferrer" className="font-medium text-[#c2410c] underline underline-offset-2">
                DOE Official Solar PV Installer Registry
              </a>{" "}
              ({data.lists.join(" and ")} lists).
            </p>
          </>
        }
      />
      <div className="shrink-0 px-5 pb-2">
        <label className="flex h-9 items-center gap-2 rounded-[10px] bg-black/[0.05] px-3 text-[#787774] transition-colors focus-within:bg-white focus-within:ring-1 focus-within:ring-[#ea580c]/50">
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
        <p className="mt-2 px-1 text-[11px] text-[#787774]" aria-live="polite">
          {rows.length === data.rows.length ? `${rows.length} installers` : `${rows.length} of ${data.rows.length} match`}
        </p>
      </div>
      <m.div layoutScroll className="min-h-0 flex-1 overflow-y-auto px-5 pb-6">
        {rows.length === 0 ? (
          <p className="py-10 text-center text-[13px] text-[#787774]">No installer matches “{q}”.</p>
        ) : (
          <ul className={GROUP_CLS}>
            {rows.map((x, i) => (
              <m.li key={x.name} variants={rowVariants} custom={i} initial={i < 8 ? "hidden" : false} animate="show">
                <button type="button" onClick={() => setSelected(x)} className={ROW_BTN_CLS}>
                  <Monogram name={x.name} size="sm" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-medium text-[#111111]">{x.name}</span>
                    <span className="mt-0.5 block truncate text-[12px] text-[#787774]">{x.area || x.address}</span>
                    <span className="mt-1 flex items-center gap-3">
                      <PrimaryContact x={x} />
                      {x.esco && <span className="text-[11px] text-[#787774]">ESCO</span>}
                    </span>
                  </span>
                  {Chevron}
                </button>
              </m.li>
            ))}
          </ul>
        )}
      </m.div>
      <Sheet open={selected !== null} onClose={() => setSelected(null)} label={selected ? `${selected.name}, installer details` : "Installer details"}>
        {selected && <InstallerDetail x={selected} sourceUrl={data.source_url} />}
      </Sheet>
    </div>
  );
}

/* ---------------------------------- Packages ---------------------------------- */

type Kind = "all" | PackageRow["type"];
type Sort = "match" | "price" | "size";
const KIND_LABEL: Record<PackageRow["type"], string> = { hybrid: "Hybrid", "grid-tied": "Grid-tied", "off-grid": "Off-grid" };
const SORTS: { value: Sort; label: string }[] = [
  { value: "match", label: "Best match" },
  { value: "price", label: "Price, low to high" },
  { value: "size", label: "Size, small to large" },
];

function Status({ p, best, budgeted }: { p: PackageRow; best: boolean; budgeted: boolean }) {
  if (best) {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#c2410c]">
        <span className="h-1.5 w-1.5 rounded-full bg-[#ea580c]" />
        Best match
      </span>
    );
  }
  if (budgeted && p.within_budget === false) return <span className="text-[11px] text-[#a3a3a3]">Over budget</span>;
  return null;
}

function PackageRowButton({ p, best, budgeted, onOpen }: { p: PackageRow; best: boolean; budgeted: boolean; onOpen: (p: PackageRow) => void }) {
  const photo = packagePhoto(p);
  const over = budgeted && p.within_budget === false;
  const meta = [`${num(p.kwp)} kWp`, KIND_LABEL[p.type], p.battery_kwh ? `${num(p.battery_kwh)} kWh` : null].filter(Boolean).join(" · ");
  return (
    <button type="button" onClick={() => onOpen(p)} className={ROW_BTN_CLS} aria-label={`${p.name}, ${p.synthetic ? "made-up example" : p.installer}, ${peso(p.price_php)}. Open details`}>
      <Photo src={photo?.src} alt="" className="h-[60px] w-[72px] rounded-[8px]" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12px] text-[#787774]">{p.synthetic ? "Made-up example" : p.installer}</span>
        <span className="block truncate text-[15px] font-medium leading-snug text-[#111111]">{p.name}</span>
        <span className="block truncate text-[12px] text-[#787774]">{meta}</span>
        <Status p={p} best={best} budgeted={budgeted} />
      </span>
      <span className="shrink-0 text-right">
        <span className={`block text-[16px] font-semibold tabular-nums tracking-tight ${over ? "text-[#a3a3a3]" : p.synthetic ? "text-[#787774]" : "text-[#111111]"}`}>{peso(p.price_php)}</span>
        <span className="block text-[11px] tabular-nums text-[#787774]">{peso(pricePerKwp(p))} / kWp</span>
      </span>
      {Chevron}
    </button>
  );
}

function PackageDetail({ p, best, budgeted }: { p: PackageRow; best: boolean; budgeted: boolean }) {
  const photo = packagePhoto(p);
  const over = budgeted && p.within_budget === false;
  return (
    <>
      <Photo src={photo?.src} alt={`${p.synthetic ? "Example" : p.installer}: ${p.name}`} className="aspect-[16/10] w-full rounded-[14px]" />
      {photo?.kind === "stock" && <p className="mt-2 text-[11px] leading-snug text-[#787774]">Stock photo of this kind of system, not this installer's work.</p>}
      <p className="mt-4 text-[12px] text-[#787774]">{p.synthetic ? "Made-up example" : p.installer}</p>
      <h3 className="mt-0.5 text-[20px] font-semibold leading-tight tracking-[-0.01em] text-[#111111]">{p.name}</h3>
      <div className="mt-2 flex flex-wrap items-baseline gap-x-2">
        <span className={`text-[28px] font-semibold tabular-nums tracking-tight ${over ? "text-[#a3a3a3]" : "text-[#111111]"}`}>{peso(p.price_php)}</span>
        <span className="text-[13px] tabular-nums text-[#787774]">{peso(pricePerKwp(p))} / kWp</span>
      </div>
      <p className="mt-0.5 text-[12px] text-[#787774]">{p.price_note}</p>
      <div className="mt-1.5">
        <Status p={p} best={best} budgeted={budgeted} />
      </div>
      {p.synthetic && (
        <p className="mt-3 rounded-[10px] bg-[#fbf3db] px-3 py-2 text-[12px] leading-snug text-[#956400]">
          Invented to fill a size or type no installer publishes. It is not an offer from anyone.
        </p>
      )}
      <dl className={`${GROUP_CLS} mt-4`}>
        <Fact label="Size">{num(p.kwp)} kWp</Fact>
        <Fact label="Type">{KIND_LABEL[p.type]}</Fact>
        <Fact label="Panels">{p.panels}</Fact>
        <Fact label="Inverter">{p.inverter}</Fact>
        <Fact label="Battery">{p.battery_kwh ? `${num(p.battery_kwh)} kWh` : "No battery"}</Fact>
        {!p.synthetic && p.area && <Fact label="Serves">{p.area}</Fact>}
      </dl>
    </>
  );
}

function PackageActions({ p, onAsk, onDone }: { p: PackageRow; onAsk?: (text: string) => void; onDone: () => void }) {
  const ask = () => {
    onAsk?.(p.synthetic ? `Tell me more about the ${p.name} package` : `Tell me more about the ${p.name} from ${p.installer}`);
    onDone();
  };
  return (
    <>
      {onAsk && (
        <button type="button" onClick={ask} className={PRIMARY_BTN_CLS}>
          {p.synthetic ? "Ask Sol about this" : "Ask Sol for details and contacts"}
        </button>
      )}
      {p.link && (
        <a href={p.link} target="_blank" rel="noreferrer" aria-label={`Open ${p.installer}'s website`} className={SECONDARY_BTN_CLS}>
          {onAsk ? "Website" : `View on ${p.installer}`}
          {Icon.external}
        </a>
      )}
    </>
  );
}

function PackagesPanel({ data, onClose, onAsk }: { data: PackageList; onClose: () => void; onAsk?: (text: string) => void }) {
  const [kind, setKind] = useState<Kind>("all");
  const [sort, setSort] = useState<Sort>("match");
  const [showOver, setShowOver] = useState(false);
  const [samplesOpen, setSamplesOpen] = useState(false);
  const [selected, setSelected] = useState<PackageRow | null>(null);
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
  const kwpText = data.wanted_kwp ? num(data.wanted_kwp) : "";
  const want = !data.wanted_kwp ? "All sizes" : data.basis === "usage" ? `Around ${kwpText} kWp, a rough size for your usage` : `Closest to your ${kwpText} kWp design`;
  const budgetText = budgeted ? ` · up to ${peso(data.budget_max as number)}` : "";
  const samplesVisible = samplesOpen || real.length === 0;
  const kindOptions = [{ value: "all" as Kind, label: "All" }, ...kinds.map((k) => ({ value: k as Kind, label: KIND_LABEL[k] }))];
  // A kind that has just been hidden (say, by hiding over-budget rows) falls back to All.
  const activeKind: Kind = kind === "all" || kinds.includes(kind) ? kind : "all";

  return (
    <div className="relative flex h-full min-h-0 w-full flex-col overflow-hidden bg-[#f7f6f3]">
      <PanelHeader
        title="Ready-made packages"
        subtitle={`${want}${budgetText} · ${data.in_your_area ? "installers that serve your area" : "installers in other areas"}`}
        onClose={onClose}
        info={
          <>
            <p>
              Prices are what each installer published on its own website on {data.checked_on}, not quotes. Sol has not vetted these installers. Ask for a written quote based on
              your own installation site and bill.
            </p>
            <p className="mt-2">
              A photo from an installer's site shows their work. Where a package has none, a stock photo of the same kind of system is shown, and it is not this exact package.
            </p>
          </>
        }
      />
      <div className="flex shrink-0 flex-wrap items-center gap-2 px-5 pb-3">
        <Segmented label="Filter by type" value={activeKind} options={kindOptions} onChange={setKind} />
        <SortMenu value={sort} options={SORTS} onChange={setSort} />
      </div>
      <m.div layoutScroll className="min-h-0 flex-1 overflow-y-auto px-5 pb-6">
        {nothingFits && (
          <p className="mb-3 rounded-[10px] bg-[#fbf3db] px-3 py-2 text-[12px] leading-snug text-[#956400]">
            Nothing I have is under {peso(data.budget_max as number)}, so these are the closest, all over budget.
          </p>
        )}
        {real.length > 0 && (
          <section>
            <h3 className={`${SECTION_LABEL_CLS} mb-2 px-1`}>From installers · {real.length}</h3>
            <ul className={GROUP_CLS}>
              <AnimatePresence initial mode="popLayout">
                {real.map((p, i) => (
                  <m.li key={p.id} layout="position" variants={rowVariants} custom={i} initial="hidden" animate="show" exit="exit">
                    <PackageRowButton p={p} best={best.has(p.id)} budgeted={budgeted} onOpen={setSelected} />
                  </m.li>
                ))}
              </AnimatePresence>
            </ul>
            {over > 0 && !nothingFits && (
              <button
                type="button"
                onClick={() => setShowOver((v) => !v)}
                aria-pressed={showOver}
                className="mt-3 px-1 text-[12px] font-medium text-[#787774] underline-offset-2 transition-colors hover:text-[#111111] hover:underline"
              >
                {showOver ? `Hide ${over} over budget` : `Show ${over} over budget`}
              </button>
            )}
          </section>
        )}
        {real.length === 0 && over > 0 && !nothingFits && (
          <button
            type="button"
            onClick={() => setShowOver((v) => !v)}
            aria-pressed={showOver}
            className="mb-3 px-1 text-[12px] font-medium text-[#787774] underline-offset-2 transition-colors hover:text-[#111111] hover:underline"
          >
            {showOver ? `Hide ${over} over budget` : `Show ${over} over budget`}
          </button>
        )}
        {samples.length > 0 && (
          <section className={real.length > 0 ? "mt-6" : ""}>
            {real.length > 0 ? (
              <button
                type="button"
                onClick={() => setSamplesOpen((v) => !v)}
                aria-expanded={samplesVisible}
                className="flex w-full items-center justify-between rounded-[8px] px-1 py-1 text-left"
              >
                <span className={SECTION_LABEL_CLS}>Examples, not real offers · {samples.length}</span>
                <span className={`text-[#a3a3a3] transition-transform duration-200 ${samplesVisible ? "rotate-180" : ""}`}>{Icon.chevronDown}</span>
              </button>
            ) : (
              <h3 className={`${SECTION_LABEL_CLS} px-1`}>Examples, not real offers · {samples.length}</h3>
            )}
            <AnimatePresence initial={false}>
              {samplesVisible && (
                <m.div
                  key="samples"
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0, transition: { duration: 0.28, ease: EASE_ENTER } }}
                  exit={{ opacity: 0, transition: { duration: 0.12 } }}
                >
                  <p className="mb-2 mt-1 px-1 text-[12px] leading-snug text-[#787774]">
                    Invented to fill sizes and types no installer publishes. Their prices only follow the range of the real ones.
                  </p>
                  <ul className={GROUP_CLS}>
                    {samples.map((p) => (
                      <li key={p.id}>
                        <PackageRowButton p={p} best={false} budgeted={budgeted} onOpen={setSelected} />
                      </li>
                    ))}
                  </ul>
                </m.div>
              )}
            </AnimatePresence>
          </section>
        )}
        {shown.length === 0 && <p className="py-10 text-center text-[13px] text-[#787774]">No package of this type.</p>}
      </m.div>
      <Sheet
        open={selected !== null}
        onClose={() => setSelected(null)}
        label={selected ? `${selected.name}, ${selected.synthetic ? "made-up example" : selected.installer}` : "Package details"}
        footer={selected && (onAsk || selected.link) ? <PackageActions p={selected} onAsk={onAsk} onDone={() => setSelected(null)} /> : undefined}
      >
        {selected && <PackageDetail p={selected} best={best.has(selected.id)} budgeted={budgeted} />}
      </Sheet>
    </div>
  );
}

/* Layout animation and drag need the larger Framer Motion feature set, so it loads when a list opens. */
const loadMotionMax = () => import("../lib/motionMax").then((r) => r.default);

export function ListingPanel({ listing, onClose, onAsk }: { listing: Listing; onClose: () => void; onAsk?: (text: string) => void }) {
  return (
    <LazyMotion features={loadMotionMax} strict>
      <MotionConfig reducedMotion="user">
        {listing.type === "installers" ? <InstallersPanel data={listing.data} onClose={onClose} /> : <PackagesPanel data={listing.data} onClose={onClose} onAsk={onAsk} />}
      </MotionConfig>
    </LazyMotion>
  );
}
