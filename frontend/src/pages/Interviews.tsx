import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, errorText, post } from "@/lib/api";
import { useActiveTransition, useRefreshAll } from "@/lib/hooks";
import type { Interview } from "@/lib/types";
import { Alert, Badge, Button, Card, CardTitle, Empty, PageHeader, Spinner, Textarea } from "@/components/ui";

export function InterviewsPage() {
  const { transition: t } = useActiveTransition();
  const refresh = useRefreshAll();
  const [current, setCurrent] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["interviews", t?.id], queryFn: () => api<{ id: string; status: string; overall_score: number | null; started_at: string }[]>(`/transitions/${t!.id}/interviews`), enabled: !!t });
  const start = useMutation({ mutationFn: () => post<Interview>(`/transitions/${t!.id}/interviews`), onSuccess: (iv) => { setCurrent(iv.id); refresh(); } });
  if (!t) return <Empty title="Create a career goal first" />;
  if (current) return <InterviewView id={current} onBack={() => setCurrent(null)} />;
  return (
    <>
      <PageHeader title="Mock interviews" actions={<Button onClick={() => start.mutate()} loading={start.isPending}>Start a mock interview</Button>}>
        Five role-specific questions (behavioural, technical and scenario), scored on the same five-part rubric every time. Type or dictate your answers.
      </PageHeader>
      {start.isError && <Alert tone="bad">{errorText(start.error)}</Alert>}
      {list.isLoading ? <Spinner /> : list.data?.length ? (
        <Card><CardTitle>History</CardTitle>
          <ul className="divide-y divide-line text-sm">{list.data.map((i) => (
            <li key={i.id} className="flex items-center justify-between py-2">
              <span>{new Date(i.started_at).toLocaleString()} <Badge tone={i.status === "completed" ? "good" : "warn"}>{i.status.replace("_", " ")}</Badge>{i.overall_score != null && ` · ${Math.round(i.overall_score)}/100`}</span>
              <Button size="sm" variant="ghost" onClick={() => setCurrent(i.id)}>Open</Button>
            </li>
          ))}</ul>
        </Card>
      ) : <Empty title="No mock interviews yet" />}
    </>
  );
}

function InterviewView({ id, onBack }: { id: string; onBack: () => void }) {
  const iv = useQuery({ queryKey: ["interview", id], queryFn: () => api<Interview>(`/interviews/${id}`) });
  if (!iv.data) return <Spinner />;
  const d = iv.data;
  return (
    <>
      <PageHeader title={`Mock interview: ${d.role}`} actions={<Button variant="outline" onClick={onBack}>Back</Button>}>
        {d.status === "completed" ? `Overall ${Math.round(d.overall_score ?? 0)}/100` : "Answer each question. Feedback appears after each answer."}
      </PageHeader>
      <Alert tone="brand">Rubric: {d.rubric.map((c) => c.name).join(", ")} (1-5 each). Suggested outlines use [placeholders]; fill them with your own real experience.</Alert>
      <div className="mt-4 space-y-4">{d.questions.map((q, i) => <QuestionBlock key={q.id} n={i + 1} interviewId={d.id} q={q} rubric={d.rubric} />)}</div>
    </>
  );
}

function QuestionBlock({ n, interviewId, q, rubric }: { n: number; interviewId: string; q: Interview["questions"][number]; rubric: Interview["rubric"] }) {
  const [text, setText] = useState("");
  const refresh = useRefreshAll();
  const send = useMutation({ mutationFn: () => post(`/interviews/${interviewId}/answers`, { question_id: q.id, response_text: text }), onSuccess: refresh });
  return (
    <Card>
      <p className="text-xs text-muted">Question {n} · <Badge>{q.type}</Badge></p>
      <CardTitle className="mt-1">{q.text}</CardTitle>
      {q.answer == null ? (
        <>
          <label htmlFor={`a-${q.id}`} className="sr-only">Your answer</label>
          <Textarea id={`a-${q.id}`} rows={6} value={text} onChange={(e) => setText(e.target.value)} placeholder="Type or dictate your answer (aim for 1-2 minutes spoken)" />
          <Button className="mt-2" onClick={() => send.mutate()} disabled={!text.trim()} loading={send.isPending}>Get feedback</Button>
          {send.isError && <div className="mt-2"><Alert tone="bad">{errorText(send.error)}</Alert></div>}
        </>
      ) : (
        <div className="space-y-2 text-sm">
          <p className="rounded bg-bg p-2">{q.answer}</p>
          <p><strong>{Math.round(q.overall ?? 0)}/100</strong> <span className="text-xs text-muted">({q.method === "ai_rubric" ? "AI rubric evaluation" : "transparent heuristic rubric"})</span></p>
          <div className="flex flex-wrap gap-2">{rubric.map((c) => <Badge key={c.id} tone={(q.criteria?.[c.id] ?? 0) >= 4 ? "good" : (q.criteria?.[c.id] ?? 0) >= 3 ? "brand" : "warn"}>{c.name}: {q.criteria?.[c.id]}/5</Badge>)}</div>
          {q.feedback && (
            <div className="grid gap-3 md:grid-cols-3">
              <div><p className="font-medium">Strengths</p><ul className="list-disc pl-5">{q.feedback.strengths.map((s) => <li key={s}>{s}</li>)}</ul></div>
              <div><p className="font-medium">Improve</p><ul className="list-disc pl-5">{q.feedback.improvements.map((s) => <li key={s}>{s}</li>)}</ul></div>
              <div><p className="font-medium">Outline to try</p><ol className="list-decimal pl-5 text-muted">{q.feedback.outline.map((s) => <li key={s}>{s}</li>)}</ol></div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
