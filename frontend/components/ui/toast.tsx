"use client";
import * as React from "react";
import { CheckCircle2, AlertTriangle, X } from "lucide-react";
import { cn } from "@/lib/utils";

type Toast = { id: number; text: string; tone: "ok" | "bad" };
const Ctx = React.createContext<(text: string, tone?: "ok" | "bad") => void>(() => {});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<Toast[]>([]);
  const push = React.useCallback((text: string, tone: "ok" | "bad" = "ok") => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { id, text, tone }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={cn(
            "pointer-events-auto flex items-start gap-2 rounded-xl border bg-white p-3 text-sm text-foreground shadow-lg animate-in fade-in slide-in-from-bottom-2",
            t.tone === "ok" ? "border-ok-border" : "border-bad-border")}>
            {t.tone === "ok" ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-600" />
              : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />}
            <span className="flex-1">{t.text}</span>
            <button aria-label="Dismiss" onClick={() => setItems((xs) => xs.filter((x) => x.id !== t.id))}>
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => React.useContext(Ctx);
