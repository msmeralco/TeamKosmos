import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ChangeEvent,
  type ClipboardEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { AnimatePresence, domAnimation, LazyMotion, m } from "framer-motion";
import { Icon } from "./components/icons";
import {
  btn,
  ConfirmDialog,
  Group,
  Logo,
  MenuItem,
  Popover,
  Separator,
  Spinner,
  ThinkingSteps,
  useReducedMotion,
  type AgentStep,
  type Suggestion,
} from "./components/ui";

/* ------------------------------------------------------------------ */
/* Types & helpers                                                     */
/* ------------------------------------------------------------------ */

type View = "chat" | "overview" | "saved";
type PersonaId = "reyes" | "maria" | "wfh";

type Persona = {
  id: PersonaId;
  initials: string;
  name: string;
  first: string;
  subtitle: string;
  location: string;
};

const PERSONAS: Record<PersonaId, Persona> = {
  reyes: {
    id: "reyes",
    initials: "RF",
    name: "Reyes Family",
    first: "Reyes Family",
    subtitle: "450 kWh/mo · Balanced",
    location: "Quezon City",
  },
  maria: {
    id: "maria",
    initials: "AM",
    name: "Ate Maria",
    first: "Maria",
    subtitle: "250 kWh/mo · Night-heavy",
    location: "Pasig City",
  },
  wfh: {
    id: "wfh",
    initials: "WC",
    name: "WFH Couple",
    first: "Alex & Sam",
    subtitle: "700 kWh/mo · Day-heavy",
    location: "Makati City",
  },
};

type UserMsg = {
  id: number;
  from: "user";
  text: string;
  files?: string[];
  previews?: (string | null)[];
};

type AgentMsg = {
  id: number;
  from: "agent";
  phase: "booting" | "working" | "done";
  steps: AgentStep[];
  reply?: {
    text: string;
    hasMapArtifact?: boolean;
    next: Suggestion[];
  };
};

type ChatMsg = UserMsg | AgentMsg;
type Conversation = { id: string; title: string; messages: ChatMsg[] };

type Notice = {
  id: string;
  message: string;
  when: string;
  read: boolean;
};

const DESKTOP = "(min-width: 768px)";
function useIsDesktop() {
  return useSyncExternalStore(
    (cb) => {
      const mql = window.matchMedia(DESKTOP);
      mql.addEventListener("change", cb);
      return () => mql.removeEventListener("change", cb);
    },
    () => window.matchMedia(DESKTOP).matches,
    () => true,
  );
}

const noopSubscribe = () => () => {};
function useGreeting() {
  return useSyncExternalStore(
    noopSubscribe,
    () => {
      const h = new Date().getHours();
      if (h < 12) return "Good morning";
      if (h < 18) return "Good afternoon";
      return "Good evening";
    },
    () => "Hello",
  );
}

function newUuid(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

function titleFor(text: string, files: string[]) {
  if (files.length) return files.length === 1 ? files[0].slice(0, 34) : `${files.length} attached files`;
  const t = text.trim();
  return t.length > 34 ? `${t.slice(0, 34)}…` : t;
}

function FileThumb({ file }: { file: File }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!file.type.startsWith("image/")) return;
    const u = URL.createObjectURL(file);
    setUrl(u);
    setFailed(false);
    return () => URL.revokeObjectURL(u);
  }, [file]);

  if (!url || failed) {
    return (
      <span className="flex h-10 w-10 items-center justify-center rounded-[7px] bg-white text-[var(--label-2)] shadow-[0_0_0_1px_var(--hairline)]">
        {Icon.docLg}
      </span>
    );
  }
  return (
    <img
      src={url}
      alt={`Preview of ${file.name}`}
      onError={() => setFailed(true)}
      className="h-10 w-10 rounded-[7px] object-cover shadow-[0_0_0_1px_var(--hairline)]"
    />
  );
}

const navBtn = "row-btn press flex h-8 w-full items-center gap-2.5 rounded-[8px] px-2.5 text-left text-[14px]";

/* ------------------------------------------------------------------ */
/* App                                                                 */
/* ------------------------------------------------------------------ */

export default function App() {
  const [personaId, setPersonaId] = useState<PersonaId>("reyes");
  const [view, setView] = useState<View>("chat");
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);

  /* Claude-style right-side Map Canvas state */
  const [canvasOpen, setCanvasOpen] = useState(false);

  /* Auto close sidebar whenever roof map canvas is opened */
  useEffect(() => {
    if (canvasOpen) {
      setCollapsed(true);
      setMobileNav(false);
    }
  }, [canvasOpen]);

  const toggleCanvas = useCallback(() => {
    setCanvasOpen((prev) => {
      const next = !prev;
      if (next) {
        setCollapsed(true);
        setMobileNav(false);
      }
      return next;
    });
  }, []);

  const [convos, setConvos] = useState<Conversation[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [pendingDelete, setPendingDelete] = useState<{ id: string; title: string } | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const [notices, setNotices] = useState<Notice[]>([
    {
      id: "n1",
      message: "Sol UI shell ready. Select a starter prompt or type a message below.",
      when: "Just now",
      read: false,
    },
  ]);

  const nextMsg = useRef(1);
  const busyRef = useRef(false);
  const isDesktop = useIsDesktop();
  const reduced = useReducedMotion();
  const persona = PERSONAS[personaId];

  const appendMsg = useCallback((cid: string, msg: ChatMsg) => {
    setConvos((cs) => cs.map((c) => (c.id === cid ? { ...c, messages: [...c.messages, msg] } : c)));
  }, []);

  /* Pure UI-only local turn simulation */
  const runUiTurn = useCallback(
    (cid: string, _promptText: string, isNew: boolean) => {
      if (busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      const mid = nextMsg.current++;

      const patch = (fn: (m: AgentMsg) => AgentMsg) =>
        setConvos((cs) =>
          cs.map((c) =>
            c.id !== cid ? c : { ...c, messages: c.messages.map((m) => (m.id === mid && m.from === "agent" ? fn(m) : m)) },
          ),
        );

      const stepLabels = [
        "Reading household parameters",
        "Preparing roof map canvas",
        "Formatting summary",
      ];

      appendMsg(cid, {
        id: mid,
        from: "agent",
        phase: isNew ? "booting" : "working",
        steps: [],
      });

      const t1 = setTimeout(() => {
        patch((m) => ({
          ...m,
          phase: "working",
          steps: [{ id: "s1", label: stepLabels[0], status: "running" }],
        }));
      }, 280);

      const t2 = setTimeout(() => {
        patch((m) => ({
          ...m,
          phase: "working",
          steps: [
            { id: "s1", label: stepLabels[0], status: "done" },
            { id: "s2", label: stepLabels[1], status: "running" },
          ],
        }));
      }, 720);

      const t3 = setTimeout(() => {
        patch((m) => ({
          ...m,
          phase: "working",
          steps: [
            { id: "s1", label: stepLabels[0], status: "done" },
            { id: "s2", label: stepLabels[1], status: "done" },
            { id: "s3", label: stepLabels[2], status: "running" },
          ],
        }));
      }, 1150);

      const t4 = setTimeout(() => {
        patch((m) => ({
          ...m,
          phase: "done",
          steps: [
            { id: "s1", label: stepLabels[0], status: "done" },
            { id: "s2", label: stepLabels[1], status: "done" },
            { id: "s3", label: stepLabels[2], status: "done" },
          ],
          reply: {
            text: `Here is the roof map canvas for ${persona.name} (${persona.subtitle} · ${persona.location}). You can toggle the map canvas anytime from the card below or the top-right toolbar.`,
            hasMapArtifact: true,
            next: [
              {
                id: "bill",
                label: "Compare monthly bill options",
                hint: "On-grid vs hybrid solar overview",
                text: "Compare monthly bill options",
              },
              {
                id: "roof",
                label: "Adjust roof area & orientation",
                hint: "Enter roof type, tilt, and usable area",
                text: "Adjust roof area & orientation",
              },
            ],
          },
        }));
        /* Auto-open the Claude-style right Map Canvas when the turn finishes */
        setCanvasOpen(true);
        setCollapsed(true);
        setMobileNav(false);
        busyRef.current = false;
        setBusy(false);
      }, 1500);

      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
        clearTimeout(t3);
        clearTimeout(t4);
      };
    },
    [appendMsg, persona],
  );

  const ask = useCallback(
    (text: string, files: string[] = [], previews?: (string | null)[]) => {
      const t = text.trim();
      if ((!t && !files.length) || busyRef.current) return;
      let cid = currentId;
      const isNew = cid === null;
      if (cid === null) {
        const id = newUuid();
        cid = id;
        setConvos((cs) => [{ id, title: titleFor(t, files), messages: [] }, ...cs]);
        setCurrentId(id);
      }
      appendMsg(cid, {
        id: nextMsg.current++,
        from: "user",
        text: t || "Attached files",
        files: files.length ? files : undefined,
        previews: files.length ? previews : undefined,
      });
      runUiTurn(cid, t, isNew);
    },
    [currentId, appendMsg, runUiTurn],
  );

  const newChat = () => {
    setCurrentId(null);
    setView("chat");
    setCanvasOpen(false);
    setMobileNav(false);
  };

  const deleteChat = (id: string) => {
    setDeleteOpen(false);
    setConvos((cs) => cs.filter((c) => c.id !== id));
    if (currentId === id) {
      setCurrentId(null);
      setCanvasOpen(false);
    }
  };

  const go = (v: View) => {
    setView(v);
    setMobileNav(false);
  };

  const current = convos.find((c) => c.id === currentId);
  const unread = notices.filter((n) => !n.read).length;

  const markRead = () => {
    if (!unread) return;
    setNotices((list) => list.map((n) => ({ ...n, read: true })));
  };

  return (
    <LazyMotion features={domAnimation} strict>
      <div className="shell h-dvh bg-white" data-collapsed={collapsed}>
        {/* ---------------- Sidebar ---------------- */}
        <aside
          className="sidebar bg-[var(--sidebar)]"
          data-mobile-open={mobileNav}
          inert={isDesktop ? collapsed : !mobileNav}
          aria-label="Sidebar"
        >
          <div className="sidebar-inner flex h-full flex-col">
            <div className="flex h-12 items-center gap-2 px-3">
              <Logo size={24} />
              <span className="flex-1 text-[14px] font-semibold tracking-tight">Sol</span>
              <button
                type="button"
                className={btn.icon}
                onClick={() => (isDesktop ? setCollapsed(true) : setMobileNav(false))}
                aria-label="Hide sidebar"
              >
                {Icon.sidebar}
              </button>
            </div>

            <nav className="grid gap-0.5 px-2 pt-1" aria-label="Primary">
              <NavItem icon={Icon.chat} label="New chat" active={view === "chat" && currentId === null} onClick={newChat} />
              <NavItem icon={Icon.overview} label="Overview" active={view === "overview"} onClick={() => go("overview")} />
              <NavItem icon={Icon.saved} label="Saved" active={view === "saved"} onClick={() => go("saved")} />
            </nav>

            <div className="mx-4 my-3 h-px bg-[var(--hairline)]" aria-hidden="true" />

            <div className="flex items-center justify-between px-4 pb-1">
              <span className="text-[12px] font-medium text-[var(--label-2)]">Recents</span>
              <button type="button" onClick={newChat} className={`${btn.icon} h-6 w-6`} aria-label="New chat">
                {Icon.plus}
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
              {convos.length === 0 ? (
                <p className="px-2.5 py-1.5 text-[13px] text-[var(--label-3)]">No chats yet</p>
              ) : (
                <ul className="grid grid-cols-[minmax(0,1fr)] gap-0.5">
                  {convos.map((c) => {
                    const active = view === "chat" && currentId === c.id;
                    return (
                      <li key={c.id} className="enter min-w-0">
                        <div
                          className={`row-btn flex h-8 min-w-0 items-center gap-1 rounded-[8px] pr-1.5 ${
                            active ? "bg-[var(--fill-2)]" : ""
                          }`}
                        >
                          <button
                            type="button"
                            onClick={() => {
                              setCurrentId(c.id);
                              go("chat");
                            }}
                            aria-current={active ? "page" : undefined}
                            title={c.title}
                            className={`flex h-full min-w-0 flex-1 items-center rounded-[8px] pl-2.5 text-left text-[13px] ${
                              active ? "font-medium" : ""
                            }`}
                          >
                            <span className="truncate">{c.title}</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setPendingDelete({ id: c.id, title: c.title });
                              setDeleteOpen(true);
                            }}
                            aria-label={`Delete chat "${c.title}"`}
                            aria-haspopup="dialog"
                            className="press flex h-6 w-6 shrink-0 items-center justify-center rounded-[7px] text-[var(--label-3)] hover:bg-[var(--fill-2)] hover:text-[var(--fg)]"
                          >
                            {Icon.trash}
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            {/* Household profile switcher */}
            <div className="px-2 pb-2">
              <div className="mb-2 h-px bg-[var(--hairline)]" aria-hidden="true" />
              <Popover
                label="Household profile"
                placement="top-start"
                className="w-[244px]"
                trigger={({ open, toggle }) => (
                  <button type="button" onClick={toggle} aria-expanded={open} className={`${navBtn} h-auto py-2`}>
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--fg)] text-[12px] font-medium text-white">
                      {persona.initials}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium">{persona.name}</span>
                      <span className="block truncate text-[12px] text-[var(--label-2)]">{persona.subtitle}</span>
                    </span>
                    <span className="text-[var(--label-3)]">{Icon.chevronDown}</span>
                  </button>
                )}
              >
                {(close) => (
                  <div role="menu" aria-label="Switch household">
                    <p className="px-2.5 pt-1.5 pb-1 text-[12px] font-medium text-[var(--label-2)]">Household profile</p>
                    {(Object.keys(PERSONAS) as PersonaId[]).map((pid) => {
                      const p = PERSONAS[pid];
                      return (
                        <MenuItem
                          key={pid}
                          checked={personaId === pid}
                          onSelect={() => {
                            setPersonaId(pid);
                            close();
                          }}
                        >
                          <span className="block font-medium">{p.name}</span>
                          <span className="block text-[12px] text-[var(--label-2)]">
                            {p.subtitle} · {p.location}
                          </span>
                        </MenuItem>
                      );
                    })}
                  </div>
                )}
              </Popover>
            </div>
          </div>
        </aside>

        <div className="mobile-backdrop" data-open={mobileNav} onClick={() => setMobileNav(false)} aria-hidden="true" />

        {/* ---------------- Main Workspace (Chat + Right-Side Claude Map Canvas) ---------------- */}
        <div className="relative flex min-w-0 flex-1 overflow-hidden">
          {/* Left / Main Chat Column */}
          <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
            <header className="flex h-12 shrink-0 items-center gap-1 px-3">
              <button
                type="button"
                className={`${btn.icon} md:hidden`}
                onClick={() => setMobileNav(true)}
                aria-label="Open sidebar"
              >
                {Icon.menu}
              </button>
              <button
                type="button"
                className={`${btn.icon} max-md:hidden ${collapsed ? "" : "pointer-events-none opacity-0"}`}
                onClick={() => setCollapsed(false)}
                aria-label="Show sidebar"
                tabIndex={collapsed ? 0 : -1}
                aria-hidden={!collapsed}
              >
                {Icon.sidebar}
              </button>
              <div className="flex-1" />

              {/* Toggle Map Canvas button in header */}
              <button
                type="button"
                onClick={toggleCanvas}
                aria-pressed={canvasOpen}
                title={canvasOpen ? "Hide roof map canvas" : "Open roof map canvas"}
                className={`row-btn press flex h-8 items-center gap-1.5 rounded-[8px] px-2.5 text-[13px] font-medium ${
                  canvasOpen ? "bg-[var(--brand-soft)] text-[var(--brand)]" : "text-[var(--label-2)]"
                }`}
              >
                {Icon.map}
                <span className="max-sm:hidden">Roof map</span>
              </button>

              <Popover
                label="Notifications"
                placement="bottom-end"
                className="w-[300px] max-w-[calc(100vw-24px)]"
                trigger={({ open, toggle }) => (
                  <button
                    type="button"
                    onClick={() => {
                      toggle();
                      if (!open) markRead();
                    }}
                    aria-expanded={open}
                    className={`${btn.icon} relative text-[var(--fg)]`}
                    aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
                  >
                    {Icon.bell}
                    <span
                      className="badge absolute top-1 right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--accent)] px-1 text-[10px] font-semibold text-[var(--fg)] shadow-[0_0_0_2px_#fff]"
                      data-show={unread > 0}
                      aria-hidden="true"
                    >
                      <span key={unread} className="pop">
                        {unread || 1}
                      </span>
                    </span>
                  </button>
                )}
              >
                {() => (
                  <div>
                    <p className="px-2.5 pt-1.5 pb-1 text-[13px] font-medium">Notifications</p>
                    <ul className="grid gap-0.5">
                      {notices.map((n) => (
                        <li key={n.id} className="flex gap-2 rounded-[10px] px-2.5 py-2">
                          <span
                            className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                              n.read ? "bg-transparent" : "bg-[var(--accent)]"
                            }`}
                            aria-hidden="true"
                          />
                          <span>
                            <span className="block text-[13px] leading-snug">{n.message}</span>
                            <span className="mt-0.5 block text-[12px] text-[var(--label-2)]">{n.when}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </Popover>
            </header>

            {view === "chat" && (
              <ChatView
                messages={current?.messages ?? []}
                busy={busy}
                first={persona.first}
                subtitle={`${persona.subtitle} · ${persona.location}`}
                canvasOpen={canvasOpen}
                onToggleCanvas={toggleCanvas}
                onAsk={ask}
              />
            )}
            {view === "overview" && (
              <PlaceholderView
                title="Overview"
                subtitle="Clean placeholder view for solar sizing, roof summary, and ROI comparison cards."
                onNewChat={newChat}
              />
            )}
            {view === "saved" && (
              <PlaceholderView
                title="Saved"
                subtitle="Clean placeholder view for saved solar packages and records."
                onNewChat={newChat}
              />
            )}
          </main>

          {/* ---------------- Right-Side Claude-Style Map Canvas ---------------- */}
          <AnimatePresence initial={false}>
            {canvasOpen && (
              <m.aside
                key="map-canvas"
                initial={reduced ? { opacity: 0 } : { width: 0, opacity: 0 }}
                animate={reduced ? { opacity: 1 } : { width: "48%", opacity: 1 }}
                exit={reduced ? { opacity: 0 } : { width: 0, opacity: 0 }}
                transition={{ duration: 0.32, ease: [0.25, 1, 0.5, 1] }}
                aria-label="Roof Map Canvas"
                className="flex h-full shrink-0 flex-col overflow-hidden border-l border-[var(--hairline)] bg-[var(--sidebar)] max-md:fixed max-md:inset-0 max-md:z-50 max-md:!w-full"
              >
                <div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--hairline)] bg-white px-4">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="text-[var(--brand)]">{Icon.map}</span>
                    <span className="truncate text-[14px] font-medium">Roof Map</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setCanvasOpen(false)}
                    className={`${btn.icon} row-btn`}
                    aria-label="Close map canvas"
                  >
                    {Icon.close}
                  </button>
                </div>

                <div className="flex min-h-0 flex-1 p-4">
                  <div className="flex flex-1 items-center justify-center rounded-[14px] bg-[var(--fill)] text-[14px] font-medium text-[var(--label-3)] shadow-[0_0_0_1px_var(--hairline)]">
                    Map Placeholder
                  </div>
                </div>
              </m.aside>
            )}
          </AnimatePresence>
        </div>
      </div>

      <ConfirmDialog
        open={deleteOpen}
        title="Delete this chat?"
        body={
          <>
            <span className="line-clamp-1 font-medium text-[var(--fg)]">{pendingDelete?.title ?? "This chat"}</span>
            This removes the conversation from your sidebar.
          </>
        }
        confirmLabel="Delete"
        onCancel={() => setDeleteOpen(false)}
        onConfirm={() => pendingDelete && deleteChat(pendingDelete.id)}
      />
    </LazyMotion>
  );
}

/* ------------------------------------------------------------------ */
/* Sidebar item                                                        */
/* ------------------------------------------------------------------ */

function NavItem({
  icon,
  label,
  active,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`${navBtn} ${active ? "bg-[var(--fill-2)] font-medium" : ""}`}
    >
      <span className={active ? "text-[var(--brand)]" : "text-[var(--label-2)]"}>{icon}</span>
      <span className="flex-1">{label}</span>
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Claude-Style Artifact Card in Chat                                  */
/* ------------------------------------------------------------------ */

function MapArtifactCard({
  open,
  onToggle,
}: {
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className={`card row-btn press flex w-full max-w-[380px] items-center gap-3 px-4 py-3 text-left transition-shadow ${
        open ? "shadow-[0_0_0_1.5px_var(--brand),0_4px_12px_rgba(0,0,0,0.04)]" : ""
      }`}
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-[var(--brand-soft)] text-[var(--brand)]">
        {Icon.map}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[14px] font-medium">Roof Map</span>
        <span className="block truncate text-[12px] text-[var(--label-2)]">
          {open ? "Showing in right canvas" : "Click to open map canvas"}
        </span>
      </span>
      <span className="text-[var(--label-3)]">{Icon.chevronRight}</span>
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Chat View                                                           */
/* ------------------------------------------------------------------ */

type PillId = "roof" | "bill" | "packages" | "upload";

const PILLS: { id: PillId; label: string; icon: ReactNode; prompt: string }[] = [
  { id: "roof", label: "Check roof size", icon: Icon.map, prompt: "Help me estimate my roof size and solar capacity" },
  { id: "bill", label: "Analyze monthly bill", icon: Icon.doc, prompt: "Analyze a ₱6,780 monthly electricity bill" },
  { id: "packages", label: "Compare packages", icon: Icon.search, prompt: "Compare on-grid and hybrid solar packages" },
  { id: "upload", label: "Attach bill or photo", icon: Icon.upload, prompt: "" },
];

function ChatView({
  messages,
  busy,
  first,
  subtitle,
  canvasOpen,
  onToggleCanvas,
  onAsk,
}: {
  messages: ChatMsg[];
  busy: boolean;
  first: string;
  subtitle: string;
  canvasOpen: boolean;
  onToggleCanvas: () => void;
  onAsk: (text: string, files?: string[], previews?: (string | null)[]) => void;
}) {
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [lightbox, setLightbox] = useState<{ src: string; name: string } | null>(null);
  const [lang, setLang] = useState("Auto");

  const fileRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const lastTop = useRef<number | null>(null);

  const reduced = useReducedMotion();
  const hello = useGreeting();
  const empty = messages.length === 0;

  /* Continuity: composer glides from center to bottom when conversation starts */
  useLayoutEffect(() => {
    const el = composerRef.current;
    if (!el) return;
    const top = el.getBoundingClientRect().top;
    const prev = lastTop.current;
    lastTop.current = top;
    if (prev === null || reduced) return;
    const dy = prev - top;
    if (Math.abs(dy) < 2) return;
    el.animate([{ transform: `translateY(${dy}px)` }, { transform: "translateY(0)" }], {
      duration: 520,
      easing: "cubic-bezier(0.32, 0.72, 0, 1)",
    });
  }, [empty, reduced]);

  useEffect(() => {
    const onResize = () => {
      if (composerRef.current) lastTop.current = composerRef.current.getBoundingClientRect().top;
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el || empty) return;
    el.scrollTo({ top: el.scrollHeight, behavior: reduced ? "auto" : "smooth" });
  }, [messages, reduced, empty]);

  const submit = (overrideFiles?: File[], overrideText?: string) => {
    const currentFiles = overrideFiles ?? files;
    const message = overrideText ?? input;
    if (busy || (!message.trim() && !currentFiles.length)) return;
    const previews = currentFiles.map((f) =>
      f.type.startsWith("image/") ? URL.createObjectURL(f) : null,
    );
    onAsk(
      message,
      currentFiles.map((f) => f.name),
      previews,
    );
    setInput("");
    setFiles([]);
  };

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!picked.length) return;
    setFiles((fs) => [...fs, ...picked].slice(0, 6));
    textRef.current?.focus();
  };

  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const images = Array.from(e.clipboardData.items)
      .filter((item) => item.kind === "file" && /^image\/(jpeg|png|webp)$/.test(item.type))
      .map((item) => item.getAsFile())
      .filter((f): f is File => !!f);
    if (!images.length) return;
    e.preventDefault();
    setFiles((fs) => [...fs, ...images].slice(0, 6));
  };

  const onKeyDown = (e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const attach = () => {
    fileRef.current?.click();
  };

  const last = messages.at(-1);
  const next = !busy && last?.from === "agent" && last.phase === "done" ? (last.reply?.next ?? []) : [];
  const nextKey = last?.id;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Conversation / hero */}
      <div ref={scrollRef} className={`min-h-0 flex-1 overflow-y-auto ${empty ? "flex flex-col justify-end" : ""}`}>
        {empty ? (
          <m.div
            initial={reduced ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
            className="flex flex-col items-center px-6 pb-7 text-center"
          >
            <Logo size={60} />
            <h1 className="mt-5 text-[28px] leading-tight font-medium tracking-tight max-sm:text-[24px]">
              {hello}, {first}. How can I help?
            </h1>
          </m.div>
        ) : (
          <div role="log" aria-live="polite" className="mx-auto flex w-full max-w-[760px] flex-col gap-6 px-6 pt-4 pb-6">
            {messages.map((msg) => {
              if (msg.from === "user") {
                return (
                  <div key={msg.id} className="enter flex flex-col items-end gap-1.5">
                    {msg.files && (
                      <div className="flex flex-wrap justify-end gap-1.5">
                        {msg.files.map((f, i) => {
                          const src = msg.previews?.[i];
                          return src ? (
                            <button
                              key={`${f}-${i}`}
                              type="button"
                              onClick={() => setLightbox({ src, name: f })}
                              className="press block overflow-hidden rounded-[14px] bg-white shadow-[0_0_0_1px_var(--hairline)]"
                            >
                              <img src={src} alt={f} className="block max-h-[200px] max-w-[240px] object-cover" />
                            </button>
                          ) : (
                            <span
                              key={`${f}-${i}`}
                              className="inline-flex items-center gap-1.5 rounded-[10px] bg-white px-2.5 py-1.5 text-[12px] shadow-[0_0_0_1px_var(--hairline)]"
                            >
                              {Icon.docLg}
                              {f}
                            </span>
                          );
                        })}
                      </div>
                    )}
                    <p className="max-w-[75%] rounded-[18px] bg-[var(--fill-2)] px-4 py-2 text-[15px] leading-relaxed">
                      {msg.text}
                    </p>
                  </div>
                );
              }

              return (
                <div key={msg.id} className="enter-card flex gap-3">
                  <Logo size={24} className="mt-0.5" />
                  <div className="flex min-w-0 flex-1 flex-col gap-3">
                    {msg.phase === "booting" ? (
                      <div className="enter flex items-center gap-3 py-0.5">
                        <Spinner variant="main" size={26} label="Sol is getting ready" />
                        <span className="text-[14px] text-[var(--label-2)]">Getting ready…</span>
                      </div>
                    ) : (
                      <>
                        {msg.steps.length > 0 && <ThinkingSteps steps={msg.steps} done={msg.phase === "done"} />}
                        {msg.phase === "done" && msg.reply && (
                          <div className="enter-card flex flex-col gap-3">
                            <p className="text-[15px] leading-relaxed">{msg.reply.text}</p>
                            {msg.reply.hasMapArtifact && (
                              <MapArtifactCard open={canvasOpen} onToggle={onToggleCanvas} />
                            )}
                            {msg.id === nextKey && next.length > 0 && (
                              <NextSteps items={next} onPick={(s) => onAsk(s.text)} />
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Starter pills (empty state only), directly above the composer */}
      {empty && (
        <div className="mx-auto grid w-full max-w-[760px] grid-cols-2 gap-2 px-6 pb-3 sm:grid-cols-4">
          {PILLS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => (p.id === "upload" ? attach() : onAsk(p.prompt))}
              disabled={busy}
              className="pill press row-btn flex h-9 min-w-0 items-center justify-center gap-1.5 rounded-full bg-white px-3 text-[13px] font-medium shadow-[0_0_0_1px_var(--hairline),0_1px_2px_rgba(0,0,0,0.03)] disabled:opacity-40 [&_svg]:size-3.5"
            >
              <span className="shrink-0 text-[var(--brand)]">{p.icon}</span>
              <span className="truncate">{p.label}</span>
            </button>
          ))}
        </div>
      )}

      {/* Composer */}
      <div ref={composerRef} className="mx-auto w-full max-w-[760px] shrink-0 px-6">
        <div className="composer rounded-[18px] bg-white">
          <div className="flex items-center gap-1.5 px-4 pt-3 text-[13px]">
            <span className="font-medium">Sol</span>
            <span className="text-[var(--label-3)]">· {subtitle}</span>
          </div>

          {files.length > 0 && (
            <div className="flex flex-wrap gap-1.5 px-3 pt-2.5">
              {files.map((f, i) => (
                <span
                  key={`${f.name}-${i}`}
                  className="pop inline-flex items-center gap-1.5 rounded-[10px] bg-[var(--fill)] py-1 pr-1 pl-1 text-[12px]"
                >
                  <FileThumb file={f} />
                  <span className="max-w-[160px] truncate">{f.name}</span>
                  <button
                    type="button"
                    onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))}
                    className={`${btn.icon} row-btn h-5 w-5 rounded-full`}
                    aria-label={`Remove ${f.name}`}
                  >
                    {Icon.close}
                  </button>
                </span>
              ))}
            </div>
          )}

          <input
            ref={fileRef}
            type="file"
            multiple
            accept="image/jpeg,image/png,image/webp,application/pdf"
            onChange={onPick}
            className="hidden"
            tabIndex={-1}
            aria-hidden="true"
          />

          <label htmlFor="composer" className="sr-only">
            Message Sol
          </label>
          <textarea
            id="composer"
            ref={textRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            onPaste={onPaste}
            rows={2}
            placeholder="Ask about your roof, monthly bill, or solar options…"
            className="block w-full resize-none bg-transparent px-4 pt-2.5 text-[15px] leading-relaxed outline-none placeholder:text-[var(--label-3)]"
          />

          <div className="flex items-center gap-1 px-2.5 pb-2.5">
            <Popover
              label="Attach"
              placement="top-start"
              className="w-[200px]"
              trigger={({ open, toggle }) => (
                <button
                  type="button"
                  onClick={toggle}
                  aria-expanded={open}
                  aria-haspopup="menu"
                  className={`${btn.icon} row-btn`}
                  aria-label="Attach files"
                  title="Attach files"
                >
                  {Icon.plus}
                </button>
              )}
            >
              {(close) => (
                <div role="menu" aria-label="Attach">
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      close();
                      attach();
                    }}
                    className="row-btn flex w-full items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-left text-[14px]"
                  >
                    <span className="text-[var(--label-2)]">{Icon.image}</span>
                    Photos or PDF
                  </button>
                </div>
              )}
            </Popover>

            <div className="flex-1" />

            <Popover
              label="Language"
              placement="top-end"
              className="w-[170px]"
              trigger={({ open, toggle }) => (
                <button
                  type="button"
                  onClick={toggle}
                  aria-expanded={open}
                  className="row-btn press flex h-8 items-center gap-1 rounded-[8px] px-2.5 text-[13px] font-medium"
                >
                  {lang} {Icon.chevronDown}
                </button>
              )}
            >
              {(close) => (
                <div role="menu" aria-label="Reply language">
                  {["Auto", "English", "Taglish"].map((l) => (
                    <MenuItem
                      key={l}
                      checked={lang === l}
                      onSelect={() => {
                        setLang(l);
                        close();
                      }}
                    >
                      {l === "Auto" ? "Auto-detect" : l}
                    </MenuItem>
                  ))}
                </div>
              )}
            </Popover>

            <button
              type="button"
              onClick={() => submit()}
              disabled={busy || (!input.trim() && !files.length)}
              aria-label={busy ? "Sol is working" : "Send"}
              className="btn-primary press flex h-8 w-8 items-center justify-center rounded-[9px] disabled:bg-[var(--fill-2)] disabled:text-[var(--label-3)]"
            >
              {busy ? <Spinner /> : Icon.send}
            </button>
          </div>
        </div>
      </div>

      {lightbox && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={lightbox.name}
          onClick={() => setLightbox(null)}
          className="enter fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-6"
        >
          <button
            type="button"
            onClick={() => setLightbox(null)}
            aria-label="Close preview"
            className="press absolute top-4 right-4 flex h-9 w-9 items-center justify-center rounded-full text-white/80 hover:text-white"
          >
            {Icon.close}
          </button>
          <img
            src={lightbox.src}
            alt={lightbox.name}
            onClick={(e) => e.stopPropagation()}
            className="max-h-full max-w-full rounded-lg object-contain"
          />
        </div>
      )}

      {empty && <div className="flex-1" aria-hidden="true" />}

      <p className="shrink-0 px-6 py-3 text-center text-[12px] text-[var(--label-3)]">
        Estimates are for planning only. Demo uses synthetic household data.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* What's next suggestions                                             */
/* ------------------------------------------------------------------ */

function NextSteps({ items, onPick }: { items: Suggestion[]; onPick: (s: Suggestion) => void }) {
  return (
    <div className="enter-card grid gap-2 pt-1">
      <span className="text-[13px] font-medium text-[var(--label-2)]">What&apos;s next</span>
      <Group className="max-w-[520px]">
        {items.map((s, i) => (
          <div key={s.id}>
            {i > 0 && <Separator />}
            <button
              type="button"
              onClick={() => onPick(s)}
              className="row-btn press flex w-full items-center gap-3 px-4 py-3 text-left"
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--brand-soft)] text-[var(--brand)]">
                {Icon.sun}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14px] font-medium">{s.label}</span>
                {s.hint && <span className="block truncate text-[13px] text-[var(--label-2)]">{s.hint}</span>}
              </span>
              <span className="text-[var(--label-3)]">{Icon.chevronRight}</span>
            </button>
          </div>
        ))}
      </Group>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Clean Minimal Placeholder View                                      */
/* ------------------------------------------------------------------ */

function PlaceholderView({
  title,
  subtitle,
  onNewChat,
}: {
  title: string;
  subtitle: string;
  onNewChat: () => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-[760px] flex-1 flex-col justify-center px-6 pb-12">
      <div className="card p-8 text-center">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-[var(--brand-soft)] text-[var(--brand)]">
          {Icon.sun}
        </div>
        <h1 className="mt-4 text-[20px] font-semibold tracking-tight">{title}</h1>
        <p className="mx-auto mt-1.5 max-w-[420px] text-[14px] leading-relaxed text-[var(--label-2)]">{subtitle}</p>
        <div className="mt-5">
          <button type="button" onClick={onNewChat} className={`${btn.secondary} btn-sm`}>
            Back to chat
          </button>
        </div>
      </div>
    </div>
  );
}
