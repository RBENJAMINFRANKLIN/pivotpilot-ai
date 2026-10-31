import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, errorText, post } from "@/lib/api";
import { useActiveTransition, useRefreshAll } from "@/lib/hooks";
import type { Attempt, Question } from "@/lib/types";
import { Alert, Badge, Button, Card, CardTitle, Empty, Input, PageHeader, Progress, Spinner, Textarea, cn, statusTone } from "@/components/ui";

// Answer tiles reuse the QuizBlitz colour + shape pattern so options are distinguishable without colour alone.
const TILES = [
  { cls: "bg-red-600 hover:bg-red-700", shape: "▲" },
  { cls: "bg-blue-600 hover:bg-blue-700", shape: "◆" },
  { cls: "bg-amber-600 hover:bg-amber-700", shape: "●" },
  { cls: "bg-green-700 hover:bg-green-800", shape: "■" },
  { cls: "bg-purple-700 hover:bg-purple-800", shape: "★" },
];

type History = { id: string; kind: string; status: string; started_at: string; skill_id: string | null; overall: { answered: number; correct: number } | null }[];

export function AssessmentPage() {
  const { transition: t } = useActiveTransition();
  const [params] = useSearchParams();
  const skill = params.get("skill");
  const refresh = useRefreshAll();
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [timed, setTimed] = useState(false);
  const history = useQuery({ queryKey: ["assessments", t?.id], queryFn: () => api<History>(`/transitions/${t!.id}/assessments`), enabled: !!t });
  const start = useMutation({
    mutationFn: (kind: "diagnostic" | "topic_check") => post<Attempt>(`/transitions/${t!.id}/assessments`, { kind, skill_id: kind === "topic_check" ? skill : undefined, timed, seconds_per_question: timed ? 90 : undefined }),
    onSuccess: setAttempt,
  });
  const open = useMutation({ mutationFn: (id: string) => api<Attempt>(`/assessments/${id}`), onSuccess: setAttempt });

  if (!t) return <Empty title="Create a career goal first" />;
  if (attempt) return <AttemptView attempt={attempt} onChange={(a) => { setAttempt(a); if (a.status === "completed") refresh(); }} onClose={() => { setAttempt(null); refresh(); }} />;

  const inProgress = history.data?.find((h) => h.status === "in_progress");
  return (
    <>
      <PageHeader title={skill ? "Checkpoint quiz" : "Skills assessment"}>
        An adaptive quiz built from your target job's requirements. Questions get harder or easier as you go. Answers are revealed when you finish.
      </PageHeader>
      <Card>
        <CardTitle>{skill ? `Topic check: ${skill}` : "Diagnostic assessment"}</CardTitle>
        <p className="text-sm text-muted">Every mandatory skill gets at least two questions. Professional skills such as communication are assessed in mock interviews and projects instead.</p>
        <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={timed} onChange={(e) => setTimed(e.target.checked)} />Timed mode (90 seconds per question, measured on the server)</label>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button onClick={() => start.mutate(skill ? "topic_check" : "diagnostic")} loading={start.isPending}>{inProgress && !skill ? "Continue assessment" : "Start"}</Button>
          {skill && <Link to="/assessment"><Button variant="ghost">Switch to full diagnostic</Button></Link>}
        </div>
        {start.isError && <div className="mt-3"><Alert tone="bad">{errorText(start.error)}</Alert></div>}
      </Card>
      {history.data && history.data.length > 0 && (
        <Card className="mt-4">
          <CardTitle>History</CardTitle>
          <ul className="divide-y divide-line text-sm">{history.data.map((h) => (
            <li key={h.id} className="flex items-center justify-between py-2">
              <span>{h.kind === "diagnostic" ? "Diagnostic" : `Topic check (${h.skill_id})`} · {new Date(h.started_at).toLocaleString()} <Badge tone={statusTone(h.status)}>{h.status.replace("_", " ")}</Badge></span>
              <Button size="sm" variant="ghost" onClick={() => open.mutate(h.id)}>{h.status === "completed" ? "View results" : "Continue"}</Button>
            </li>
          ))}</ul>
        </Card>
      )}
    </>
  );
}

function AttemptView({ attempt, onChange, onClose }: { attempt: Attempt; onChange: (a: Attempt) => void; onClose: () => void }) {
  const answer = useMutation({
    mutationFn: (response: unknown) => post<Attempt>(`/assessments/${attempt.id}/answer`, { question_id: attempt.question!.id, response }),
    onSuccess: onChange,
  });
  const finish = useMutation({ mutationFn: () => post<Attempt>(`/assessments/${attempt.id}/finish`), onSuccess: onChange });
  const p = attempt.progress;

  if (attempt.status === "completed" && attempt.results) return <Results attempt={attempt} onClose={onClose} />;
  const q = attempt.question;
  return (
    <>
      <PageHeader title={attempt.kind === "diagnostic" ? "Skills assessment" : "Checkpoint quiz"}
        actions={<Button variant="ghost" onClick={() => finish.mutate()} loading={finish.isPending}>Finish now</Button>}>
        Question {p.answered + 1} of up to {p.budget} · {p.skills_covered}/{p.skills_total} skills covered
      </PageHeader>
      <Progress value={(p.answered / p.budget) * 100} label="Assessment progress" className="mb-4" />
      {finish.isError && <div className="mb-3"><Alert tone="warn">{errorText(finish.error)}</Alert></div>}
      {q ? <QuestionCard key={q.id} q={q} timeLeft={attempt.time_left} onSubmit={(r) => answer.mutate(r)} busy={answer.isPending} /> : <Spinner />}
      {answer.isError && <div className="mt-3"><Alert tone="bad">{errorText(answer.error)}</Alert></div>}
    </>
  );
}

function QuestionCard({ q, timeLeft, onSubmit, busy }: { q: Question; timeLeft: number | null; onSubmit: (r: unknown) => void; busy: boolean }) {
  const [multi, setMulti] = useState<number[]>([]);
  const [text, setText] = useState("");
  const [left, setLeft] = useState(timeLeft);
  useEffect(() => {
    if (left == null) return;
    const id = setInterval(() => setLeft((v) => (v == null ? v : Math.max(0, v - 1))), 1000);
    return () => clearInterval(id);
  }, [left == null]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Card>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        <Badge tone="brand">{q.skill_name}</Badge><Badge>{q.topic}</Badge><Badge>{["", "easy", "medium", "hard"][q.difficulty]}</Badge>
        {left != null && <span className={cn("ml-auto font-semibold tabular-nums", left <= 10 && "text-bad")} role="timer" aria-live="polite">{left}s</span>}
      </div>
      <h2 className="text-lg font-medium">{q.prompt}</h2>
      {q.code && <pre className="mt-3 overflow-x-auto rounded-lg bg-ink p-3 text-sm text-white"><code>{q.code}</code></pre>}
      {q.free_text ? (
        <form className="mt-4 space-y-2" onSubmit={(e) => { e.preventDefault(); onSubmit(text); }}>
          {q.type === "practical" ? <Textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} aria-label="Your answer" />
            : <Input value={text} onChange={(e) => setText(e.target.value)} aria-label="Your answer" placeholder="Type the exact output" />}
          <Button type="submit" loading={busy} disabled={!text.trim()}>Submit answer</Button>
        </form>
      ) : q.select_multiple ? (
        <div className="mt-4 space-y-2">
          <p className="text-sm text-muted">Select all that apply.</p>
          <div className="grid gap-2 sm:grid-cols-2">{q.choices.map((c, i) => (
            <button key={i} type="button" aria-pressed={multi.includes(i)} onClick={() => setMulti((m) => m.includes(i) ? m.filter((x) => x !== i) : [...m, i])}
              className={cn("flex items-center gap-3 rounded-xl p-4 text-left text-white", TILES[i % 5].cls, multi.includes(i) ? "ring-4 ring-ink/40" : "opacity-90")}>
              <span aria-hidden>{TILES[i % 5].shape}</span><span>{c}</span>{multi.includes(i) && <span className="ml-auto" aria-hidden>✓</span>}
            </button>
          ))}</div>
          <Button onClick={() => onSubmit(multi.sort())} disabled={!multi.length} loading={busy}>Submit answer</Button>
        </div>
      ) : (
        <div className="mt-4 grid gap-2 sm:grid-cols-2">{q.choices.map((c, i) => (
          <button key={i} type="button" disabled={busy} onClick={() => onSubmit(i)}
            className={cn("flex items-center gap-3 rounded-xl p-4 text-left text-white disabled:opacity-60", TILES[i % 5].cls)}>
            <span aria-hidden>{TILES[i % 5].shape}</span><span>{c}</span>
          </button>
        ))}</div>
      )}
    </Card>
  );
}

type Review = (Question & { your_answer: unknown; correct_answer: unknown; explanation: string; is_correct: boolean | null; timed_out: boolean; validation_source: string })[];

function Results({ attempt, onClose }: { attempt: Attempt; onClose: () => void }) {
  const r = attempt.results!;
  const review = useQuery({ queryKey: ["review", attempt.id], queryFn: () => api<Review>(`/assessments/${attempt.id}/review`) });
  const fmt = (q: Question, a: unknown) => Array.isArray(a) ? a.map((i) => q.choices[i]).join(", ") : typeof a === "number" ? q.choices[a] : a && typeof a === "object" ? (a as { accepted: string[] }).accepted.join(" or ") : String(a ?? "–");
  return (
    <>
      <PageHeader title="Your results" actions={<Button onClick={onClose}>Done</Button>}>
        {r.overall.correct} of {r.overall.answered} correct. {r.disclaimer}
      </PageHeader>
      {r.plan_revision && <div className="mb-4"><Alert tone="good" title={`Your plan was updated (version ${r.plan_revision.version})`}>{r.plan_revision.reasons.join("; ")}. <Link className="underline" to="/plan">See the plan</Link></Alert></div>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(r.skills).map(([sid, s]) => (
          <Card key={sid}>
            <div className="flex justify-between"><p className="font-semibold">{s.name}</p><Badge tone={statusTone(s.confidence)}>{s.confidence} confidence</Badge></div>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{s.score == null ? "Not enough evidence" : `${Math.round(s.score)}/100`}</p>
            <p className="text-xs text-muted">{s.level.replace("_", " ")} · {s.answered} answered · accuracy {s.accuracy == null ? "–" : `${Math.round(s.accuracy * 100)}%`}</p>
            <p className="text-xs text-muted">By difficulty: {Object.entries(s.difficulty).map(([d, v]) => `${["", "easy", "medium", "hard"][+d]} ${v.correct}/${v.asked}`).join(" · ") || "–"}</p>
          </Card>
        ))}
      </div>
      {r.uncovered.length > 0 && <div className="mt-4"><Alert tone="brand" title="Not covered by this quiz">{r.uncovered.map((u) => `${u.name}: ${u.reason}`).join(" ")}</Alert></div>}
      <Card className="mt-4">
        <CardTitle>Review answers</CardTitle>
        {review.data?.map((q) => (
          <details key={q.id} className="border-t border-line py-2 text-sm">
            <summary className="cursor-pointer">{q.is_correct ? "✓" : q.is_correct === false ? "✗" : "•"} {q.prompt}</summary>
            {q.code && <pre className="mt-2 overflow-x-auto rounded bg-ink p-2 text-xs text-white">{q.code}</pre>}
            <p className="mt-1">Your answer: {q.timed_out ? "time ran out" : fmt(q, q.your_answer)}</p>
            <p>Correct answer: {fmt(q, q.correct_answer)}</p>
            <p className="text-muted">{q.explanation}</p>
            <p className="text-xs text-muted">Source: {q.validation_source}</p>
          </details>
        ))}
      </Card>
    </>
  );
}
