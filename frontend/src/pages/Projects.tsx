import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, errorText, patch, post } from "@/lib/api";
import { useActiveTransition, useRefreshAll } from "@/lib/hooks";
import type { Project } from "@/lib/types";
import { Alert, Badge, Button, Card, CardTitle, Empty, Input, PageHeader, Select, Spinner, statusTone } from "@/components/ui";

export function ProjectsPage() {
  const { transition: t } = useActiveTransition();
  const projects = useQuery({ queryKey: ["projects", t?.id], queryFn: () => api<Project[]>(`/transitions/${t!.id}/projects`), enabled: !!t });
  if (!t) return <Empty title="Create a career goal first" />;
  if (projects.isLoading) return <Spinner />;
  return (
    <>
      <PageHeader title="Portfolio projects">Projects that produce real evidence for the skills your target job needs.</PageHeader>
      {!projects.data?.length ? <Empty title="No project suggestions yet">Add a job description first.</Empty> :
        <div className="space-y-4">{projects.data.map((p) => <ProjectCard key={p.id} p={p} />)}</div>}
    </>
  );
}

function ProjectCard({ p }: { p: Project }) {
  const refresh = useRefreshAll();
  const [scores, setScores] = useState<Record<string, number>>({});
  const [link, setLink] = useState(p.repo_url ?? "");
  const upd = useMutation({ mutationFn: (body: object) => patch(`/projects/${p.id}`, body), onSuccess: refresh });
  const ev = useMutation({ mutationFn: (body: object) => post(`/projects/${p.id}/evidence`, body), onSuccess: () => { setScores({}); refresh(); } });
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <CardTitle>{p.title}</CardTitle>
        <Select aria-label="Project status" className="w-40" value={p.status} onChange={(e) => upd.mutate({ status: e.target.value })}>
          {["suggested", "in_progress", "completed", "dropped"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
        </Select>
      </div>
      <p className="text-sm">{p.problem_statement}</p>
      <p className="mt-1 text-xs text-muted">{p.rationale}</p>
      <div className="mt-2 flex flex-wrap gap-1">{p.required_skills.map((s) => <Badge key={s} tone="brand">{s}</Badge>)}</div>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div>
          <p className="text-sm font-medium">Milestones</p>
          <ul className="mt-1 space-y-1 text-sm">{p.milestones.map((m, i) => (
            <li key={i}><label className="flex items-center gap-2"><input type="checkbox" checked={m.done} onChange={() => upd.mutate({ milestone_index: i, milestone_done: !m.done })} />{m.title}</label></li>
          ))}</ul>
          <p className="mt-3 text-sm font-medium">Deliverables</p>
          <ul className="list-disc pl-5 text-sm">{p.deliverables.map((d) => <li key={d}>{d}</li>)}</ul>
          <p className="mt-3 text-sm font-medium">Resume line (fill in your real results)</p>
          <p className="rounded bg-bg p-2 text-xs">{p.resume_evidence}</p>
        </div>
        <div>
          <p className="text-sm font-medium">Self-assessment against the rubric (1 = not yet, 4 = strong)</p>
          <ul className="mt-1 space-y-2 text-sm">{p.rubric.map((c) => (
            <li key={c.id}>
              <label htmlFor={`${p.id}-${c.id}`} className="block">{c.name} <span className="text-xs text-muted">{c.description}</span></label>
              <Select id={`${p.id}-${c.id}`} value={scores[c.id] ?? ""} onChange={(e) => setScores((s) => ({ ...s, [c.id]: Number(e.target.value) }))}>
                <option value="">Choose…</option>{[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
              </Select>
            </li>
          ))}</ul>
          <Button size="sm" className="mt-2" disabled={Object.keys(scores).length < p.rubric.length} loading={ev.isPending}
            onClick={() => ev.mutate({ kind: "rubric_self_assessment", rubric_scores: scores })}>Record self-assessment</Button>
          <div className="mt-3 flex gap-2">
            <Input aria-label="Repository or demo link" placeholder="https://github.com/…" value={link} onChange={(e) => setLink(e.target.value)} />
            <Button size="sm" variant="outline" onClick={() => upd.mutate({ repo_url: link })} disabled={!/^https?:\/\//.test(link)}>Save link</Button>
          </div>
          {p.evidence.length > 0 && <ul className="mt-3 text-xs text-muted">{p.evidence.map((e) => <li key={e.id}>{e.kind.split("_").join(" ")}{e.score != null ? `: ${e.score}/100` : ""} · {new Date(e.created_at).toLocaleDateString()}</li>)}</ul>}
          <p className="mt-2 text-xs text-muted">Self-assessments count as project evidence in readiness, never as quiz-assessed skill.</p>
        </div>
      </div>
      {(upd.isError || ev.isError) && <div className="mt-3"><Alert tone="bad">{errorText(upd.error ?? ev.error)}</Alert></div>}
      <Badge className="mt-3" tone={statusTone(p.status)}>{p.status.replace("_", " ")}</Badge>
    </Card>
  );
}
