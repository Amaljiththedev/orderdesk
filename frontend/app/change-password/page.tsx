"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, Loader2 } from "lucide-react";
import { useSessionBoot } from "@/components/session";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { errorText } from "@/lib/utils";
import { useChangePasswordMutation } from "@/store/api";
import { sessionStarted } from "@/store/authSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

export default function ChangePasswordPage() {
  const status = useSessionBoot();
  const user = useAppSelector((s) => s.auth.user);
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [change, { isLoading }] = useChangePasswordMutation();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { if (status === "signed_out") router.replace("/login"); }, [status, router]);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const current = String(f.get("current") ?? "");
    const next = String(f.get("next") ?? "");
    if (next.length < 12) return setError("The new password needs at least 12 characters.");
    if (next !== f.get("again")) return setError("The two new passwords don't match.");
    setError(null);
    try {
      const session = await change({ current_password: current, new_password: next }).unwrap();
      dispatch(sessionStarted(session));
      router.replace("/inbox");
    } catch (err) {
      setError(errorText(err));
    }
  }

  if (status !== "signed_in") {
    return <div className="flex min-h-[100dvh] items-center justify-center"><Loader2 className="h-5 w-5 animate-spin" /></div>;
  }
  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-neutral-50 p-6">
      <Card className="w-full max-w-md">
        <CardBody className="space-y-5 p-8">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-white"><KeyRound className="h-5 w-5" /></div>
          <div>
            <h1 className="text-2xl font-semibold">{user?.must_change_password ? "Choose your own password" : "Change password"}</h1>
            <p className="mt-1 text-sm">
              {user?.must_change_password ? "Your account was created with a temporary password. " : ""}
              Use at least 12 characters. A long phrase is easiest to remember. Other sessions will be signed out.
            </p>
          </div>
          <form className="space-y-4" onSubmit={onSubmit}>
            <div><Label htmlFor="current">Current password</Label><Input id="current" name="current" type="password" autoComplete="current-password" required /></div>
            <div><Label htmlFor="next">New password</Label><Input id="next" name="next" type="password" autoComplete="new-password" minLength={12} required /></div>
            <div><Label htmlFor="again">New password again</Label><Input id="again" name="again" type="password" autoComplete="new-password" required /></div>
            {error && <p role="alert" className="rounded-xl border border-bad-border bg-bad-bg px-3 py-2 text-sm">{error}</p>}
            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading && <Loader2 className="h-4 w-4 animate-spin" />} Save password
            </Button>
          </form>
        </CardBody>
      </Card>
    </div>
  );
}
