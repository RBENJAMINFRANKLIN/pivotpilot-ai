import { useMutation } from "@tanstack/react-query";
import { Mic, Wand2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { errorText, post } from "@/lib/api";
import { useRefreshAll } from "@/lib/hooks";
import { Alert, Button, Textarea } from "./ui";

type Interpretation = {
  understood: boolean;
  message?: string;
  valid?: boolean;
  errors?: string[];
  summary?: string;
  changes?: { field: string; item?: string; from?: unknown; to?: unknown }[];
  requires_confirmation?: boolean;
  action?: { type: string; params: Record<string, unknown> };
};

/** Natural-language box. Works with any dictation tool (e.g. Wispr Flow) because it is a plain
 *  text field: dictate, review the proposed change, confirm, and see the real result. */
export function CommandBar() {
  const [text, setText] = useState("");
  const [proposal, setProposal] = useState<Interpretation | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const refresh = useRefreshAll();
  const nav = useNavigate();

  const interpret = useMutation({
    mutationFn: () => post<Interpretation>("/commands/interpret", { text }),
    onSuccess: (r) => { setProposal(r); setResult(null); },
  });
  const execute = useMutation({
    mutationFn: () => post<{ summary: string; type: string; result: { assessment?: { id: string } } }>("/commands/execute", { ...proposal!.action, confirmed: true }),
    onSuccess: (r) => {
      setResult(`Done: ${r.summary}.`);
      setProposal(null);
      setText("");
      refresh();
      if (r.type === "start_topic_check") nav("/assessment");
    },
  });

  return (
    <div className="space-y-2">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) interpret.mutate(); }}>
        <label htmlFor="command" className="sr-only">Tell PivotPilot what changed</label>
        <div className="relative flex-1">
          <Mic className="pointer-events-none absolute left-3 top-3 size-4 text-muted" aria-hidden />
          <Textarea id="command" rows={1} value={text} onChange={(e) => setText(e.target.value)} className="min-h-10 resize-y pl-9"
            placeholder='Type or dictate, e.g. "I can study 8 hours a week" or "I applied for a data analyst role at Acme"'
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (text.trim()) interpret.mutate(); } }} />
        </div>
        <Button type="submit" variant="subtle" loading={interpret.isPending}><Wand2 className="size-4" aria-hidden />Interpret</Button>
      </form>
      {interpret.isError && <Alert tone="bad">{errorText(interpret.error)}</Alert>}
      {proposal && !proposal.understood && <Alert tone="warn">{proposal.message}</Alert>}
      {proposal?.understood && (
        <Alert tone={proposal.valid ? "brand" : "warn"} title={proposal.valid ? "Proposed change" : "I understood, but can't do that"}>
          {proposal.valid ? (
            <>
              <p>{proposal.summary}</p>
              <ul className="mt-1 list-disc pl-5 text-xs text-muted">
                {proposal.changes?.map((c, i) => (
                  <li key={i}>{c.field}{c.item ? ` (${c.item})` : ""}: {c.from !== undefined ? `${String(c.from ?? "not set")} → ` : ""}<strong>{String(c.to ?? "")}</strong></li>
                ))}
              </ul>
              <div className="mt-2 flex gap-2">
                <Button size="sm" onClick={() => execute.mutate()} loading={execute.isPending}>{proposal.requires_confirmation ? "Confirm" : "Go"}</Button>
                <Button size="sm" variant="ghost" onClick={() => setProposal(null)}>Cancel</Button>
              </div>
              {execute.isError && <p className="mt-2 text-bad">{errorText(execute.error)}</p>}
            </>
          ) : <p>{proposal.errors?.join(" ")}</p>}
        </Alert>
      )}
      {result && <Alert tone="good">{result}</Alert>}
    </div>
  );
}
