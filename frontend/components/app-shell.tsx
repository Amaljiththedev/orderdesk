"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { BarChart3, FileText, Inbox, Loader2, LogOut, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSessionBoot } from "@/components/session";
import { api, useLogoutMutation } from "@/store/api";
import { signedOut } from "@/store/authSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

const NAV = [
  { href: "/inbox", label: "Inbox", icon: Inbox, admin: false },
  { href: "/metrics", label: "Metrics", icon: BarChart3, admin: true },
  { href: "/users", label: "Users", icon: Users, admin: true },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const status = useSessionBoot();
  const user = useAppSelector((s) => s.auth.user);
  const router = useRouter();
  const path = usePathname();
  const dispatch = useAppDispatch();
  const [logout] = useLogoutMutation();

  useEffect(() => {
    if (status === "signed_out") router.replace("/login");
    else if (status === "signed_in" && user?.must_change_password) router.replace("/change-password");
  }, [status, user, router]);

  const adminOnly = NAV.find((n) => path.startsWith(n.href))?.admin;
  if (status !== "signed_in" || !user || user.must_change_password) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center gap-2 text-sm">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading your session…
      </div>
    );
  }

  async function onLogout() {
    try { await logout().unwrap(); } catch { /* signed out locally anyway */ }
    dispatch(signedOut());
    dispatch(api.util.resetApiState());
    router.replace("/login");
  }

  return (
    <div className="flex min-h-[100dvh] bg-white">
      <aside className="sticky top-0 hidden h-[100dvh] w-60 shrink-0 flex-col border-r border-border bg-neutral-50/60 p-4 md:flex">
        <Link href="/inbox" className="mb-8 flex items-center gap-2 px-2 text-lg font-semibold">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-white"><FileText className="h-4 w-4" /></span>
          OrderDesk
        </Link>
        <nav className="flex flex-1 flex-col gap-1">
          {NAV.filter((n) => !n.admin || user.role === "admin").map((n) => {
            const active = path.startsWith(n.href) || (n.href === "/inbox" && path.startsWith("/orders"));
            return (
              <Link key={n.href} href={n.href}
                className={cn("flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium",
                  active ? "border border-border bg-white shadow-sm" : "hover:bg-white")}>
                <n.icon className="h-4 w-4" /> {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="rounded-2xl border border-border bg-white p-3">
          <p className="truncate text-sm font-medium">{user.full_name || user.email}</p>
          <p className="truncate text-xs">{user.email} · {user.role}</p>
          <button onClick={onLogout} className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-border py-1.5 text-sm hover:bg-secondary">
            <LogOut className="h-3.5 w-3.5" /> Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* mobile top bar */}
        <header className="flex items-center justify-between border-b border-border px-4 py-3 md:hidden">
          <span className="font-semibold">OrderDesk</span>
          <div className="flex gap-3 text-sm">
            {NAV.filter((n) => !n.admin || user.role === "admin").map((n) => <Link key={n.href} href={n.href}>{n.label}</Link>)}
            <button onClick={onLogout}>Sign out</button>
          </div>
        </header>
        <main className="min-w-0 flex-1">
          {adminOnly && user.role !== "admin" ? (
            <div className="p-10 text-sm">This page is for admins only.</div>
          ) : children}
        </main>
      </div>
    </div>
  );
}

export function PageHeader({ title, text, actions }: { title: React.ReactNode; text?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border px-6 py-5 md:px-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {text && <p className="mt-1 text-sm">{text}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
