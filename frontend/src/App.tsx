import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
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
import { LoginView } from "./components/LoginView";
import { MapCanvas } from "./components/MapCanvas";
import { OverviewView, SavedView } from "./components/ResultsViews";
import { RichText } from "./components/RichText";
import { SolLogo } from "./components/SolLogo";
import { AnimatedSol } from "./components/SolMascotLazy";
import {
  ApiError,
  deleteSession,
  fetchMe,
  getSessionHistory,
  listSessions,
  logout,
  onUnauthorized,
  streamChat,
  type Language,
  type StepEvent,
  type User,
} from "./lib/api";
import {
  ConfirmDialog,
  MenuItem,
  Popover,
  ThinkingSteps,
  useReducedMotion,
  type AgentStep,
  type Suggestion,
} from "./components/ui";

/* ------------------------------------------------------------------ */
/* Types & helpers                                                     */
/* ------------------------------------------------------------------ */

type View = "chat" | "overview" | "saved";
/** What the UI shows about the signed-in household. Built from the account, never hardcoded. */
type Persona = {
  initials: string;
  name: string;
  first: string;
  subtitle: string;
  location: string | null;
};

const TEMPLATE_LABEL = { night_heavy: "Night-heavy", balanced: "Balanced", day_heavy: "Day-heavy" } as const;

function toPersona(u: User): Persona {
  const h = u.household;
  const usage = [h.monthlyKwh ? `${h.monthlyKwh} kWh/mo` : null, h.template ? TEMPLATE_LABEL[h.template] : null]
    .filter(Boolean)
    .join(" · ");
  return {
    initials: u.initials,
    name: h.name,
    first: u.name.split(/\s+/)[0],
    subtitle: usage || "Tell Sol about your home to get started",
    location: h.city,
  };
}
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
    next?: Suggestion[];
  };
};

type ChatMsg = UserMsg | AgentMsg;

type Conversation = {
  id: string;
  title: string;
  messages: ChatMsg[];
  /** false until the saved messages of a chat from the server have been fetched */
  loaded: boolean;
};

type Notice = {
  id: string;
  message: string;
  when: string;
  read: boolean;
};

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

  useEffect(() => {
    if (!file.type.startsWith("image/")) return;
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);

  if (!url) {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-[4px] bg-[#f0f0ee] text-[#787774]">
        {Icon.doc}
      </span>
    );
  }
  return <img src={url} alt={file.name} className="h-5 w-5 rounded-[4px] object-cover" />;
}

const LANGS = { Auto: "auto", English: "english", Taglish: "taglish" } as const satisfies Record<string, Language>;
type LangLabel = keyof typeof LANGS;

/** Add a step, or update the one with the same id (ids are stable per turn). */
function upsertStep(steps: AgentStep[], s: StepEvent): AgentStep[] {
  const i = steps.findIndex((x) => x.id === s.id);
  if (i < 0) return [...steps, s];
  const next = steps.slice();
  next[i] = s;
  return next;
}

/** Reveals a reply word by word so it reads like someone answering. Plays once per message. */
const typed = new Set<number>();
function TypedText({ id, text, animate }: { id: number; text: string; animate: boolean }) {
  const words = useMemo(() => text.split(/(\s+)/), [text]);
  const [play] = useState(() => animate && !typed.has(id)); // decided once: later renders must not cancel the animation
  const [shown, setShown] = useState(play ? 0 : words.length);
  useEffect(() => {
    if (!play) return;
    typed.add(id);
    const t = setInterval(() => setShown((n) => (n >= words.length ? n : n + 2)), 28);
    return () => clearInterval(t);
  }, [play, id, words.length]);
  // Replies with lists or tables are shown whole: typing half a table or a half-open **bold** looks broken.
  if (/\n/.test(text)) return <RichText text={text} />;
  return <RichText text={words.slice(0, shown).join("")} />;
}

/* ------------------------------------------------------------------ */
/* Main App Component                                                  */
/* ------------------------------------------------------------------ */

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);
  const [view, setView] = useState<View>("chat");

  /* Roof Map view state: true = side-by-side view; false = centered 100% workspace */
  const [canvasOpen, setCanvasOpen] = useState(false);
  const [roofTick, setRoofTick] = useState(0);

  /* Adjustable split state: default 40% chat / 60% map */
  const [splitPercent, setSplitPercent] = useState(40);
  const [isDragging, setIsDragging] = useState(false);
  const workspaceRef = useRef<HTMLDivElement>(null);

  const [convos, setConvos] = useState<Conversation[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [pendingDelete, setPendingDelete] = useState<{ id: string; title: string } | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const [notices, setNotices] = useState<Notice[]>([]);

  const [lang, setLang] = useState<LangLabel>("Auto");
  const nextMsg = useRef(1);
  const busyRef = useRef(false);
  const abortRef = useRef<(() => void) | null>(null);
  const reduced = useReducedMotion();
  const persona = useMemo(() => (user ? toPersona(user) : null), [user]);

  /* Restore the saved sign-in, if any. */
  useEffect(() => {
    let live = true;
    fetchMe()
      .then((u) => live && setUser(u))
      .catch(() => {})
      .finally(() => live && setBooting(false));
    return () => {
      live = false;
    };
  }, []);

  /* Clear everything that belongs to the previous account. */
  const resetWorkspace = useCallback(() => {
    if (abortRef.current) abortRef.current();
    abortRef.current = null;
    busyRef.current = false;
    setBusy(false);
    setConvos([]);
    setCurrentId(null);
    setCanvasOpen(false);
    setView("chat");
  }, []);

  /* The server rejected our token: go back to the login screen. */
  useEffect(
    () =>
      onUnauthorized(() => {
        resetWorkspace();
        setUser(null);
      }),
    [resetWorkspace],
  );

  /* Load this account's chats whenever someone signs in. */
  useEffect(() => {
    if (!user) return;
    let live = true;
    listSessions()
      .then((rows) => {
        if (!live) return;
        setConvos((cs) => {
          const known = new Set(cs.map((c) => c.id));
          const fromServer = rows.filter((r) => !known.has(r.id)).map((r) => ({ id: r.id, title: r.title, messages: [], loaded: false }));
          return [...cs, ...fromServer];
        });
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [user]);

  const stopTurn = useCallback(() => {
    if (abortRef.current) {
      abortRef.current();
      abortRef.current = null;
    }
    busyRef.current = false;
    setBusy(false);
  }, []);

  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current();
    };
  }, []);

  /* Smooth pointer tracking for adjustable chat/map split */
  const handlePointerDown = (e: React.PointerEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  useEffect(() => {
    if (!isDragging) return;

    const handlePointerMove = (e: PointerEvent) => {
      if (!workspaceRef.current) return;
      const rect = workspaceRef.current.getBoundingClientRect();
      const rawX = e.clientX - rect.left;
      const pct = (rawX / rect.width) * 100;
      // Clamp split between 25% and 75%
      const clamped = Math.min(Math.max(pct, 25), 75);
      setSplitPercent(clamped);
    };

    const handlePointerUp = () => {
      setIsDragging(false);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging]);

  const appendMsg = useCallback((cid: string, msg: ChatMsg) => {
    setConvos((cs) => cs.map((c) => (c.id === cid ? { ...c, messages: [...c.messages, msg] } : c)));
  }, []);

  /* One real turn: stream the backend agent's steps and reply into the chat. */
  const runTurn = useCallback(
    (cid: string, text: string, isNew: boolean, rawFiles: File[]) => {
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
      const allDone = (steps: AgentStep[]): AgentStep[] => steps.map((s) => ({ ...s, status: "done" as const }));

      appendMsg(cid, { id: mid, from: "agent", phase: isNew ? "booting" : "working", steps: [] });

      const controller = new AbortController();
      abortRef.current = () => {
        controller.abort();
        patch((m) => ({
          ...m,
          phase: "done",
          steps: allDone(m.steps),
          reply: { text: "Generation stopped.", hasMapArtifact: false, next: [] },
        }));
      };

      streamChat({
        conversationId: cid,
        message: text || "Attached files",
        language: LANGS[lang],
        files: rawFiles,
        signal: controller.signal,
        onStep: (s) => patch((m) => ({ ...m, phase: "working", steps: upsertStep(m.steps, s) })),
      })
        .then((reply) => {
          patch((m) => ({
            ...m,
            phase: "done",
            steps: allDone(m.steps),
            reply: { text: reply.text, hasMapArtifact: reply.hasMapArtifact, next: reply.next },
          }));
          if (reply.hasMapArtifact) setCanvasOpen(true);
          setRoofTick((t) => t + 1);
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted) return; // stopTurn already updated the message
          const message =
            err instanceof ApiError && err.status > 0
              ? err.message
              : "I couldn't reach the Sol server. Make sure the backend is running on port 8000, then try again.";
          patch((m) => ({ ...m, phase: "done", steps: allDone(m.steps), reply: { text: message, hasMapArtifact: false, next: [] } }));
        })
        .finally(() => {
          abortRef.current = null;
          busyRef.current = false;
          setBusy(false);
        });
    },
    [appendMsg, lang],
  );

  const ask = useCallback(
    (text: string, files: string[] = [], previews?: (string | null)[], rawFiles: File[] = []) => {
      const t = text.trim();
      if ((!t && !files.length) || busyRef.current) return;
      let cid = currentId;
      const isNew = cid === null;
      if (cid === null) {
        const id = newUuid();
        cid = id;
        setConvos((cs) => [{ id, title: titleFor(t, files), messages: [], loaded: true }, ...cs]);
        setCurrentId(id);
      }
      appendMsg(cid, {
        id: nextMsg.current++,
        from: "user",
        text: t || "Attached files",
        files: files.length ? files : undefined,
        previews: files.length ? previews : undefined,
      });
      runTurn(cid, t, isNew, rawFiles);
    },
    [currentId, appendMsg, runTurn],
  );

  const onRoofSubmitted = useCallback(
    (what: "drawn" | "sketch") => ask(what === "sketch" ? "I've finished sketching my roof." : "I've finished drawing my roof outline."),
    [ask],
  );

  const toggleCanvas = useCallback(() => {
    setCanvasOpen((prev) => !prev);
  }, []);

  const newChat = () => {
    stopTurn();
    setCurrentId(null);
    setView("chat");
    setCanvasOpen(false);
  };

  /* Open a chat; saved ones fetch their messages the first time. */
  const openChat = (id: string) => {
    stopTurn();
    setCurrentId(id);
    go("chat");
    const convo = convos.find((c) => c.id === id);
    if (!convo || convo.loaded) return;
    getSessionHistory(id)
      .then((history) => {
        const messages: ChatMsg[] = history.map((h) => {
          const mid = nextMsg.current++;
          if (h.role === "user") return { id: mid, from: "user", text: h.text };
          typed.add(mid); // restored replies appear at once instead of being typed out again
          return { id: mid, from: "agent", phase: "done", steps: [], reply: { text: h.text } };
        });
        setConvos((cs) => cs.map((c) => (c.id === id ? { ...c, messages, loaded: true } : c)));
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) setConvos((cs) => cs.filter((c) => c.id !== id));
      });
  };

  const deleteChat = (id: string) => {
    setDeleteOpen(false);
    void deleteSession(id);
    if (currentId === id) {
      stopTurn();
      setCurrentId(null);
      setCanvasOpen(false);
    }
    setConvos((cs) => cs.filter((c) => c.id !== id));
  };

  const go = (v: View) => {
    setView(v);
  };

  const current = convos.find((c) => c.id === currentId);
  const unread = notices.filter((n) => !n.read).length;

  const markRead = () => {
    if (!unread) return;
    setNotices((list) => list.map((n) => ({ ...n, read: true })));
  };

  const signOut = () => {
    void logout();
    resetWorkspace();
    setUser(null);
  };

  if (booting) {
    return (
      <div className="flex h-dvh w-screen items-center justify-center bg-white" aria-busy="true">
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-[#e5e5e4] border-t-[#ea580c]" />
      </div>
    );
  }

  if (!user || !persona) {
    return (
      <LazyMotion features={domAnimation} strict>
        <m.div
          key="login-view"
          initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.99 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.99 }}
          transition={{ duration: 0.28, ease: [0.32, 0.72, 0, 1] }}
          className="h-dvh w-screen overflow-hidden"
        >
          <LoginView onLogin={setUser} />
        </m.div>
      </LazyMotion>
    );
  }

  return (
    <LazyMotion features={domAnimation} strict>
      <div className="relative flex h-dvh w-screen overflow-hidden bg-white text-[#111111]">
        {/* ---------------- 1. Slim Icon Navigation Rail (Hover to Auto-Expand) ---------------- */}
        <aside
          className="group/rail flex h-full w-14 hover:w-52 shrink-0 flex-col justify-between border-r border-[#f0f0ee] bg-white py-3 z-40 select-none transition-[width] duration-300 ease-[cubic-bezier(0.25,1,0.5,1)]"
          aria-label="App Navigation"
        >
          {/* Top Icons & Labels, then the recents list fills the remaining height */}
          <div className="flex min-h-0 flex-1 flex-col gap-1 px-2">
            {/* Sol Sun Logo */}
            <button
              type="button"
              onClick={newChat}
              className="flex h-10 w-full items-center justify-center rounded-[10px] transition-colors hover:bg-[#fafaf9]"
              title="Sol Clean Energy"
            >
              <SolLogo height={20} />
            </button>

            <div className="my-1 h-px w-full bg-[#f0f0ee]" />

            {/* 1. New Chat */}
            <button
              type="button"
              onClick={newChat}
              className="flex h-10 w-full items-center rounded-[10px] text-left text-[#787774] transition-colors hover:bg-[#fafaf9] hover:text-[#ea580c]"
              title="Start a new chat"
            >
              <span className="flex h-10 w-10 shrink-0 items-center justify-center">
                {Icon.plus}
              </span>
              <span className="min-w-0 flex-1 truncate pl-1.5 opacity-0 group-hover/rail:opacity-100 transition-opacity duration-200 text-[13px]">
                New Chat
              </span>
            </button>

            <div className="my-1 h-px w-full bg-[#f0f0ee]" />

            {/* 3. Recents & History: always listed, scrolls when long (titles show when the rail expands) */}
            <div className="flex h-8 shrink-0 items-center text-[#a3a3a3]" aria-hidden="true">
              <span className="flex h-8 w-10 shrink-0 items-center justify-center">{Icon.history}</span>
              <span className="pl-1.5 text-[11px] font-medium uppercase tracking-wide opacity-0 group-hover/rail:opacity-100 transition-opacity duration-200">
                Recents
              </span>
            </div>

            <nav
              aria-label="Recent chats"
              className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden opacity-0 pointer-events-none [scrollbar-width:none] transition-opacity duration-200 group-hover/rail:opacity-100 group-hover/rail:pointer-events-auto group-hover/rail:[scrollbar-width:thin]"
            >
              {convos.length === 0 ? (
                <p className="px-3 py-1 text-[12px] text-[#a3a3a3]">No conversations yet</p>
              ) : (
                <ul className="flex flex-col gap-0.5">
                  {convos.map((c) => {
                    const active = currentId === c.id && view === "chat";
                    return (
                      <li key={c.id}>
                        <div
                          className={`flex h-8 items-center rounded-[8px] transition-colors ${
                            active ? "bg-[#fafaf9] text-[#ea580c] font-medium" : "text-[#787774] hover:bg-[#fafaf9] hover:text-[#111111]"
                          }`}
                        >
                          <button
                            type="button"
                            onClick={() => openChat(c.id)}
                            title={c.title}
                            aria-current={active ? "page" : undefined}
                            className="flex h-8 min-w-0 flex-1 items-center pl-3 text-left"
                          >
                            <span className="min-w-0 flex-1 truncate text-[12px]">{c.title}</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setPendingDelete({ id: c.id, title: c.title });
                              setDeleteOpen(true);
                            }}
                            className="mr-1.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-[6px] text-[#a3a3a3] hover:bg-white hover:text-[#dc2626] transition-colors"
                            title="Delete conversation"
                            aria-label={`Delete conversation ${c.title}`}
                          >
                            {Icon.trash}
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </nav>
          </div>

          {/* Bottom: Overview, then the user profile */}
          <div className="flex shrink-0 flex-col gap-1 px-2 pt-2">
            {/* 4. Overview & Settings */}
            <button
              type="button"
              onClick={() => go("overview")}
              className={`flex h-10 w-full items-center rounded-[10px] text-left transition-colors ${
                view === "overview"
                  ? "bg-[#fafaf9] text-[#ea580c] font-medium"
                  : "text-[#787774] hover:bg-[#fafaf9] hover:text-[#111111]"
              }`}
              title="Overview & Settings"
            >
              <span className="flex h-10 w-10 shrink-0 items-center justify-center">
                {Icon.settings}
              </span>
              <span className="min-w-0 flex-1 truncate pl-1.5 opacity-0 group-hover/rail:opacity-100 transition-opacity duration-200 text-[13px]">
                Overview
              </span>
            </button>

            <Popover
              label="Household Profile"
              placement="right-end"
              className="w-[250px] max-w-[calc(100vw-70px)]"
              trigger={({ open, toggle }) => (
                <button
                  type="button"
                  onClick={toggle}
                  aria-expanded={open}
                  className="flex h-10 w-full items-center rounded-[10px] text-left transition-colors hover:bg-[#fafaf9]"
                  title={persona.location ? `${persona.name} (${persona.location})` : persona.name}
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#111111] text-[10px] font-semibold text-white">
                      {persona.initials}
                    </span>
                  </span>
                  <span className="min-w-0 flex-1 truncate pl-1.5 opacity-0 group-hover/rail:opacity-100 transition-opacity duration-200">
                    <span className="block text-[12px] font-semibold text-[#111111] truncate">{persona.name}</span>
                    <span className="block text-[10px] text-[#787774] truncate">{persona.location ?? user.email}</span>
                  </span>
                </button>
              )}
            >
              {(close) => (
                <div role="menu" aria-label="Account">
                  <div className="px-2.5 pt-1.5 pb-2">
                    <p className="truncate text-[13px] font-semibold text-[#111111]">{user.name}</p>
                    <p className="truncate text-[11px] text-[#787774]">{user.email}</p>
                    <p className="mt-1 truncate text-[11px] text-[#787774]">
                      {[persona.subtitle, persona.location].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <div className="my-1 h-px bg-[#f0f0ee]" />
                  <MenuItem
                    onSelect={() => {
                      close();
                      signOut();
                    }}
                  >
                    <span className="block font-medium text-[#dc2626]">Sign Out</span>
                    <span className="block text-[11px] text-[#787774]">Return to login screen</span>
                  </MenuItem>
                </div>              )}
            </Popover>
          </div>
        </aside>

        {/* ---------------- 3. Main Workspace Area (Adjustable Chat / Map Split) ---------------- */}
        <div ref={workspaceRef} className="relative flex min-w-0 flex-1 h-full overflow-hidden">
          {/* Main / Side Chat Column (Smoothly glides between 100% and splitPercent) */}
          <m.div
            className="relative flex h-full flex-col overflow-hidden bg-white shrink-0 min-w-0"
            animate={{ width: canvasOpen ? `${splitPercent}%` : "100%" }}
            transition={isDragging ? { duration: 0 } : { duration: 0.36, ease: [0.32, 0.72, 0, 1] }}
          >
            {/* Top Workspace Header (Minimal, clean hairline) */}
            <header className="flex h-12 shrink-0 items-center justify-end border-b border-[#f0f0ee] px-4">
              {/* Header Right Actions */}
              <div className="flex items-center gap-1.5">
                {/* Roof Map toggle (moved here from the sidebar) */}
                <button
                  type="button"
                  onClick={toggleCanvas}
                  aria-pressed={canvasOpen}
                  className={`row-btn press flex h-7 w-7 items-center justify-center rounded-[7px] transition-colors ${
                    canvasOpen
                      ? "bg-[#fafaf9] text-[#ea580c]"
                      : "text-[#787774] hover:bg-[#fafaf9] hover:text-[#111111]"
                  }`}
                  title={canvasOpen ? "Close roof map" : "Open roof map"}
                  aria-label={canvasOpen ? "Close roof map" : "Open roof map"}
                >
                  {Icon.map}
                </button>

                {/* Notifications Bell in Top Workspace Header */}
                <Popover
                  label="Notifications"
                  placement="bottom-end"
                  className="w-[280px] max-w-[calc(100vw-70px)]"
                  trigger={({ open, toggle }) => (
                    <button
                      type="button"
                      onClick={() => {
                        toggle();
                        if (!open) markRead();
                      }}
                      className="row-btn press flex h-7 w-7 items-center justify-center rounded-[7px] text-[#787774] hover:bg-[#fafaf9] hover:text-[#111111] transition-colors relative"
                      title={unread ? `${unread} unread notifications` : "Notifications"}
                    >
                      {Icon.bell}
                      {unread > 0 && (
                        <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-[#ea580c]" />
                      )}
                    </button>
                  )}
                >
                  {() => (
                    <div>
                      <p className="px-2.5 pt-1.5 pb-1 text-[12px] font-semibold text-[#111111]">Notifications</p>
                      <ul className="grid gap-1 mt-1">
                        {notices.map((n) => (
                          <li key={n.id} className="flex gap-2 rounded-[8px] px-2.5 py-2 hover:bg-[#fafaf9]">
                            <span
                              className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                                n.read ? "bg-transparent" : "bg-[#ea580c]"
                              }`}
                            />
                            <span>
                              <span className="block text-[12px] leading-snug text-[#111111]">{n.message}</span>
                              <span className="mt-0.5 block text-[10px] text-[#787774]">{n.when}</span>
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </Popover>
              </div>
            </header>

            {/* Chat Views */}
            <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
              {view === "chat" && (
                <ChatView
                  messages={current?.messages ?? []}
                  busy={busy}
                  persona={persona}
                  canvasOpen={canvasOpen}
                  onToggleCanvas={toggleCanvas}
                  onAsk={ask}
                  onStop={stopTurn}
                  lang={lang}
                  onLang={setLang}
                />
              )}
              {view === "overview" && (
                <OverviewView conversationId={currentId} onNewChat={() => setView("chat")} />
              )}
              {view === "saved" && (
                <SavedView conversationId={currentId} onNewChat={() => setView("chat")} />
              )}
            </div>
          </m.div>

          {/* ---------------- Draggable Split Divider ---------------- */}
          {canvasOpen && (
            <div
              onPointerDown={handlePointerDown}
              onDoubleClick={() => setSplitPercent(40)}
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize chat and map panes"
              title="Drag to resize · Double-click to reset (40/60)"
              className="group relative z-30 flex h-full w-3 shrink-0 -mx-1.5 cursor-col-resize items-center justify-center select-none"
            >
              {/* Hairline */}
              <div
                className={`h-full w-[1px] transition-colors ${
                  isDragging ? "bg-[#ea580c]" : "bg-[#f0f0ee] group-hover:bg-[#ea580c]/60"
                }`}
              />

              {/* Floating pill handle */}
              <div
                className={`absolute flex h-8 w-3.5 items-center justify-center rounded-full bg-white shadow-[0_1px_4px_rgba(0,0,0,0.08)] border transition-all ${
                  isDragging
                    ? "border-[#ea580c] scale-110 shadow-[0_2px_8px_rgba(234,88,12,0.2)]"
                    : "border-[#e5e5e4] group-hover:border-[#ea580c]/60 group-hover:scale-105"
                }`}
              >
                <div className="flex flex-col gap-0.5">
                  <span className="h-0.5 w-0.5 rounded-full bg-[#787774]" />
                  <span className="h-0.5 w-0.5 rounded-full bg-[#787774]" />
                  <span className="h-0.5 w-0.5 rounded-full bg-[#787774]" />
                </div>
              </div>
            </div>
          )}

          {/* ---------------- 4. Photo Map Canvas (Adjustable Width from Right) ---------------- */}
          <AnimatePresence initial={false}>
            {canvasOpen && (
              <m.div
                key="photo-map-view"
                initial={reduced ? { opacity: 0 } : { width: "0%", opacity: 0 }}
                animate={reduced ? { opacity: 1 } : { width: `${100 - splitPercent}%`, opacity: 1 }}
                exit={reduced ? { opacity: 0 } : { width: "0%", opacity: 0 }}
                transition={isDragging ? { duration: 0 } : { duration: 0.36, ease: [0.32, 0.72, 0, 1] }}
                className="relative flex h-full shrink-0 overflow-hidden bg-white border-l border-[#f0f0ee] will-change-transform"
              >
                <div className="relative flex h-full w-full min-w-0 flex-col overflow-hidden">
                  <MapCanvas conversationId={currentId} refreshKey={roofTick} onSubmitted={onRoofSubmitted} onClose={toggleCanvas} />
                </div>
              </m.div>
            )}
          </AnimatePresence>
        </div>

        {/* Delete Confirmation Modal */}
        <ConfirmDialog
          open={deleteOpen}
          title="Delete conversation?"
          body={`"${pendingDelete?.title ?? ""}" will be removed.`}
          confirmLabel="Delete"
          onCancel={() => setDeleteOpen(false)}
          onConfirm={() => pendingDelete && deleteChat(pendingDelete.id)}
        />
      </div>
    </LazyMotion>
  );
}

/* ------------------------------------------------------------------ */
/* Map Artifact Card in Chat                                           */
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
      className={`row-btn press flex w-full max-w-[380px] items-center gap-3 rounded-[12px] bg-white p-3 text-left shadow-[0_1px_4px_rgba(0,0,0,0.04)] border border-[#f0f0ee] transition-all ${
        open ? "ring-1.5 ring-[#ea580c] border-transparent" : "hover:bg-[#fafaf9]"
      }`}
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[9px] bg-[#fff7ed] text-[#ea580c]">
        {Icon.map}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-semibold text-[#111111]">
          Roof Map Analysis
        </span>
        <span className="block truncate text-[11px] text-[#787774]">
          {open ? "Active on right map canvas" : "Click to view map"}
        </span>
      </span>
      <span className="text-[#a3a3a3]">{Icon.chevronRight}</span>
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
  persona,
  canvasOpen,
  onToggleCanvas,
  onAsk,
  onStop,
  lang,
  onLang,
}: {
  messages: ChatMsg[];
  busy: boolean;
  persona: Persona;
  canvasOpen: boolean;
  onToggleCanvas: () => void;
  onAsk: (text: string, files?: string[], previews?: (string | null)[], rawFiles?: File[]) => void;
  onStop: () => void;
  lang: LangLabel;
  onLang: (l: LangLabel) => void;
}) {
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<File[]>([]);

  const fileRef = useRef<HTMLInputElement>(null);
  const [addressMode, setAddressMode] = useState(false);
  const autoSendPick = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLDivElement>(null);

  /* React's input types have no onCancel, so listen for the browser's native "cancel"
     (fired when the file picker is dismissed) to drop the pending auto-send. */
  useEffect(() => {
    const input = fileRef.current;
    if (!input) return;
    const onCancel = () => {
      autoSendPick.current = false;
    };
    input.addEventListener("cancel", onCancel);
    return () => input.removeEventListener("cancel", onCancel);
  }, []);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const lastTop = useRef<number | null>(null);

  const reduced = useReducedMotion();
  const hello = useGreeting();
  const empty = messages.length === 0;

  /* Keyboard shortcut: Escape cancels generation if busy */
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && busy) {
        e.preventDefault();
        onStop();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, onStop]);

  /* FLIP Continuity: composer smoothly glides from center to bottom when conversation starts */
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
      duration: 480,
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
    setAddressMode(false);
    const previews = currentFiles.map((f) =>
      f.type.startsWith("image/") ? URL.createObjectURL(f) : null,
    );
    onAsk(
      message,
      currentFiles.map((f) => f.name),
      previews,
      currentFiles,
    );
    setInput("");
    setFiles([]);
    if (textRef.current) textRef.current.style.height = "auto";
  };

  const onKey = (e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const autoResize = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  };

  const onPickFiles = (e: ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files?.length ? Array.from(e.target.files) : [];
    e.target.value = ""; // allow picking the same file again
    const autoSend = autoSendPick.current;
    autoSendPick.current = false;
    if (!picked.length) return;
    if (autoSend) {
      // Opened from the "Attach a bill photo" chip: send straight away
      submit([...files, ...picked], "");
      return;
    }
    setFiles((prev) => [...prev, ...picked]);
  };

  /* "Attach a bill photo" chip: open the file picker instead of sending text */
  const onSuggestion = (n: Suggestion) => {
    if (n.id === "load_photo") {
      if (busy) return;
      autoSendPick.current = true;
      fileRef.current?.click();
      return;
    }
    /* "Type my address" chip: skip the round trip and focus the composer so the user types it */
    if (n.id === "roof_address") {
      setAddressMode(true);
      textRef.current?.focus();
      return;
    }
    submit(undefined, n.text);
  };

  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const imageFiles: File[] = [];
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith("image/")) {
        const file = items[i].getAsFile();
        if (file) imageFiles.push(file);
      }
    }
    if (imageFiles.length > 0) {
      e.preventDefault();
      setFiles((prev) => [...prev, ...imageFiles]);
    }
  };

  const onPill = (p: (typeof PILLS)[number]) => {
    if (p.id === "upload") {
      fileRef.current?.click();
      return;
    }
    if (p.id === "roof") {
      onToggleCanvas();
    }
    submit(undefined, p.prompt);
  };

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-white">
      {/* Spacers above and below the hero + composer group. The bottom one is twice as tall, so the
          group sits above the exact center by a share of the free space (works at every screen height). */}
      {empty && <div className="min-h-3 flex-1" aria-hidden="true" />}

      {/* Scrollable Conversation Body (sized to its content while empty, so the group can center) */}
      <div
        ref={scrollRef}
        className={`flex min-h-0 flex-col overflow-y-auto ${empty ? "flex-initial" : "flex-1"}`}
      >
        {empty ? (
          <>
            {/* Hero Greeting */}
            <div
              className={`mx-auto flex w-full flex-col items-center px-6 text-center select-none ${
                canvasOpen ? "max-w-full" : "max-w-[720px]"
              }`}
            >
              <AnimatedSol size={128} className="-mb-2" />
              <h1 className="mt-4 text-[26px] font-semibold tracking-tight text-[#111111]">
                {hello}, {persona.first}
              </h1>
              <p className="mt-1 text-[13px] text-[#787774]">
                {[persona.subtitle, persona.location].filter(Boolean).join(" · ")}
              </p>
            </div>

            <div className="h-6 shrink-0" aria-hidden="true" />

            {/* Starter Quick Pills directly above the composer */}
            <div
              className={`mx-auto grid w-full gap-2 px-6 pb-3 ${
                canvasOpen ? "grid-cols-2 max-w-full" : "grid-cols-2 sm:grid-cols-4 max-w-[720px]"
              }`}
            >
              {PILLS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => onPill(p)}
                  disabled={busy}
                  className="row-btn press flex h-9 min-w-0 items-center justify-center gap-1.5 rounded-full bg-white px-3 text-[12px] font-medium text-[#111111] shadow-[0_0_0_1px_#e5e5e4,0_1px_3px_rgba(0,0,0,0.03)] hover:bg-[#fafaf9] transition-colors"
                >
                  <span className="shrink-0 text-[#ea580c]">{p.icon}</span>
                  <span className="truncate">{p.label}</span>
                </button>
              ))}
            </div>
          </>
        ) : (
          /* Active Messages Thread */
          <div
            className={`mx-auto flex w-full flex-col gap-4 px-6 py-6 ${
              canvasOpen ? "max-w-full" : "max-w-[720px]"
            }`}
          >
            {messages.map((m) => {
              if (m.from === "user") {
                return (
                  <div key={m.id} className="flex flex-col items-end gap-1.5">
                    {m.files && m.files.length > 0 && (
                      <div className="flex max-w-[85%] flex-wrap justify-end gap-1.5">
                        {m.files.map((name, i) => {
                          const src = m.previews?.[i];
                          return src ? (
                            <img
                              key={`${name}-${i}`}
                              src={src}
                              alt={name}
                              className="max-h-[160px] max-w-[220px] rounded-[12px] border border-[#e5e5e4] object-cover"
                            />
                          ) : (
                            <span
                              key={`${name}-${i}`}
                              className="inline-flex items-center gap-1.5 rounded-[10px] border border-[#e5e5e4] bg-[#fafaf9] px-2.5 py-1.5 text-[11px] text-[#111111]"
                            >
                              <span className="text-[#ea580c]">{Icon.doc}</span>
                              <span className="max-w-[180px] truncate">{name}</span>
                            </span>
                          );
                        })}
                      </div>
                    )}
                    {(m.text !== "Attached files" || !m.files?.length) && (
                      <div className="max-w-[85%] rounded-[14px] bg-[#111111] px-4 py-2.5 text-[13px] text-white">
                        <p className="whitespace-pre-wrap leading-relaxed">{m.text}</p>
                      </div>
                    )}
                  </div>
                );
              }

              return (
                <div key={m.id} className="flex flex-col gap-2.5 text-left">
                  {/* Agent Thinking Steps */}
                  {m.steps.length > 0 && <ThinkingSteps steps={m.steps} done={m.phase === "done"} />}

                  {/* Shown right away, before the first step arrives from the server */}
                  {m.steps.length === 0 && !m.reply && m.phase !== "done" && (
                    <div className="flex items-center gap-2 py-1 text-[12px] text-[#787774]" role="status" aria-live="polite">
                      <span className="inline-flex gap-1" aria-hidden="true">
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#ea580c]" />
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#ea580c] [animation-delay:150ms]" />
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#ea580c] [animation-delay:300ms]" />
                      </span>
                      Working on it…
                    </div>
                  )}

                  {/* Agent Message Content */}
                  {m.reply && (
                    <div className="rounded-[14px] bg-[#fafaf9] p-4 text-[13px] text-[#111111] border border-[#f0f0ee]">
                      <TypedText id={m.id} text={m.reply.text} animate={m.id === messages.at(-1)?.id} />

                      {/* Roof Map Card Preview */}
                      {m.reply.hasMapArtifact && (
                        <div className="mt-3.5">
                          <MapArtifactCard
                            open={canvasOpen}
                            onToggle={onToggleCanvas}
                          />
                        </div>
                      )}

                    </div>
                  )}

                  {/* Follow-up suggestions: outside the answer card, clearly tappable */}
                  {m.reply?.next && m.reply.next.length > 0 && (
                    <div className="flex flex-wrap gap-2 pt-0.5" role="group" aria-label="Suggested replies">
                      {m.reply.next.map((n) => (
                        <button
                          key={n.id}
                          type="button"
                          title={n.hint}
                          disabled={busy}
                          onClick={() => onSuggestion(n)}
                          className="press rounded-full border border-[#ea580c]/35 bg-white px-3.5 py-1.5 text-[13px] font-medium text-[#111111] shadow-[0_1px_3px_rgba(0,0,0,0.06)] transition-colors hover:border-[#ea580c] hover:bg-[#fff7ed] hover:text-[#ea580c] disabled:opacity-50 disabled:hover:border-[#ea580c]/35 disabled:hover:bg-white disabled:hover:text-[#111111]"
                        >
                          {n.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Unified Persistent Composer with FLIP Glide Animation */}
      <div
        ref={composerRef}
        className={`mx-auto w-full shrink-0 px-6 ${empty ? "pb-0" : "pb-3 pt-2"} ${
          canvasOpen ? "max-w-full" : "max-w-[720px]"
        }`}
      >
        <div className="rounded-[16px] bg-white px-3 pt-2 pb-1.5 border border-[#e5e5e4] shadow-[0_4px_20px_rgba(0,0,0,0.04)] focus-within:border-[#ea580c] focus-within:shadow-[0_4px_24px_rgba(234,88,12,0.08)] transition-all">
          {/* Attached Files List */}
          {files.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1.5 pb-1">
              {files.map((f, i) => (
                <span
                  key={`${f.name}-${i}`}
                  className="inline-flex items-center gap-1.5 rounded-[8px] bg-[#fafaf9] py-1 pr-1.5 pl-2 text-[11px] border border-[#f0f0ee]"
                >
                  <FileThumb file={f} />
                  <span className="max-w-[140px] truncate text-[#111111]">{f.name}</span>
                  <button
                    type="button"
                    onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))}
                    className="flex h-4 w-4 items-center justify-center rounded-full text-[#787774] hover:text-[#ea580c]"
                    title={`Remove ${f.name}`}
                  >
                    {Icon.close}
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* Textarea */}
          <textarea
            ref={textRef}
            rows={1}
            value={input}
            onChange={autoResize}
            onKeyDown={onKey}
            onPaste={onPaste}
            placeholder={
              addressMode
                ? "Type your address, e.g. 123 Rizal St, Pasig…"
                : empty
                  ? "Ask about your roof, monthly bill, or solar options…"
                  : "Reply to Sol…"
            }
            className="w-full resize-none bg-transparent px-1 py-1 text-[14px] leading-relaxed text-[#111111] placeholder-[#a3a3a3] outline-none"
          />

          {/* Bottom Bar Actions */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1">
              <input
                ref={fileRef}
                type="file"
                multiple
                accept="image/*,.pdf"
                className="hidden"
                onChange={onPickFiles}
              />
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="flex h-8 w-8 items-center justify-center rounded-[8px] text-[#787774] hover:bg-[#fafaf9] hover:text-[#ea580c] transition-colors"
                title="Upload bill or photo"
              >
                {Icon.upload}
              </button>

              {/* Reply language: Auto follows the user, Taglish forces a Tagalog-English mix */}
              <Popover
                label="Reply language"
                placement="top-start"
                className="w-[170px]"
                trigger={({ open, toggle }) => (
                  <button
                    type="button"
                    onClick={toggle}
                    aria-expanded={open}
                    title="Reply language"
                    className="flex h-8 items-center gap-1 rounded-[8px] px-2 text-[12px] font-medium text-[#787774] hover:bg-[#fafaf9] hover:text-[#ea580c] transition-colors"
                  >
                    {lang} {Icon.chevronDown}
                  </button>
                )}
              >
                {(close) => (
                  <div role="menu" aria-label="Reply language">
                    {(Object.keys(LANGS) as LangLabel[]).map((l) => (
                      <MenuItem
                        key={l}
                        checked={lang === l}
                        onSelect={() => {
                          onLang(l);
                          close();
                        }}
                      >
                        {l === "Auto" ? "Auto-detect" : l}
                      </MenuItem>
                    ))}
                  </div>
                )}
              </Popover>
            </div>

            {busy ? (
              <button
                type="button"
                onClick={onStop}
                className="press flex h-8 w-8 items-center justify-center rounded-[9px] bg-[#111111] text-white hover:bg-[#ea580c] transition-colors shadow-sm"
                title="Stop generating (Esc)"
                aria-label="Stop generating"
              >
                {Icon.stop}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => submit()}
                disabled={!input.trim() && !files.length}
                className="press flex h-8 w-8 items-center justify-center rounded-[9px] bg-[#111111] text-white hover:bg-[#262626] disabled:bg-[#f0f0ee] disabled:text-[#a3a3a3] transition-colors"
                title="Send message"
                aria-label="Send message"
              >
                {Icon.send}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Bottom spacer: twice the weight of the top one */}
      {empty && <div className="flex-[2]" aria-hidden="true" />}
    </div>
  );
}

