"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, Check, CheckCircle2, Keyboard, Loader2, RefreshCw, Search, Sparkles, X } from "lucide-react";
import { DocumentPane } from "@/components/document-pane";
import { ConfidenceBar, StatusBadge } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import type { Line, Order } from "@/lib/types";
import { cn, dateLabel, errorText, money } from "@/lib/utils";
import { useApproveMutation, useFixLineMutation, useOrderQuery, useOrdersQuery, useRejectMutation, useSearchProductsQuery } from "@/store/api";

const EDITABLE = ["needs_review", "auto_approved", "export_failed"];
const METHOD: Record<string, string> = {
  alias: "Known customer reference", code: "Product code", search: "Catalogue search",
  history: "Customer's usual brand", agent: "AI suggestion", human: "Fixed by reviewer",
};

export default function OrderPage() {
  const { id } = useParams<{ id: string }>();
  const orderId = Number(id);
  const { data: order, isLoading, isError, error, refetch } = useOrderQuery(orderId, { skip: !Number.isFinite(orderId) });

  if (isLoading) {
    return <div className="grid gap-6 p-8 lg:grid-cols-2"><Skeleton className="h-[70vh]" /><Skeleton className="h-[70vh]" /></div>;
  }
  if (isError || !order) {
    return <div className="p-8"><ErrorState text={errorText(error, "Couldn't load this order.")} onRetry={refetch} /></div>;
  }
  return <Review order={order} refetch={refetch} />;
}

function Review({ order, refetch }: { order: Order; refetch: () => void }) {
  const router = useRouter();
  const toast = useToast();
  const editable = EDITABLE.includes(order.status);
  const firstFlagged = order.lines.find((l) => l.needs_review)?.line_no ?? order.lines[0]?.line_no ?? 1;
  const [selected, setSelected] = useState(firstFlagged);
  const [conflict, setConflict] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [fixLine, fixState] = useFixLineMutation();
  const [approve, approveState] = useApproveMutation();
  const { data: inbox } = useOrdersQuery({});

  const open = order.lines.filter((l) => l.needs_review).length;
  const total = order.lines.reduce((s, l) => s + (l.unit_price ?? 0) * l.qty, 0);
  const line = order.lines.find((l) => l.line_no === selected) ?? order.lines[0];
  const nextToReview = useMemo(
    () => inbox?.find((o) => o.status === "needs_review" && o.id !== order.id)?.id, [inbox, order.id]);

  const onError = useCallback((err: unknown) => {
    if ((err as { status?: number }).status === 409 && errorText(err).toLowerCase().includes("changed by someone")) setConflict(true);
    else toast(errorText(err), "bad");
  }, [toast]);

  const fix = useCallback(async (l: Line, change: { product_id?: number; qty?: number }, label?: string) => {
    try {
      const updated = await fixLine({ orderId: order.id, lineNo: l.line_no, version: order.version, ...change }).unwrap();
      if (change.product_id && updated.customer) {
        toast(`Saved. Next time ${updated.customer.name} writes “${l.raw_text}”, it matches ${label ?? "this product"} automatically.`);
      } else toast("Line saved.");
      const next = updated.lines.find((x) => x.needs_review && x.line_no !== l.line_no);
      if (next) setSelected(next.line_no);
    } catch (err) { onError(err); }
  }, [fixLine, order.id, order.version, toast, onError]);

  const doApprove = useCallback(async () => {
    try {
      await approve({ orderId: order.id, version: order.version }).unwrap();
      toast(`Order #${order.id} approved. It will be sent to the ERP.`);
      router.push(nextToReview ? `/orders/${nextToReview}` : "/inbox");
    } catch (err) { onError(err); }
  }, [approve, order.id, order.version, toast, router, nextToReview, onError]);

  // keyboard: j/k move, 1-3 pick a candidate, a approve
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) || e.metaKey || e.ctrlKey || e.altKey) return;
      const i = order.lines.findIndex((l) => l.line_no === selected);
      if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); setSelected(order.lines[Math.min(i + 1, order.lines.length - 1)].line_no); }
      else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); setSelected(order.lines[Math.max(i - 1, 0)].line_no); }
      else if (editable && line && /^[1-3]$/.test(e.key)) {
        const c = line.candidates[Number(e.key) - 1];
        if (c) fix(line, { product_id: c.product_id }, c.code);
      } else if (editable && e.key === "a" && open === 0) doApprove();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [order.lines, selected, editable, line, open, fix, doApprove]);

  return (
    <div className="flex h-[100dvh] flex-col">
      {/* header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-4">
        <div className="flex min-w-0 items-center gap-4">
          <Link href="/inbox" className="rounded-xl border border-border p-2 hover:bg-secondary" aria-label="Back to inbox"><ArrowLeft className="h-4 w-4" /></Link>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold">Order #{order.id}</h1>
              <StatusBadge status={order.status} />
            </div>
            <p className="truncate text-sm">
              {order.customer ? <>{order.customer.name} <span className="font-mono">({order.customer.account_code})</span></> : <><AlertTriangle className="mr-1 inline h-3.5 w-3.5 text-amber-600" />Sender not recognised</>}
              {" · "}PO {order.po_number ?? "—"} · Delivery {dateLabel(order.delivery_date)}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="mr-2 text-right text-sm">
            <div className="text-xs">Order total (ex VAT)</div>
            <div className="text-lg font-semibold tabular-nums">{money(total)}</div>
          </div>
          {editable && (
            <>
              <Button variant="danger" onClick={() => setRejecting((v) => !v)}><X className="h-4 w-4" /> Reject</Button>
              <Button onClick={doApprove} disabled={open > 0 || approveState.isLoading}
                title={open > 0 ? `${open} line(s) still need a product or quantity` : "Approve (a)"}>
                {approveState.isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                {open > 0 ? `${open} to fix` : "Approve"}
              </Button>
            </>
          )}
        </div>
      </div>

      {conflict && (
        <div className="flex items-center justify-between gap-3 border-b border-warn-border bg-warn-bg px-6 py-3 text-sm">
          <span className="flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-amber-600" /> Someone else changed this order while you had it open.</span>
          <Button size="sm" variant="outline" onClick={() => { setConflict(false); refetch(); }}><RefreshCw className="h-3.5 w-3.5" /> Reload</Button>
        </div>
      )}
      {order.status === "rejected" && order.reject_reason && (
        <div className="border-b border-border bg-secondary px-6 py-3 text-sm">Rejected: {order.reject_reason}</div>
      )}
      {order.erp_ref && <div className="border-b border-ok-border bg-ok-bg px-6 py-3 text-sm">In the ERP as <span className="font-mono">{order.erp_ref}</span></div>}
      {rejecting && <RejectBar order={order} onDone={() => router.push("/inbox")} onCancel={() => setRejecting(false)} onError={onError} />}

      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <section className="min-h-0 border-b border-border lg:border-b-0 lg:border-r">
          <DocumentPane doc={order.document} highlight={line?.raw_text} />
        </section>

        <section className="flex min-h-0 flex-col">
          <div className="flex items-center justify-between border-b border-border px-5 py-3 text-sm">
            <span className="font-medium">{order.lines.length} lines · {open === 0 ? "all checked" : `${open} need you`}</span>
            <span className="hidden items-center gap-1.5 sm:flex"><Keyboard className="h-4 w-4" /> j / k move · 1–3 pick · a approve</span>
          </div>
          <div className="min-h-0 flex-1 space-y-3 overflow-auto p-5">
            {order.lines.map((l) => (
              <LineCard key={l.line_no} line={l} selected={l.line_no === selected} editable={editable}
                busy={fixState.isLoading} onSelect={() => setSelected(l.line_no)} onFix={(c, label) => fix(l, c, label)} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function LineCard({ line, selected, editable, busy, onSelect, onFix }: {
  line: Line; selected: boolean; editable: boolean; busy: boolean; onSelect: () => void;
  onFix: (change: { product_id?: number; qty?: number }, label?: string) => void;
}) {
  const lineTotal = line.unit_price != null ? line.unit_price * line.qty : null;

  return (
    <Card onClick={onSelect}
      className={cn("cursor-pointer p-4 transition-shadow",
        line.needs_review ? "border-warn-border" : "",
        selected ? "ring-2 ring-violet-400 ring-offset-1" : "hover:shadow-sm")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs font-medium">
            <span className="rounded-md border border-border px-1.5">{line.line_no}</span>
            {line.needs_review ? <Badge tone="warn">Check this line</Badge> : <Badge tone="ok">Matched</Badge>}
            {line.match_method && <span>{METHOD[line.match_method] ?? line.match_method}</span>}
          </div>
          <p className="mt-2 font-mono text-sm">“{line.raw_text}”</p>
        </div>
        <div className="shrink-0 text-right text-sm">
          <div className="tabular-nums"><span className="font-semibold">{line.qty}</span> {line.unit ?? ""}</div>
          <div className="tabular-nums">{money(line.unit_price)} each</div>
          <div className="font-semibold tabular-nums">{money(lineTotal)}</div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-neutral-50 px-3 py-2 text-sm">
        {line.product ? (
          <span className="min-w-0"><span className="font-mono text-xs">{line.product.code}</span> · {line.product.name}
            {line.product.pack_qty > 1 && <span> (pack of {line.product.pack_qty})</span>}</span>
        ) : <span>No product chosen yet</span>}
        <ConfidenceBar value={line.confidence} />
      </div>

      {line.reason && (
        <p className="mt-2 flex items-start gap-2 rounded-xl border border-warn-border bg-warn-bg px-3 py-2 text-sm">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" /> {line.reason}
        </p>
      )}

      {selected && editable && (
        <div className="mt-4 space-y-4 border-t border-border pt-4" onClick={(e) => e.stopPropagation()}>
          {line.candidates.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide">Candidates</p>
              <div className="space-y-2">
                {line.candidates.map((c, i) => {
                  const chosen = line.product?.id === c.product_id;
                  return (
                    <button key={c.product_id} disabled={busy} onClick={() => onFix({ product_id: c.product_id }, c.code)}
                      className={cn("flex w-full items-center gap-3 rounded-xl border px-3 py-2 text-left text-sm transition-colors disabled:opacity-60",
                        chosen ? "border-ok-border bg-ok-bg" : "border-border hover:bg-secondary")}>
                      <kbd className="rounded-md border border-border bg-white px-1.5 font-mono text-xs">{i + 1}</kbd>
                      <span className="min-w-0 flex-1"><span className="font-mono text-xs">{c.code}</span><br />{c.name}</span>
                      <span className="tabular-nums text-xs">{c.score.toFixed(2)}</span>
                      {chosen && <CheckCircle2 className="h-4 w-4 text-green-600" />}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          <CatalogueSearch initial={line.raw_text} busy={busy} onPick={(p) => onFix({ product_id: p.id }, p.code)} />
          <QtyEditor key={line.qty} current={line.qty} busy={busy} onSave={(qty) => onFix({ qty })} />
        </div>
      )}
    </Card>
  );
}

function QtyEditor({ current, busy, onSave }: { current: number; busy: boolean; onSave: (qty: number) => void }) {
  const [qty, setQty] = useState(String(current));   // re-mounted (key) when the saved qty changes
  return (
    <div className="flex items-end gap-2">
      <label className="text-sm">
        <span className="mb-1.5 block font-medium">Quantity (selling units)</span>
        <Input type="number" min={1} step={1} value={qty} onChange={(e) => setQty(e.target.value)} className="w-32" />
      </label>
      <Button variant="outline" disabled={busy || !(Number(qty) > 0) || Number(qty) === current}
        onClick={() => onSave(Number(qty))}>Save quantity</Button>
    </div>
  );
}

function CatalogueSearch({ initial, busy, onPick }: { initial: string; busy: boolean; onPick: (p: { id: number; code: string }) => void }) {
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const t = setTimeout(() => setDebounced(term.trim()), 250); return () => clearTimeout(t); }, [term]);
  const { data, isFetching, isError } = useSearchProductsQuery(debounced, { skip: debounced.length < 2 });

  return (
    <div>
      <p className="mb-2 text-xs font-medium uppercase tracking-wide">Search the catalogue</p>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" />
        <Input value={term} onChange={(e) => setTerm(e.target.value)} placeholder={`e.g. ${initial.slice(0, 40)}`} className="pl-9" />
        {isFetching && <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin" />}
      </div>
      {isError && <p className="mt-2 text-sm">Search failed.</p>}
      {debounced.length >= 2 && data && (
        <div className="mt-2 max-h-56 overflow-auto rounded-xl border border-border">
          {data.length === 0 ? <p className="p-3 text-sm">No products found.</p> : data.map((p) => (
            <button key={p.code} disabled={busy} onClick={() => onPick(p)}
              className="flex w-full items-center gap-3 border-b border-border px-3 py-2 text-left text-sm last:border-0 hover:bg-secondary disabled:opacity-60">
              <span className="min-w-0 flex-1"><span className="font-mono text-xs">{p.code}</span><br />{p.name}</span>
              <span className="tabular-nums text-xs">{p.score.toFixed(2)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function RejectBar({ order, onDone, onCancel, onError }: { order: Order; onDone: () => void; onCancel: () => void; onError: (e: unknown) => void }) {
  const [reason, setReason] = useState("");
  const [reject, { isLoading }] = useRejectMutation();
  const toast = useToast();
  async function submit() {
    try {
      await reject({ orderId: order.id, version: order.version, reason: reason.trim() }).unwrap();
      toast(`Order #${order.id} rejected.`);
      onDone();
    } catch (err) { onError(err); }
  }
  return (
    <div className="flex flex-wrap items-end gap-3 border-b border-bad-border bg-bad-bg px-6 py-3">
      <label className="min-w-[260px] flex-1 text-sm">
        <span className="mb-1.5 block font-medium">Why are you rejecting this order? (saved in the audit log)</span>
        <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Duplicate of order #12, customer confirmed by phone" autoFocus />
      </label>
      <Button variant="outline" onClick={onCancel}>Cancel</Button>
      <Button onClick={submit} disabled={!reason.trim() || isLoading}>{isLoading && <Loader2 className="h-4 w-4 animate-spin" />} Reject order</Button>
    </div>
  );
}
