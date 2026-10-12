"use client";
// Adapted from the provided sign-in reference: same two-column layout, glass inputs and entrance
// animations, but light only with black text. No Google sign-in, testimonials or "create account":
// OrderDesk has no public sign-up (admins create users).
import React, { useState } from "react";
import { Eye, EyeOff, Loader2 } from "lucide-react";

interface SignInPageProps {
  title?: React.ReactNode;
  description?: React.ReactNode;
  side?: React.ReactNode;
  error?: string | null;
  busy?: boolean;
  onSignIn?: (event: React.FormEvent<HTMLFormElement>) => void;
  onResetPassword?: () => void;
}

const GlassInputWrapper = ({ children }: { children: React.ReactNode }) => (
  <div className="rounded-2xl border border-border bg-neutral-50 transition-colors focus-within:border-violet-400 focus-within:bg-violet-50/60">
    {children}
  </div>
);

export const SignInPage: React.FC<SignInPageProps> = ({
  title = <span className="font-light tracking-tighter text-foreground">Welcome</span>,
  description = "Sign in to continue",
  side,
  error,
  busy,
  onSignIn,
  onResetPassword,
}) => {
  const [showPassword, setShowPassword] = useState(false);

  return (
    <div className="flex min-h-[100dvh] w-full flex-col bg-white text-foreground md:flex-row">
      <section className="flex flex-1 items-center justify-center p-8">
        <div className="w-full max-w-md">
          <div className="flex flex-col gap-6">
            <h1 className="animate-element animate-delay-100 text-4xl font-semibold leading-tight md:text-5xl">{title}</h1>
            <p className="animate-element animate-delay-200 text-foreground">{description}</p>

            <form className="space-y-5" onSubmit={onSignIn} noValidate>
              <div className="animate-element animate-delay-300">
                <label htmlFor="email" className="text-sm font-medium">Email address</label>
                <GlassInputWrapper>
                  <input id="email" name="email" type="email" autoComplete="username" required autoFocus
                    placeholder="you@company.co.uk"
                    className="w-full rounded-2xl bg-transparent p-4 text-sm placeholder:text-neutral-500 focus:outline-none" />
                </GlassInputWrapper>
              </div>

              <div className="animate-element animate-delay-400">
                <label htmlFor="password" className="text-sm font-medium">Password</label>
                <GlassInputWrapper>
                  <div className="relative">
                    <input id="password" name="password" type={showPassword ? "text" : "password"}
                      autoComplete="current-password" required placeholder="Your password"
                      className="w-full rounded-2xl bg-transparent p-4 pr-12 text-sm placeholder:text-neutral-500 focus:outline-none" />
                    <button type="button" onClick={() => setShowPassword(!showPassword)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      className="absolute inset-y-0 right-3 flex items-center">
                      {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                    </button>
                  </div>
                </GlassInputWrapper>
              </div>

              {error && (
                <p role="alert" className="rounded-xl border border-bad-border bg-bad-bg px-4 py-3 text-sm">{error}</p>
              )}

              <div className="animate-element animate-delay-500 flex items-center justify-end text-sm">
                <a href="#" onClick={(e) => { e.preventDefault(); onResetPassword?.(); }}
                  className="text-foreground underline-offset-4 hover:underline">Forgot password?</a>
              </div>

              <button type="submit" disabled={busy}
                className="animate-element animate-delay-600 flex w-full items-center justify-center gap-2 rounded-2xl bg-primary py-4 font-medium text-primary-foreground transition-colors hover:bg-neutral-800 disabled:opacity-60">
                {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                Sign in
              </button>
            </form>

            <p className="animate-element animate-delay-700 text-center text-sm">
              No account? Ask your OrderDesk admin to add you.
            </p>
          </div>
        </div>
      </section>

      {side && (
        <section className="relative hidden flex-1 p-4 md:block">
          <div className="animate-slide-right animate-delay-300 absolute inset-4 overflow-hidden rounded-3xl border border-border bg-gradient-to-br from-violet-50 via-white to-amber-50">
            {side}
          </div>
        </section>
      )}
    </div>
  );
};
