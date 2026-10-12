import * as React from "react";
import { cn } from "@/lib/utils";

export type Tone = "neutral" | "warn" | "ok" | "bad" | "info" | "accent";
const tones: Record<Tone, string> = {
  neutral: "bg-secondary border-border",
  warn: "bg-warn-bg border-warn-border",
  ok: "bg-ok-bg border-ok-border",
  bad: "bg-bad-bg border-bad-border",
  info: "bg-info-bg border-info-border",
  accent: "bg-violet-50 border-violet-300",
};
const dots: Record<Tone, string> = {
  neutral: "bg-neutral-400", warn: "bg-amber-500", ok: "bg-green-600", bad: "bg-red-600",
  info: "bg-blue-600", accent: "bg-violet-600",
};

export function Badge({ tone = "neutral", dot = true, className, children, ...props }:
  React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone; dot?: boolean }) {
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium text-foreground", tones[tone], className)}
      {...props}
    >
      {dot && <span className={cn("h-1.5 w-1.5 rounded-full", dots[tone])} aria-hidden />}
      {children}
    </span>
  );
}
