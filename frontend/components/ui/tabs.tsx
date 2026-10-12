"use client";
import { cn } from "@/lib/utils";

export function Tabs<T extends string>({ value, onChange, items, className }: {
  value: T; onChange: (v: T) => void; items: { value: T; label: string; count?: number }[]; className?: string;
}) {
  return (
    <div role="tablist" className={cn("inline-flex flex-wrap gap-1 rounded-xl border border-border bg-secondary p-1", className)}>
      {items.map((it) => (
        <button
          key={it.value}
          role="tab"
          aria-selected={value === it.value}
          onClick={() => onChange(it.value)}
          className={cn(
            "rounded-lg px-3 py-1.5 text-sm font-medium text-foreground transition-colors",
            value === it.value ? "bg-white shadow-sm" : "hover:bg-white/60",
          )}
        >
          {it.label}
          {it.count != null && <span className="ml-1.5 tabular-nums">{it.count}</span>}
        </button>
      ))}
    </div>
  );
}
