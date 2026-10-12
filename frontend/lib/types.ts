// Shapes returned by the FastAPI backend (backend/app/api/*).

export type Role = "reviewer" | "admin";
export interface User {
  id: number; email: string; full_name: string | null; role: Role; must_change_password: boolean;
  is_active?: boolean; last_login_at?: string | null;
}
export interface Session { access_token: string; token_type: string; expires_in: number; user: User }

export type OrderStatus = "auto_approved" | "needs_review" | "approved" | "exported" | "export_failed" | "rejected";

export interface OrderRow {
  id: number; status: OrderStatus; customer: string | null; po_number: string | null;
  delivery_date: string | null; received_at: string; filename: string; lines: number;
  lines_to_review: number; confidence: number | null; erp_ref: string | null; version: number;
}

export interface Candidate { product_id: number; code: string; name: string; score: number }
export interface Line {
  line_no: number; raw_text: string; qty: number; unit: string | null;
  product: { id: number; code: string; name: string; pack_qty: number } | null;
  unit_price: number | null; match_method: string | null; confidence: number | null;
  candidates: Candidate[]; needs_review: boolean; reason: string | null;
}
export interface Order {
  id: number; status: OrderStatus; version: number; po_number: string | null; delivery_date: string | null;
  confidence: number | null; erp_ref: string | null; reject_reason: string | null;
  customer: { id: number; account_code: string; name: string } | null;
  document: { id: number; filename: string; received_at: string; text: string | null };
  lines: Line[];
}

export interface DocumentRow {
  id: number; filename: string; source: string; status: string; sha256: string;
  received_at: string; error: string | null; duplicate?: boolean;
}
export interface ProductHit { id: number; code: string; name: string; score: number }

export interface LlmRow {
  purpose: string; prompt_version: string; model: string; calls: number; failures: number;
  input_tokens: number; output_tokens: number; latency_p95_ms: number | null; fallback: boolean; cost_gbp: number | null;
}
export interface Metrics {
  window_days: number; since: string; data: string;
  orders: {
    orders: number; auto_approved: number; needs_review: number; approved: number; exported: number;
    export_failed: number; rejected: number; accepted_without_edits: number; accepted: number;
    documents: number; failed: number; unreadable: number;
    auto_approve_rate_pct: number | null; no_edit_rate_pct: number | null;
  };
  lines: { lines: number; still_flagged: number; fixed_by_reviewer: number;
    fixes_by_original_method: Record<string, number>; auto_approved_then_fixed: number };
  timing: { routed_p50_s: number | null; routed_p95_s: number | null; export_p50_s: number | null };
  llm: { by_purpose: LlmRow[]; cost_gbp: number | null; cost_per_order_gbp: number | null; note: string | null };
  by_day: { day: string; orders: number; auto_approved: number; reviewed_or_pending: number }[];
  evals: {
    matching?: { file: string; lines: number; top1_pct: number; top5_pct: number; auto_approve_pct: number; auto_precision_pct: number };
    injection?: { file: string; orders: number; changed_without_review: number };
    resolve_agent?: { file: string; lines: number; pick_precision_pct: number | null };
  };
}
