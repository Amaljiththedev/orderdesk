"use client";
import { useEffect, useMemo, useState } from "react";
import { FileText, Loader2 } from "lucide-react";
import { Tabs } from "@/components/ui/tabs";
import { useAppSelector } from "@/store/hooks";

/** The source document. "Text" is what the model read, with the selected line highlighted. */
export function DocumentPane({ doc, highlight }: {
  doc: { id: number; filename: string; text: string | null }; highlight?: string | null;
}) {
  const [view, setView] = useState<"text" | "original">("text");
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-2 text-sm font-medium">
          <FileText className="h-4 w-4 shrink-0" /><span className="truncate">{doc.filename}</span>
        </div>
        <Tabs value={view} onChange={setView} items={[{ value: "text", label: "Text read" }, { value: "original", label: "Original" }]} />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {view === "text" ? <TextView text={doc.text} highlight={highlight} /> : <OriginalView id={doc.id} filename={doc.filename} />}
      </div>
    </div>
  );
}

function TextView({ text, highlight }: { text: string | null; highlight?: string | null }) {
  const parts = useMemo(() => {
    if (!text) return null;
    const needle = highlight?.trim();
    if (!needle) return [text];
    const i = text.toLowerCase().indexOf(needle.toLowerCase());
    return i < 0 ? [text] : [text.slice(0, i), text.slice(i, i + needle.length), text.slice(i + needle.length)];
  }, [text, highlight]);

  useEffect(() => {
    document.getElementById("evidence")?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [highlight]);

  if (!parts) return <p className="p-5 text-sm">No text was read from this document.</p>;
  return (
    <pre className="whitespace-pre-wrap break-words p-5 font-mono text-[13px] leading-6 text-foreground">
      {parts.length === 3 ? <>{parts[0]}<mark id="evidence" className="evidence">{parts[1]}</mark>{parts[2]}</> : parts[0]}
    </pre>
  );
}

function OriginalView({ id, filename }: { id: number; filename: string }) {
  const token = useAppSelector((s) => s.auth.token);
  const [state, setState] = useState<{ url?: string; text?: string; error?: string }>({});

  useEffect(() => {
    let url: string | undefined;
    let alive = true;
    // the file needs the bearer token, so fetch it ourselves instead of pointing an iframe at it
    fetch(`/api/documents/${id}/file`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "The original file is not on the server." : "Couldn't load the file.");
        const blob = await r.blob();
        if (!alive) return;
        if (filename.toLowerCase().endsWith(".pdf")) {
          url = URL.createObjectURL(blob);
          setState({ url });
        } else {
          setState({ text: await blob.text() });
        }
      })
      .catch((e: Error) => alive && setState({ error: e.message }));
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [id, filename, token]);

  if (state.error) return <p className="p-5 text-sm">{state.error}</p>;
  if (state.url) return <iframe src={state.url} title={filename} className="h-full min-h-[70vh] w-full" />;
  if (state.text != null) return <pre className="whitespace-pre-wrap break-words p-5 font-mono text-[13px] leading-6">{state.text}</pre>;
  return <div className="flex items-center gap-2 p-5 text-sm"><Loader2 className="h-4 w-4 animate-spin" /> Loading original…</div>;
}
