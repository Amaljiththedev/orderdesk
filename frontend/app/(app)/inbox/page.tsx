"use client";
import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ChevronRight, FileText, Loader2, Mail, RefreshCw, Search, Upload } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { ConfidenceBar, DocStatusBadge, StatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import type { OrderRow, OrderStatus } from "@/lib/types";
import { dateLabel, errorText, timeAgo } from "@/lib/utils";
import { useDocumentsQuery, useOrdersQuery, useUploadMutation } from "@/store/api";

type Filter = "all" | OrderStatus;
const FILTERS: { value: Filter; label: string }[] = [
  { value: "needs_review", label: "Needs review" },
  { value: "auto_approved", label: "Auto-approved" },
  { value: "approved", label: "Approved" },
  { value: "exported", label: "Sent to ERP" },
  { value: "export_failed", label: "Export failed" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

export default function InboxPage() {
  const router = useRouter();
  const [filter, setFilter] = useState<Filter>("needs_review");
  const [q, setQ] = useState("");
  // one list, filtered here, so the tab counts are always right; refreshes every 5 s
  const { data, isLoading, isError, error, refetch, isFetching } = useOrdersQuery({}, { pollingInterval: 5000 });

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: data?.length ?? 0 };
    for (const o of data ?? []) c[o.status] = (c[o.status] ?? 0) + 1;
    return c;
  }, [data]);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data ?? [])
      .filter((o) => filter === "all" || o.status === filter)
      .filter((o) => !needle || [o.customer, o.po_number, o.filename, String(o.id)].some((v) => v?.toLowerCase().includes(needle)));
  }, [data, filter, q]);

  return (
    <div>
      <PageHeader
        title="Inbox"
        text="Orders read from email and PDF. Work the ones that need review first."
        actions={<>
          <Button variant="outline" onClick={() => refetch()} aria-label="Refresh">
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh
          </Button>
          <UploadButton />
        </>}
      />

      <div className="grid gap-6 p-6 md:p-8 xl:grid-cols-[1fr_320px]">
        <Card className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-4">
            <Tabs value={filter} onChange={setFilter} items={FILTERS.map((f) => ({ ...f, count: counts[f.value] ?? 0 }))} />
            <div className="relative w-full sm:w-64">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Customer, PO, file…" className="pl-9" aria-label="Search orders" />
            </div>
          </div>

          {isLoading ? (
            <div className="space-y-3 p-4">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : isError ? (
            <div className="p-4"><ErrorState text={errorText(error, "Couldn't load orders.")} onRetry={refetch} /></div>
          ) : rows.length === 0 ? (
            <EmptyState
              title={filter === "needs_review" && !q ? "Nothing to review" : "No orders here"}
              text={filter === "needs_review" && !q ? "Every order is either auto-approved or already handled. Upload an order to try it." : "Try another tab or search."}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs font-medium uppercase tracking-wide">
                    <th className="px-4 py-3">Order</th>
                    <th className="px-4 py-3">Customer</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Lines</th>
                    <th className="px-4 py-3">Confidence</th>
                    <th className="px-4 py-3">Delivery</th>
                    <th className="px-4 py-3">Received</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((o) => <Row key={o.id} o={o} onOpen={() => router.push(`/orders/${o.id}`)} />)}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <RecentUploads />
      </div>
    </div>
  );
}

function Row({ o, onOpen }: { o: OrderRow; onOpen: () => void }) {
  return (
    <tr onClick={onOpen} onKeyDown={(e) => e.key === "Enter" && onOpen()} tabIndex={0}
      className="cursor-pointer border-b border-border last:border-0 hover:bg-neutral-50 focus:bg-neutral-50 focus:outline-none">
      <td className="px-4 py-3">
        <div className="font-medium">#{o.id}</div>
        <div className="flex items-center gap-1 text-xs">
          {o.filename.endsWith(".pdf") ? <FileText className="h-3 w-3" /> : <Mail className="h-3 w-3" />}
          <span className="max-w-[140px] truncate">{o.po_number || o.filename}</span>
        </div>
      </td>
      <td className="px-4 py-3">{o.customer ?? <span className="inline-flex items-center gap-1"><AlertTriangle className="h-3.5 w-3.5 text-amber-600" /> Unknown sender</span>}</td>
      <td className="px-4 py-3"><StatusBadge status={o.status} /></td>
      <td className="px-4 py-3 tabular-nums">
        {o.lines_to_review > 0 ? <span><span className="font-semibold">{o.lines_to_review}</span> of {o.lines} to check</span> : <span>{o.lines}</span>}
      </td>
      <td className="px-4 py-3"><ConfidenceBar value={o.confidence} /></td>
      <td className="px-4 py-3 whitespace-nowrap">{o.delivery_date ? dateLabel(o.delivery_date) : "—"}</td>
      <td className="px-4 py-3 whitespace-nowrap">{timeAgo(o.received_at)}</td>
      <td className="px-4 py-3"><ChevronRight className="h-4 w-4" /></td>
    </tr>
  );
}

function UploadButton() {
  const ref = useRef<HTMLInputElement>(null);
  const [upload, { isLoading }] = useUploadMutation();
  const toast = useToast();

  async function onFiles(files: FileList | null) {
    for (const file of Array.from(files ?? [])) {
      try {
        const doc = await upload(file).unwrap();
        toast(doc.duplicate ? `${file.name} was already uploaded; it won't be processed twice.` : `${file.name} uploaded. It will appear in the inbox in a few seconds.`);
      } catch (err) {
        toast(`${file.name}: ${errorText(err, "upload failed")}`, "bad");
      }
    }
    if (ref.current) ref.current.value = "";
  }

  return (
    <>
      <input ref={ref} type="file" accept=".eml,.pdf" multiple hidden onChange={(e) => onFiles(e.target.files)} />
      <Button onClick={() => ref.current?.click()} disabled={isLoading}>
        {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Upload order
      </Button>
    </>
  );
}

function RecentUploads() {
  const { data, isLoading, isError } = useDocumentsQuery(undefined, { pollingInterval: 3000 });
  return (
    <Card className="h-fit">
      <CardHeader><CardTitle>Recent documents</CardTitle></CardHeader>
      {isLoading ? (
        <div className="space-y-2 p-4">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-10" />)}</div>
      ) : isError ? (
        <p className="p-4 text-sm">Couldn&apos;t load documents.</p>
      ) : !data?.length ? (
        <p className="p-4 text-sm">No documents yet. Upload an .eml or .pdf order.</p>
      ) : (
        <ul className="divide-y divide-border">
          {data.map((d) => (
            <li key={d.id} className="px-4 py-3">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium" title={d.filename}>{d.filename}</span>
                <DocStatusBadge status={d.status} />
              </div>
              <div className="mt-0.5 text-xs">{timeAgo(d.received_at)} · {d.source}</div>
              {d.error && <p className="mt-1 line-clamp-2 text-xs">{d.error}</p>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
