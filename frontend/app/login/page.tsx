"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, FileText, ShieldCheck, Sparkles } from "lucide-react";
import { SignInPage } from "@/components/ui/sign-in";
import { errorText } from "@/lib/utils";
import { useLoginMutation } from "@/store/api";
import { sessionStarted } from "@/store/authSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

function Side() {
  const rows = [
    { raw: "20 x 3/4 cu elbows comp", code: "CU-EL90-NORT-22-COMP", ok: true },
    { raw: "PTFE tape x5", code: "PTFE-12-12-P10", ok: true },
    { raw: "15mm iso valve blue", code: "Brand not stated", ok: false },
  ];
  return (
    <div className="flex h-full flex-col justify-between p-10">
      <div className="flex items-center gap-2 text-lg font-semibold"><FileText className="h-5 w-5" /> OrderDesk</div>
      <div className="mx-auto w-full max-w-md space-y-3">
        <p className="text-sm font-medium">From a customer email</p>
        {rows.map((r) => (
          <div key={r.raw} className="flex items-center justify-between gap-3 rounded-2xl border border-border bg-white/90 px-4 py-3 shadow-sm">
            <span className="font-mono text-sm">{r.raw}</span>
            <span className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${r.ok ? "border-ok-border bg-ok-bg" : "border-warn-border bg-warn-bg"}`}>
              {r.ok ? <CheckCircle2 className="h-3.5 w-3.5 text-green-600" /> : <Sparkles className="h-3.5 w-3.5 text-amber-600" />}
              {r.code}
            </span>
          </div>
        ))}
      </div>
      <div className="flex items-start gap-3 text-sm">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" />
        <p>Reads messy orders, matches every line to the catalogue, prices it with your rules, and only asks a person about the lines it isn&apos;t sure of.</p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const status = useAppSelector((s) => s.auth.status);
  const [login, { isLoading }] = useLoginMutation();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "signed_in") router.replace("/inbox");
  }, [status, router]);

  async function onSignIn(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const email = String(f.get("email") ?? "").trim();
    const password = String(f.get("password") ?? "");
    if (!email || !password) return setError("Enter your email and password.");
    setError(null);
    try {
      const session = await login({ email, password }).unwrap();
      dispatch(sessionStarted(session));
      router.replace(session.user.must_change_password ? "/change-password" : "/inbox");
    } catch (err) {
      const s = (err as { status?: number }).status;
      setError(s === 401 ? "Wrong email or password." : s === 429 ? "Too many attempts. Wait 15 minutes and try again." : errorText(err));
    }
  }

  return (
    <SignInPage
      title={<span className="font-light tracking-tighter">Welcome to <span className="font-semibold">OrderDesk</span></span>}
      description="Sign in to review incoming orders."
      side={<Side />}
      error={error}
      busy={isLoading}
      onSignIn={onSignIn}
      onResetPassword={() => setError("Ask your OrderDesk admin to reset your password.")}
    />
  );
}
