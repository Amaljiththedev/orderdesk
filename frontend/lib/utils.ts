import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const gbp = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" });
export const money = (v: number | null | undefined) => (v == null ? "—" : gbp.format(v));

export function pct(v: number | null | undefined, digits = 0) {
  return v == null ? "—" : `${v.toFixed(digits)}%`;
}

export function timeAgo(iso: string | null | undefined) {
  if (!iso) return "—";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function dateLabel(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}

/** FastAPI errors are {detail: string} or {detail: [{msg}]}; turn any of them into one sentence. */
export function errorText(err: unknown, fallback = "Something went wrong") {
  const e = err as { status?: number | string; data?: { detail?: unknown } } | undefined;
  const d = e?.data?.detail;
  if (typeof d === "string") return d.charAt(0).toUpperCase() + d.slice(1);
  if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg);
  if (e?.status === "FETCH_ERROR") return "Can't reach the server. Is the API running on port 8001?";
  return fallback;
}
