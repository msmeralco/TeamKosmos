/* Solar Passport booklet for the demo solar owner (same look as the deck's Passport: teal frame, cream page, QR tile and check seal).
   The cover swings open on click; page 1 is the ID page, page 2 holds the vouchers. The nav entry only exists for accounts that have a Passport. */
import { useState, type ReactNode } from "react";
import { AnimatePresence, MotionConfig, m } from "framer-motion";
import { QRCodeSVG } from "qrcode.react";
import { redeemVoucher, type Rewards, type Voucher } from "../lib/api";
import { Icon } from "./icons";

const TEAL = "#2f7f78";
const TEAL_DARK = "#235f5a";
const CREAM = "#e8e1d2";
const TAN = "#c9bfa8";
const INK = "#4a4234";
const CHIP = "#b9cbc6";

const php = (v: number | null) => (v === null ? "n/a" : `₱${Math.round(v).toLocaleString("en-PH")}`);
const day = (iso: string) => new Date(iso).toLocaleDateString("en-PH", { year: "numeric", month: "short", day: "numeric" });

function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-[3px] px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ background: CHIP, color: TEAL_DARK }}>
      {children}
    </span>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="border-b pb-2" style={{ borderColor: TAN }}>
      <p className="text-[9px] font-semibold uppercase tracking-[0.14em]" style={{ color: "#8f8570" }}>
        {label}
      </p>
      <p className="truncate text-[14px] font-medium" style={{ color: INK }}>
        {children}
      </p>
    </div>
  );
}

function Seal({ valid }: { valid: boolean }) {
  return (
    <div
      className="absolute -bottom-3 -right-3 flex h-[104px] w-[104px] items-center justify-center rounded-full"
      style={{ background: valid ? TEAL : "#a33b3b", boxShadow: `0 0 0 5px ${valid ? TEAL_DARK : "#7d2a2a"}, 0 6px 14px rgba(0,0,0,0.18)` }}
      role="img"
      aria-label={valid ? "Signed and verified" : "Verification failed"}
    >
      <span className="flex h-[76px] w-[76px] items-center justify-center rounded-full" style={{ background: valid ? TEAL_DARK : "#7d2a2a" }}>
        <svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ filter: "drop-shadow(0 0 6px rgba(255,255,255,0.8))" }} aria-hidden="true">
          {valid ? <path d="M5 12.5l4.5 4.5L19 7.5" /> : <path d="M6 6l12 12M18 6L6 18" />}
        </svg>
      </span>
    </div>
  );
}

function Ticket({ v, busy, onRedeem }: { v: Voucher; busy: boolean; onRedeem: () => void }) {
  return (
    <li className="relative rounded-[6px] border border-dashed p-3.5" style={{ borderColor: TAN, background: v.redeemed ? "#dfe9e4" : "#f1ecdf" }}>
      <span aria-hidden="true" className="absolute -left-[7px] top-1/2 h-3 w-3 -translate-y-1/2 rounded-full" style={{ background: CREAM }} />
      <span aria-hidden="true" className="absolute -right-[7px] top-1/2 h-3 w-3 -translate-y-1/2 rounded-full" style={{ background: CREAM }} />
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[4px]" style={{ background: CHIP, color: TEAL_DARK }}>
          {Icon.gift}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-semibold leading-snug" style={{ color: INK }}>{v.title}</p>
          <p className="text-[12px] font-semibold" style={{ color: TEAL }}>{v.value} · <span className="font-normal" style={{ color: "#8f8570" }}>{v.partner}</span></p>
          <p className="mt-1 text-[11px] leading-snug" style={{ color: "#8f8570" }}>{v.terms}</p>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between gap-2 border-t border-dashed pt-2.5" style={{ borderColor: TAN }}>
        {v.redeemed && v.code ? (
          <>
            <span className="font-mono text-[13px] font-semibold tracking-[0.18em]" style={{ color: INK }}>{v.code}</span>
            <span className="-rotate-6 rounded-[4px] border-2 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.2em]" style={{ borderColor: TEAL, color: TEAL }}>
              Redeemed
            </span>
          </>
        ) : (
          <>
            <span className="text-[11px]" style={{ color: "#8f8570" }}>Code shows after redeeming</span>
            <button
              type="button"
              onClick={onRedeem}
              disabled={busy}
              className="rounded-[4px] px-3 py-1.5 text-[12px] font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              style={{ background: TEAL }}
            >
              {busy ? "Redeeming…" : "Redeem"}
            </button>
          </>
        )}
      </div>
    </li>
  );
}

function Cover({ holder, opened, onOpen }: { holder: string; opened: boolean; onOpen: () => void }) {
  return (
    <m.button
      type="button"
      onClick={onOpen}
      disabled={opened}
      aria-label="Open Solar Passport"
      initial={false}
      animate={opened ? { rotateY: -112, opacity: 0 } : { rotateY: 0, opacity: 1 }}
      transition={{ rotateY: { duration: 0.9, ease: [0.5, 0, 0.2, 1] }, opacity: { duration: 0.4, delay: opened ? 0.5 : 0 } }}
      whileHover={opened ? undefined : { rotateY: -8 }}
      className="absolute inset-0 z-10 flex flex-col items-center justify-between rounded-[10px] px-6 py-8 text-center focus-visible:outline-offset-4"
      style={{
        transformOrigin: "left center",
        pointerEvents: opened ? "none" : "auto",
        background: TEAL,
        backgroundImage: "radial-gradient(rgba(255,255,255,0.08) 1px, transparent 1px)",
        backgroundSize: "10px 10px",
        boxShadow: `inset 0 0 0 8px ${TEAL}, inset 0 0 0 10px ${CREAM}55`,
      }}
    >
      <span className="h-2 w-full max-w-[260px] rounded-[2px]" style={{ background: CREAM }} />
      <span className="flex flex-col items-center gap-5">
        <span className="flex h-24 w-24 items-center justify-center rounded-full border-2 [&_svg]:h-12 [&_svg]:w-12" style={{ borderColor: CREAM, color: CREAM }}>
          {Icon.sun}
        </span>
        <span className="text-[26px] font-bold leading-none tracking-[0.2em]" style={{ color: CREAM }}>SOLAR</span>
        <span className="-mt-3 text-[26px] font-bold leading-none tracking-[0.2em]" style={{ color: CREAM }}>PASSPORT</span>
        <span className="rounded-[3px] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em]" style={{ background: CHIP, color: TEAL_DARK }}>{holder}</span>
      </span>
      <span className="text-[11px] font-medium uppercase tracking-[0.22em]" style={{ color: `${CREAM}cc` }}>Tap to open</span>
    </m.button>
  );
}

export function RewardsView({ data, holder, onChange }: { data: Rewards; holder: string; onChange: (r: Rewards) => void }) {
  const [opened, setOpened] = useState(false);
  const [page, setPage] = useState<1 | 2>(1);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const p = data.passport;
  if (!p) return null;
  const verifyUrl = `${window.location.origin}${p.verify_path}`;
  const done = data.vouchers.filter((v) => v.redeemed).length;

  const redeem = async (id: string) => {
    setBusyId(id);
    setErr(null);
    try {
      onChange(await redeemVoucher(id));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusyId(null);
    }
  };

  const turn = "rounded-[8px] border border-[#e5e5e3] bg-white px-3.5 py-1.5 text-[12px] font-medium text-[#111111] hover:bg-[#fafaf9] disabled:opacity-40";

  return (
    <MotionConfig reducedMotion="user">
    <div className="flex h-full flex-1 flex-col items-center overflow-y-auto p-6 text-[#111111]">
      {/* The booklet: stacked page edges on the right and bottom */}
      <div
        className="relative w-full max-w-[420px] rounded-[10px] p-2.5"
        style={{ perspective: 1400, background: TEAL, boxShadow: `5px 5px 0 -1px ${TEAL_DARK}, 9px 9px 0 -2px #cfc7b3, 12px 12px 0 -3px #bdb49d` }}
      >
        <Cover holder={holder} opened={opened} onOpen={() => setOpened(true)} />
        {/* header band */}
        <div className="px-1.5 pb-3 pt-1.5" inert={!opened}>
          <div className="mb-3 h-2 rounded-[2px]" style={{ background: CREAM }} />
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-[3px] px-3 py-1.5 text-[15px] font-bold tracking-[0.14em]" style={{ background: CREAM, color: TEAL_DARK }}>
              {page === 1 ? "SOLAR PASSPORT" : "VOUCHERS"}
            </span>
            {page === 1 ? (
              <>
                <Chip>{p.id}</Chip>
                <Chip>{day(p.created_at)}</Chip>
              </>
            ) : (
              <Chip>
                {done} of {data.vouchers.length} stamped
              </Chip>
            )}
          </div>
        </div>

        {/* cream page */}
        <AnimatePresence mode="wait" initial={false}>
        <m.div
          key={page}
          inert={!opened}
          initial={{ rotateY: 75, opacity: 0 }}
          animate={{ rotateY: 0, opacity: 1 }}
          exit={{ rotateY: -75, opacity: 0 }}
          transition={{ duration: 0.32, ease: "easeInOut" }}
          className="relative min-h-[430px] rounded-[4px] px-5 pb-24 pt-5"
          style={{ background: CREAM, transformOrigin: "left center" }}
        >
          {page === 1 ? (
            <>
              <div className="flex flex-col gap-3">
                <Row label="Holder">{holder}</Row>
                <Row label="Installed">
                  {p.installation ? day(p.installation.installed_on) : "n/a"}
                  {p.installation ? ` by ${p.installation.installer}` : ""}
                </Row>
                <Row label="System">
                  {p.panels ? `${p.panels} panels` : p.option}
                  {p.kwp ? ` · ${p.kwp} kWp` : ""}
                  {p.capex_php !== null ? ` · about ${php(p.capex_php)}` : ""}
                </Row>
                <Row label="Record hash">
                  <span className="font-mono tracking-wider">{p.short_hash}</span>
                </Row>
              </div>
              {p.installation?.sample && (
                <p className="mt-3 text-[11px]" style={{ color: "#8f8570" }}>
                  Demo installation with sample data. The record is real and signed by Sol.
                </p>
              )}
              <div className="absolute bottom-5 left-5 flex items-end gap-3">
                <div className="rounded-[2px] p-1.5" style={{ background: "#111111" }}>
                  <QRCodeSVG value={verifyUrl} size={84} fgColor={CREAM} bgColor="#111111" title={`QR code for ${verifyUrl}`} />
                </div>
                <div className="flex flex-col items-start gap-1 pb-0.5">
                  <a href={p.verify_path} target="_blank" rel="noreferrer" className="text-[11px] font-semibold underline" style={{ color: TEAL_DARK }}>
                    Open verify page
                  </a>
                  <button type="button" onClick={() => navigator.clipboard?.writeText(verifyUrl)} className="text-[11px] font-semibold underline" style={{ color: TEAL_DARK }}>
                    Copy link
                  </button>
                </div>
              </div>
              <Seal valid={p.valid} />
            </>
          ) : (
            <>
              <p className="mb-3 text-[11px]" style={{ color: "#8f8570" }}>
                Sample vouchers for the demo. Nothing here is agreed with Meralco or any business, and none has a cash value.
              </p>
              {err && <p className="mb-2 text-[12px] text-[#b00020]">{err}</p>}
              <ul className="flex flex-col gap-3">
                {data.vouchers.map((v) => (
                  <Ticket key={v.id} v={v} busy={busyId === v.id} onRedeem={() => void redeem(v.id)} />
                ))}
              </ul>
            </>
          )}
        </m.div>
        </AnimatePresence>
      </div>

      <div className="mt-8 flex items-center gap-3" style={{ visibility: opened ? "visible" : "hidden" }}>
        <button type="button" onClick={() => setPage(1)} disabled={page === 1} className={turn}>
          ← ID page
        </button>
        <span className="text-[12px] text-[#787774]">Page {page} of 2</span>
        <button type="button" onClick={() => setPage(2)} disabled={page === 2} className={turn}>
          Vouchers →
        </button>
        <button type="button" onClick={() => { setOpened(false); setPage(1); }} className={turn}>
          Close
        </button>
      </div>
    </div>
    </MotionConfig>
  );
}
