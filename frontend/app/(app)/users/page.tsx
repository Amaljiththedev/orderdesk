"use client";
import { useState } from "react";
import { Loader2, UserPlus } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import type { User } from "@/lib/types";
import { errorText, timeAgo } from "@/lib/utils";
import { useCreateUserMutation, useUpdateUserMutation, useUsersQuery } from "@/store/api";
import { useAppSelector } from "@/store/hooks";

export default function UsersPage() {
  const { data, isLoading, isError, error, refetch } = useUsersQuery();
  const [adding, setAdding] = useState(false);
  return (
    <div>
      <PageHeader title="Users" text="There is no public sign-up. Add people here; they choose their own password on first sign-in."
        actions={<Button onClick={() => setAdding((v) => !v)}><UserPlus className="h-4 w-4" /> Add user</Button>} />
      <div className="space-y-6 p-6 md:p-8">
        {adding && <AddUser onDone={() => setAdding(false)} />}
        <Card>
          {isLoading ? <div className="space-y-2 p-4">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
            : isError ? <div className="p-4"><ErrorState text={errorText(error, "Couldn't load users.")} onRetry={refetch} /></div>
            : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-border text-left text-xs font-medium uppercase tracking-wide">
                    <th className="px-4 py-3">Name</th><th className="px-4 py-3">Role</th><th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Last sign-in</th><th className="px-4 py-3" />
                  </tr></thead>
                  <tbody>{data?.map((u) => <UserRow key={u.id} u={u} />)}</tbody>
                </table>
              </div>
            )}
        </Card>
      </div>
    </div>
  );
}

function UserRow({ u }: { u: User }) {
  const me = useAppSelector((s) => s.auth.user);
  const [update, { isLoading }] = useUpdateUserMutation();
  const toast = useToast();
  const self = me?.id === u.id;

  async function change(body: { role?: string; is_active?: boolean }, msg: string) {
    try { await update({ id: u.id, ...body }).unwrap(); toast(msg); }
    catch (err) { toast(errorText(err), "bad"); }
  }

  return (
    <tr className="border-b border-border last:border-0">
      <td className="px-4 py-3"><div className="font-medium">{u.full_name || "—"}{self && " (you)"}</div><div className="text-xs">{u.email}</div></td>
      <td className="px-4 py-3">
        <select aria-label={`Role for ${u.email}`} value={u.role} disabled={isLoading || self}
          onChange={(e) => change({ role: e.target.value }, `${u.email} is now ${e.target.value}. Their sessions were signed out.`)}
          className="h-9 rounded-lg border border-border bg-white px-2 text-sm">
          <option value="reviewer">Reviewer</option>
          <option value="admin">Admin</option>
        </select>
      </td>
      <td className="px-4 py-3">
        {!u.is_active ? <Badge tone="neutral">Deactivated</Badge> : u.must_change_password ? <Badge tone="warn">Must set password</Badge> : <Badge tone="ok">Active</Badge>}
      </td>
      <td className="px-4 py-3">{u.last_login_at ? timeAgo(u.last_login_at) : "Never"}</td>
      <td className="px-4 py-3 text-right">
        {!self && (
          <Button size="sm" variant={u.is_active ? "danger" : "outline"} disabled={isLoading}
            onClick={() => change({ is_active: !u.is_active }, u.is_active ? `${u.email} deactivated and signed out.` : `${u.email} reactivated.`)}>
            {isLoading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}{u.is_active ? "Deactivate" : "Reactivate"}
          </Button>
        )}
      </td>
    </tr>
  );
}

function AddUser({ onDone }: { onDone: () => void }) {
  const [create, { isLoading }] = useCreateUserMutation();
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setError(null);
    try {
      const u = await create({
        email: String(f.get("email")).trim(), full_name: String(f.get("name")).trim(),
        role: String(f.get("role")), temporary_password: String(f.get("password")),
      }).unwrap();
      toast(`${u.email} added. Give them the temporary password; they'll replace it on first sign-in.`);
      onDone();
    } catch (err) { setError(errorText(err)); }
  }

  return (
    <Card>
      <CardHeader><CardTitle>Add a user</CardTitle></CardHeader>
      <CardBody>
        <form onSubmit={onSubmit} className="grid gap-4 md:grid-cols-2">
          <div><Label htmlFor="name">Full name</Label><Input id="name" name="name" required placeholder="Sam Patel" /></div>
          <div><Label htmlFor="email">Email</Label><Input id="email" name="email" type="email" required placeholder="sam@company.co.uk" /></div>
          <div>
            <Label htmlFor="role">Role</Label>
            <select id="role" name="role" defaultValue="reviewer" className="h-10 w-full rounded-xl border border-border bg-white px-3 text-sm">
              <option value="reviewer">Reviewer: reviews and fixes orders</option>
              <option value="admin">Admin: also metrics and users</option>
            </select>
          </div>
          <div><Label htmlFor="password">Temporary password (12+ characters)</Label><Input id="password" name="password" type="text" minLength={12} required autoComplete="off" /></div>
          {error && <p role="alert" className="rounded-xl border border-bad-border bg-bad-bg px-3 py-2 text-sm md:col-span-2">{error}</p>}
          <div className="flex gap-2 md:col-span-2">
            <Button type="submit" disabled={isLoading}>{isLoading && <Loader2 className="h-4 w-4 animate-spin" />} Add user</Button>
            <Button variant="outline" onClick={onDone}>Cancel</Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}
