import { Badge, type Tone } from "@/components/ui/badge";
import type { OrderStatus } from "@/lib/types";

export const STATUS: Record<OrderStatus, { label: string; tone: Tone }> = {
  needs_review: { label: "Needs review", tone: "warn" },
  auto_approved: { label: "Auto-approved", tone: "accent" },
  approved: { label: "Approved", tone: "info" },
  exported: { label: "Sent to ERP", tone: "ok" },
  export_failed: { label: "Export failed", tone: "bad" },
  rejected: { label: "Rejected", tone: "neutral" },
};

export function StatusBadge({ status }: { status: OrderStatus }) {
  const s = STATUS[status] ?? { label: status, tone: "neutral" as Tone };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

const DOC: Record<string, { label: string; tone: Tone }> = {
  queued: { label: "Queued", tone: "neutral" },
  processing: { label: "Reading…", tone: "info" },
  extracted: { label: "Matching…", tone: "info" },
  done: { label: "Done", tone: "ok" },
  needs_review: { label: "Couldn't read", tone: "warn" },
  failed: { label: "Failed", tone: "bad" },
};

export function DocStatusBadge({ status }: { status: string }) {
  const s = DOC[status] ?? { label: status, tone: "neutral" as Tone };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export function ConfidenceBar({ value }: { value: number | null | undefined }) {
  if (value == null) return <span>—</span>;
  const v = Math.max(0, Math.min(1, value));
  const color = v >= 0.5 ? "bg-green-600" : v >= 0.2 ? "bg-amber-500" : "bg-red-500";
  return (
    <span className="inline-flex items-center gap-2" title={`confidence ${v.toFixed(2)}`}>
      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-neutral-200">
        <span className={`block h-full ${color}`} style={{ width: `${Math.max(4, v * 100)}%` }} />
      </span>
      <span className="tabular-nums text-xs">{v.toFixed(2)}</span>
    </span>
  );
}
