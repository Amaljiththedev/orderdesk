import * as React from "react";
import { AlertTriangle, Inbox } from "lucide-react";
import { Button } from "./button";

export function EmptyState({ title, text, icon, action }: {
  title: string; text?: string; icon?: React.ReactNode; action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <div className="mb-1 rounded-2xl border border-border bg-secondary p-3">{icon ?? <Inbox className="h-5 w-5" />}</div>
      <p className="font-medium">{title}</p>
      {text && <p className="max-w-sm text-sm text-muted-foreground">{text}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-bad-border bg-bad-bg p-4 text-sm">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
      <div className="flex-1">{text}</div>
      {onRetry && <Button size="sm" variant="outline" onClick={onRetry}>Try again</Button>}
    </div>
  );
}
