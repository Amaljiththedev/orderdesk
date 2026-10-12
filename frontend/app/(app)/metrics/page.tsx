"use client";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { FlaskConical, Info, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Tabs } from "@/components/ui/tabs";
import type { Metrics } from "@/lib/types";
import { errorText, money, pct } from "@/lib/utils";
import { useMetricsQuery } from "@/store/api";

// categorical slots 1-2 of the validated reference palette (light surface, CVD-safe, >= 3:1)
const AUTO = "#2a78d6";
const REVIEW = "#eb6834";

export default function MetricsPage() {
  const [days, setDays] = useState<"7" | "30" | "90">("30");
  const { data, isLoading, isError, error, refetch, isFetching } = useMetricsQuery(Number(days));

  return (
    <div>
      <PageHeader
        title="Metrics"
        text="How much went through untouched, how fast, how accurate and what it cost."
        actions={<>
          <Tabs value={days} onChange={setDays} items={[{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }, { value: "90", label: "90 days" }]} />
          <Button variant="outline" onClick={() => refetch()} aria-label="Refresh"><RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} /></Button>
        </>}
      />
      <div className="space-y-6 p-6 md:p-8">
        {isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-28" />)}</div>
        ) : isError || !data ? (
          <ErrorState text={errorText(error, "Couldn't load metrics.")} onRetry={refetch} />
        ) : <Body m={data} />}
      </div>
    </div>
  );
}

function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "warn" | "ok" }) {
  return (
    <Card className={tone === "warn" ? "border-warn-border" : ""}>
      <CardBody className="p-5">
        <p className="text-sm">{label}</p>
        <p className="mt-2 text-3xl font-semibold tabular-nums tracking-tight">{value}</p>
        {sub && <p className="mt-1 text-xs">{sub}</p>}
      </CardBody>
    </Card>
  );
}

function secs(v: number | null) {
  if (v == null) return "—";
  return v < 90 ? `${v.toFixed(0)} s` : `${(v / 60).toFixed(1)} min`;
}

function Body({ m }: { m: Metrics }) {
  const o = m.orders;
  const fixes = Object.entries(m.lines.fixes_by_original_method);
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label="Orders received" value={String(o.orders)} sub={`${o.documents} documents · ${o.failed + o.unreadable} couldn't be read`} />
        <Tile label="Auto-approved" value={pct(o.auto_approve_rate_pct)} sub={`${o.auto_approved} of ${o.orders} orders needed no person`} />
        <Tile label="Accepted with no edits" value={pct(o.no_edit_rate_pct)} sub={`${o.accepted_without_edits} of ${o.accepted} accepted orders · target ≥ 50%`} />
        <Tile label="Auto-approved, later fixed" value={String(m.lines.auto_approved_then_fixed)}
          sub="Lines that went through alone and a reviewer changed. Should be 0." tone={m.lines.auto_approved_then_fixed > 0 ? "warn" : undefined} />
        <Tile label="Waiting for review" value={String(o.needs_review)} sub={`${m.lines.still_flagged} lines flagged`} />
        <Tile label="Received → routed (p95)" value={secs(m.timing.routed_p95_s)} sub={`median ${secs(m.timing.routed_p50_s)}`} />
        <Tile label="Sent to ERP" value={String(o.exported)} sub={`${o.export_failed} failed · median ${secs(m.timing.export_p50_s)} to send`} tone={o.export_failed > 0 ? "warn" : undefined} />
        <Tile label="LLM cost per order" value={m.llm.cost_per_order_gbp == null ? "—" : money(m.llm.cost_per_order_gbp)}
          sub={m.llm.note ?? `total ${money(m.llm.cost_gbp)}`} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Orders per day</CardTitle>
          <div className="flex items-center gap-4 text-sm" aria-label="Legend">
            <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: AUTO }} /> Auto-approved</span>
            <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: REVIEW }} /> Reviewed or waiting</span>
          </div>
        </CardHeader>
        <CardBody>
          {m.by_day.length === 0 ? <EmptyState title="No orders in this period" /> : (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={m.by_day} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="#ececea" />
                  <XAxis dataKey="day" tickLine={false} axisLine={{ stroke: "#d4d4d4" }} tick={{ fill: "#0a0a0a", fontSize: 12 }}
                    tickFormatter={(d: string) => new Date(d).toLocaleDateString("en-GB", { day: "numeric", month: "short" })} minTickGap={16} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: "#0a0a0a", fontSize: 12 }} />
                  <Tooltip cursor={{ fill: "#f5f5f4" }} contentStyle={{ borderRadius: 12, borderColor: "#e5e5e5", color: "#0a0a0a" }}
                    labelFormatter={(d) => new Date(String(d)).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })} />
                  <Bar dataKey="auto_approved" name="Auto-approved" stackId="a" fill={AUTO} stroke="#fff" strokeWidth={2} maxBarSize={36} />
                  <Bar dataKey="reviewed_or_pending" name="Reviewed or waiting" stackId="a" fill={REVIEW} stroke="#fff" strokeWidth={2} radius={[4, 4, 0, 0]} maxBarSize={36} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardBody>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Card className="min-w-0">
          <CardHeader><CardTitle>LLM calls</CardTitle><span className="text-xs">every call is logged with model and prompt version</span></CardHeader>
          {m.llm.by_purpose.length === 0 ? <EmptyState title="No LLM calls in this period" /> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border text-left text-xs font-medium uppercase tracking-wide">
                  <th className="px-4 py-3">Purpose</th><th className="px-4 py-3">Model / prompt</th><th className="px-4 py-3 text-right">Calls</th>
                  <th className="px-4 py-3 text-right">Failed</th><th className="px-4 py-3 text-right">Tokens in / out</th>
                  <th className="px-4 py-3 text-right">p95</th><th className="px-4 py-3 text-right">Cost</th>
                </tr></thead>
                <tbody>
                  {m.llm.by_purpose.map((r) => (
                    <tr key={`${r.purpose}-${r.model}-${r.prompt_version}`} className="border-b border-border last:border-0">
                      <td className="px-4 py-3 font-medium">{r.purpose}</td>
                      <td className="px-4 py-3"><span className="font-mono text-xs">{r.model}</span>{r.fallback && <Badge tone="warn" className="ml-2">fallback</Badge>}<br /><span className="text-xs">{r.prompt_version}</span></td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.calls}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.failures}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.input_tokens.toLocaleString()} / {r.output_tokens.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.latency_p95_ms == null ? "—" : `${(r.latency_p95_ms / 1000).toFixed(1)} s`}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.cost_gbp == null ? "—" : money(r.cost_gbp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {m.llm.note && <p className="flex items-center gap-2 border-t border-border px-4 py-3 text-xs"><Info className="h-3.5 w-3.5" /> {m.llm.note}</p>}
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle>Reviewer fixes by what the matcher said</CardTitle></CardHeader>
            <CardBody>
              {fixes.length === 0 ? <p className="text-sm">No lines fixed in this period.</p> : (
                <ul className="space-y-2 text-sm">
                  {fixes.map(([method, n]) => {
                    const max = Math.max(...fixes.map(([, x]) => x));
                    return (
                      <li key={method} className="grid grid-cols-[110px_1fr_32px] items-center gap-3">
                        <span>{method}</span>
                        <span className="h-2 rounded-full bg-neutral-100"><span className="block h-full rounded-full" style={{ width: `${(n / max) * 100}%`, background: AUTO }} /></span>
                        <span className="text-right tabular-nums">{n}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><FlaskConical className="h-4 w-4" /> Latest evals</CardTitle><Badge tone="info">synthetic data</Badge></CardHeader>
            <CardBody className="space-y-3 text-sm">
              {m.evals.matching ? (
                <div className="flex justify-between gap-3"><span>Matching top-1 / top-5</span><span className="tabular-nums font-medium">{pct(m.evals.matching.top1_pct, 1)} / {pct(m.evals.matching.top5_pct, 1)}</span></div>
              ) : null}
              {m.evals.matching ? (
                <div className="flex justify-between gap-3"><span>Auto-approved lines that are right</span><span className="tabular-nums font-medium">{pct(m.evals.matching.auto_precision_pct, 1)} at {pct(m.evals.matching.auto_approve_pct, 1)} auto</span></div>
              ) : null}
              {m.evals.injection ? (
                <div className="flex justify-between gap-3"><span>Injection orders that changed anything unreviewed</span><span className="tabular-nums font-medium">{m.evals.injection.changed_without_review} of {m.evals.injection.orders}</span></div>
              ) : null}
              {m.evals.resolve_agent ? (
                <div className="flex justify-between gap-3"><span>AI suggestion precision</span><span className="tabular-nums font-medium">{pct(m.evals.resolve_agent.pick_precision_pct, 1)}</span></div>
              ) : null}
              {!m.evals.matching && !m.evals.injection && !m.evals.resolve_agent && <p>No saved eval runs found. Run the evals to see them here.</p>}
            </CardBody>
          </Card>
        </div>
      </div>
    </>
  );
}
