import { useState, type FormEvent } from "react";
import { AnimatePresence, LazyMotion, domAnimation, m, type Variants } from "framer-motion";
import { SolLogo } from "./SolLogo";
import { ApiError, login, signup, type User } from "../lib/api";
import { Login3DPlaceholder } from "./Login3DPlaceholder";

interface LoginViewProps {
  onLogin: (user: User) => void;
}

type AuthMode = "signin" | "signup";

/* ------------------------------------------------------------------ */
/* Framer Motion Animation Variants (defined outside component)       */
/* ------------------------------------------------------------------ */

const tabContentVariants: Variants = {
  initial: { opacity: 0, y: 6 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] as const },
  },
  exit: {
    opacity: 0,
    y: -6,
    transition: { duration: 0.14, ease: [0.16, 1, 0.3, 1] as const },
  },
};

const alertVariants: Variants = {
  initial: { opacity: 0, y: -4, scale: 0.98 },
  animate: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.16, ease: [0.16, 1, 0.3, 1] as const },
  },
  exit: {
    opacity: 0,
    y: -4,
    scale: 0.98,
    transition: { duration: 0.12, ease: [0.16, 1, 0.3, 1] as const },
  },
};

export function LoginView({ onLogin }: LoginViewProps) {
  const [mode, setMode] = useState<AuthMode>("signin");

  // Form Fields
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  // UI States
  const [error, setError] = useState<string | null>(null);
  const [infoNotice, setInfoNotice] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const resetErrors = () => {
    if (error) setError(null);
    if (infoNotice) setInfoNotice(null);
  };

  const handleModeSwitch = (newMode: AuthMode) => {
    resetErrors();
    setMode(newMode);
  };

  // Validation
  const validateEmail = (val: string): boolean => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val.trim());
  };

  const submit = async (action: () => Promise<User>) => {
    setIsSubmitting(true);
    try {
      onLogin(await action());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setIsSubmitting(false);
    }
  };

  const handleSignInSubmit = (e: FormEvent) => {
    e.preventDefault();
    resetErrors();

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setError("Please enter your email address.");
      return;
    }
    if (!validateEmail(trimmedEmail)) {
      setError("Please enter a valid email address.");
      return;
    }
    if (!password) {
      setError("Please enter your password.");
      return;
    }

    void submit(() => login(trimmedEmail, password));
  };

  const handleSignUpSubmit = (e: FormEvent) => {
    e.preventDefault();
    resetErrors();

    const trimmedName = name.trim();
    const trimmedEmail = email.trim();

    if (!trimmedName) {
      setError("Please enter your full name.");
      return;
    }
    if (!trimmedEmail) {
      setError("Please enter your email address.");
      return;
    }
    if (!validateEmail(trimmedEmail)) {
      setError("Please enter a valid email address.");
      return;
    }
    if (!password) {
      setError("Please create a password.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match. Please verify and try again.");
      return;
    }

    void submit(() => signup(trimmedName, trimmedEmail, password));
  };

  return (
    <LazyMotion features={domAnimation}>
      <div className="relative flex h-dvh w-screen overflow-hidden bg-white text-[#111111]">
        {/* ---------------- Left Pane: Minimalist Auth Form ---------------- */}
        <div className="relative flex h-full w-full lg:w-1/2 flex-col justify-between overflow-y-auto lg:overflow-hidden px-6 py-6 sm:px-12 md:px-16 lg:px-20 select-none">
          {/* Top Bar: Sol Logo Mark */}
          <div className="flex items-center gap-2.5">
            <SolLogo height={40} />
          </div>

          {/* Center Form Container */}
          <div className="mx-auto my-auto w-full max-w-[380px] py-2">
            <AnimatePresence mode="wait">
              {mode === "signin" ? (
                /* =================== SIGN IN VIEW =================== */
                <m.div
                  key="signin-view"
                  variants={tabContentVariants}
                  initial="initial"
                  animate="animate"
                  exit="exit"
                >
                  <div className="text-center">
                    <h1 className="text-[24px] font-bold tracking-tight text-[#111111]">
                      Welcome Back!
                    </h1>
                    <p className="mt-1 text-[13px] text-[#787774]">
                      Sign in to continue where you left off.
                    </p>
                  </div>

                  {/* Feedback Banners */}
                  <AnimatePresence>
                    {error && (
                      <m.div
                        variants={alertVariants}
                        initial="initial"
                        animate="animate"
                        exit="exit"
                        className="mt-3.5 rounded-[8px] bg-[#FDEBEC] px-3.5 py-2 text-[12px] font-medium text-[#9F2F2D] border border-[#FCA5A5] text-center"
                      >
                        {error}
                      </m.div>
                    )}
                    {infoNotice && (
                      <m.div
                        variants={alertVariants}
                        initial="initial"
                        animate="animate"
                        exit="exit"
                        className="mt-3.5 rounded-[8px] bg-[#EDF3EC] px-3.5 py-2 text-[12px] font-medium text-[#346538] border border-[#D5E5D4] text-center"
                      >
                        {infoNotice}
                      </m.div>
                    )}
                  </AnimatePresence>

                  {/* Sign In Form */}
                  <form
                    onSubmit={handleSignInSubmit}
                    className="mt-5 flex flex-col gap-3 text-left"
                    noValidate
                  >
                    <div>
                      <label
                        htmlFor="signin-email"
                        className="block text-[12px] font-medium text-[#111111] mb-1"
                      >
                        Email
                      </label>
                      <input
                        id="signin-email"
                        type="email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => {
                          setEmail(e.target.value);
                          resetErrors();
                        }}
                        placeholder="you@example.com"
                        className="w-full h-10 rounded-[8px] bg-white px-3.5 py-2 text-[13px] text-[#111111] placeholder-[#A3A3A3] border border-[#EAEAEA] outline-none shadow-[0_1px_2px_rgba(0,0,0,0.02)] transition-colors focus:border-[#111111] focus:ring-1 focus:ring-[#111111]"
                      />
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label
                          htmlFor="signin-password"
                          className="block text-[12px] font-medium text-[#111111]"
                        >
                          Password
                        </label>
                      </div>
                      <input
                        id="signin-password"
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        onChange={(e) => {
                          setPassword(e.target.value);
                          resetErrors();
                        }}
                        placeholder="••••••••"
                        className="w-full h-10 rounded-[8px] bg-white px-3.5 py-2 text-[13px] text-[#111111] placeholder-[#A3A3A3] border border-[#EAEAEA] outline-none shadow-[0_1px_2px_rgba(0,0,0,0.02)] transition-colors focus:border-[#111111] focus:ring-1 focus:ring-[#111111]"
                      />
                    </div>

                    {/* Minimalist Primary Button */}
                    <m.button
                      type="submit"
                      disabled={isSubmitting}
                      whileTap={{ scale: 0.98 }}
                      className="mt-1 flex h-10 w-full items-center justify-center rounded-[8px] bg-[#ea580c] text-[13px] font-semibold text-white shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-colors hover:bg-[#c2410c] disabled:opacity-60 cursor-pointer"
                    >
                      {isSubmitting ? "Signing In…" : "Sign In"}
                    </m.button>
                  </form>
                </m.div>
              ) : (
                /* =================== SIGN UP VIEW =================== */
                <m.div
                  key="signup-view"
                  variants={tabContentVariants}
                  initial="initial"
                  animate="animate"
                  exit="exit"
                >
                  <div className="text-center">
                    <h1 className="text-[24px] font-bold tracking-tight text-[#111111]">
                      Create an Account
                    </h1>
                    <p className="mt-1 text-[13px] text-[#787774]">
                      Join Sol to plan solar for your home.
                    </p>
                  </div>

                  {/* Feedback Banners */}
                  <AnimatePresence>
                    {error && (
                      <m.div
                        variants={alertVariants}
                        initial="initial"
                        animate="animate"
                        exit="exit"
                        className="mt-3 rounded-[8px] bg-[#FDEBEC] px-3.5 py-2 text-[12px] font-medium text-[#9F2F2D] border border-[#FCA5A5] text-center"
                      >
                        {error}
                      </m.div>
                    )}
                  </AnimatePresence>

                  {/* Sign Up Form (Compact and Non-scrollable) */}
                  <form
                    onSubmit={handleSignUpSubmit}
                    className="mt-4 flex flex-col gap-2.5 text-left"
                    noValidate
                  >
                    <div>
                      <label
                        htmlFor="signup-name"
                        className="block text-[12px] font-medium text-[#111111] mb-1"
                      >
                        Full Name
                      </label>
                      <input
                        id="signup-name"
                        type="text"
                        autoComplete="name"
                        value={name}
                        onChange={(e) => {
                          setName(e.target.value);
                          resetErrors();
                        }}
                        placeholder="Your name"
                        className="w-full h-9 rounded-[8px] bg-white px-3 py-1.5 text-[13px] text-[#111111] placeholder-[#A3A3A3] border border-[#EAEAEA] outline-none shadow-[0_1px_2px_rgba(0,0,0,0.02)] transition-colors focus:border-[#111111] focus:ring-1 focus:ring-[#111111]"
                      />
                    </div>

                    <div>
                      <label
                        htmlFor="signup-email"
                        className="block text-[12px] font-medium text-[#111111] mb-1"
                      >
                        Email
                      </label>
                      <input
                        id="signup-email"
                        type="email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => {
                          setEmail(e.target.value);
                          resetErrors();
                        }}
                        placeholder="you@example.com"
                        className="w-full h-9 rounded-[8px] bg-white px-3 py-1.5 text-[13px] text-[#111111] placeholder-[#A3A3A3] border border-[#EAEAEA] outline-none shadow-[0_1px_2px_rgba(0,0,0,0.02)] transition-colors focus:border-[#111111] focus:ring-1 focus:ring-[#111111]"
                      />
                    </div>

                    <div>
                      <label
                        htmlFor="signup-password"
                        className="block text-[12px] font-medium text-[#111111] mb-1"
                      >
                        Password
                      </label>
                      <input
                        id="signup-password"
                        type="password"
                        autoComplete="new-password"
                        value={password}
                        onChange={(e) => {
                          setPassword(e.target.value);
                          resetErrors();
                        }}
                        placeholder="At least 8 characters"
                        className="w-full h-9 rounded-[8px] bg-white px-3 py-1.5 text-[13px] text-[#111111] placeholder-[#A3A3A3] border border-[#EAEAEA] outline-none shadow-[0_1px_2px_rgba(0,0,0,0.02)] transition-colors focus:border-[#111111] focus:ring-1 focus:ring-[#111111]"
                      />
                    </div>

                    <div>
                      <label
                        htmlFor="signup-confirm-password"
                        className="block text-[12px] font-medium text-[#111111] mb-1"
                      >
                        Confirm Password
                      </label>
                      <input
                        id="signup-confirm-password"
                        type="password"
                        autoComplete="new-password"
                        value={confirmPassword}
                        onChange={(e) => {
                          setConfirmPassword(e.target.value);
                          resetErrors();
                        }}
                        placeholder="Re-enter password"
                        className="w-full h-9 rounded-[8px] bg-white px-3 py-1.5 text-[13px] text-[#111111] placeholder-[#A3A3A3] border border-[#EAEAEA] outline-none shadow-[0_1px_2px_rgba(0,0,0,0.02)] transition-colors focus:border-[#111111] focus:ring-1 focus:ring-[#111111]"
                      />
                    </div>

                    {/* Minimalist Primary Button */}
                    <m.button
                      type="submit"
                      disabled={isSubmitting}
                      whileTap={{ scale: 0.98 }}
                      className="mt-1 flex h-10 w-full items-center justify-center rounded-[8px] bg-[#ea580c] text-[13px] font-semibold text-white shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-colors hover:bg-[#c2410c] disabled:opacity-60 cursor-pointer"
                    >
                      {isSubmitting ? "Creating Account…" : "Create Account"}
                    </m.button>
                  </form>
                </m.div>
              )}
            </AnimatePresence>

            {/* Bottom Switcher Helper */}
            <div className="mt-3.5 text-center text-[12px] text-[#787774]">
              {mode === "signin" ? (
                <p>
                  New to Sol?{" "}
                  <button
                    type="button"
                    onClick={() => handleModeSwitch("signup")}
                    className="font-semibold text-[#ea580c] hover:underline cursor-pointer"
                  >
                    Create an account
                  </button>
                </p>
              ) : (
                <p>
                  Already have an account?{" "}
                  <button
                    type="button"
                    onClick={() => handleModeSwitch("signin")}
                    className="font-semibold text-[#ea580c] hover:underline cursor-pointer"
                  >
                    Sign in
                  </button>
                </p>
              )}
            </div>
          </div>

          {/* Spacer to balance bottom */}
          <div className="h-4" />
        </div>

        {/* ---------------- Right Pane: 3D Presentation Viewport ---------------- */}
        <div className="hidden lg:block lg:w-1/2 h-full">
          <Login3DPlaceholder />
        </div>
      </div>
    </LazyMotion>
  );
}
