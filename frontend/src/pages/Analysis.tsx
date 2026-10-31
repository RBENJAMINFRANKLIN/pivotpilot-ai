import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, errorText, post } from "@/lib/api";
import { useActiveTransition, useRefreshAll } from "@/lib/hooks";
import type { Analysis, Gaps } from "@/lib/types";
import { Alert, Badge, Button, Card, CardTitle, Empty, PageHeader, Progress, Score, Spinner, statusTone } from "@/components/ui";

export function AnalysisPage() {
  const { transition: t } = useActiveTransition();
  const refresh = useRefreshAll();
  const a = useQuery({ queryKey: ["analysis", t?.id], queryFn: () => api<Analysis | null>(`/transitions/${t!.id}/analysis`), enabled: !!t });
  const gaps = useQuery({ queryKey: ["gaps", t?.id], queryFn: () => api<Gaps>(`/transitions/${t!.id}/gaps`), enabled: !!t });
  const run = useMutation({ mutationFn: () => post(`/transitions/${t!.id}/analysis`, {}), onSuccess: refresh });
  if (!t) return <Empty title="Create a career goal first" />;
  if (a.isLoading) return <Spinner />;
  const d = a.data;

  return (
    <>
      <PageHeader title="Fit analysis" actions={<Button variant="outline" onClick={() => run.mutate()} loading={run.isPending}>Re-run analysis</Button>}>
        Resume quality, role fit and skill proficiency are separate measures. Keywords on a resume are evidence of a claim, not proof of skill.
      </PageHeader>
      {run.isError && <div className="mb-4"><Alert tone="bad">{errorText(run.error)}</Alert></div>}
      {!d ? <Empty title="No analysis yet" action={<Link to="/intake" className="text-brand underline">Add your resume and target job</Link>} /> : (
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <Card><Score value={d.quality_score} label="Resume document quality" sub="How clearly the resume is written (independent of the job)" /></Card>
            <Card><Score value={d.fit_score} label="Role fit (resume evidence)" sub={d.fit_breakdown.caveat} /></Card>
            <Card>
              <Score value={d.experience_alignment.score} label="Experience alignment" />
              <p className="text-xs text-muted">{d.experience_alignment.note} {d.experience_alignment.required_years != null && `Required ${d.experience_alignment.required_years}+ years; your resume shows ${d.experience_alignment.resume_years ?? "?"}.`}</p>
            </Card>
          </div>

          <Card>
            <CardTitle>Requirement by requirement</CardTitle>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted"><tr><th className="py-2 pr-3">Requirement</th><th className="pr-3">What the job says</th><th className="pr-3">Evidence on your resume</th><th>Status</th></tr></thead>
                <tbody>
                  {d.requirement_evidence.filter((e) => e.category !== "responsibility").map((e) => (
                    <tr key={e.requirement_id} className="border-t border-line align-top">
                      <td className="py-2 pr-3"><p className="font-medium">{e.label}</p><Badge tone={e.importance === "mandatory" ? "brand" : "neutral"}>{e.importance}</Badge></td>
                      <td className="pr-3 text-xs text-muted">{e.job_excerpt ? `“${e.job_excerpt}”` : "Role template"}</td>
                      <td className="pr-3 text-xs">{e.resume_excerpts.length ? e.resume_excerpts.map((x, i) => <p key={i}>“{x}”</p>) : <span className="text-muted">None found</span>}
                        {e.note && <p className="mt-1 text-muted">{e.note}</p>}</td>
                      <td><Badge tone={statusTone(e.status)}>{e.status}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardTitle>Resume quality breakdown</CardTitle>
              <ul className="space-y-2 text-sm">{d.quality_breakdown.components.map((c) => (
                <li key={c.id}>
                  <div className="flex justify-between"><span>{c.label}</span><span className="tabular-nums text-muted">{c.points}/{c.max}</span></div>
                  <Progress value={(c.points / c.max) * 100} label={c.label} />
                  <p className="text-xs text-muted">{c.detail}</p>
                </li>
              ))}</ul>
            </Card>
            <Card>
              <CardTitle>Suggestions</CardTitle>
              <ul className="list-disc space-y-1 pl-5 text-sm">{d.suggestions.map((s, i) => <li key={i}>{s.text}</li>)}</ul>
              {d.transferable_skills.length > 0 && (<>
                <CardTitle className="mt-4">Transferable strengths</CardTitle>
                <ul className="space-y-2 text-sm">{d.transferable_skills.map((s) => <li key={s.skill_id}><strong>{s.label}</strong>: {s.reason}<p className="text-xs text-muted">“{s.excerpt}”</p></li>)}</ul>
              </>)}
            </Card>
          </div>

          <Card>
            <CardTitle>Skill gaps <Badge tone={statusTone(gaps.data?.status ?? "")}>{gaps.data?.status.replace("_", " ")}</Badge></CardTitle>
            {gaps.data?.status !== "assessed" && gaps.data && <div className="mb-3"><Alert tone="warn">{gaps.data.note} <Link className="underline" to="/assessment">Take the assessment</Link>.</Alert></div>}
            <ul className="grid gap-3 sm:grid-cols-2">{gaps.data?.items.map((g) => (
              <li key={g.skill_id} className="rounded-lg border border-line p-3 text-sm">
                <div className="flex justify-between"><span className="font-medium">{g.name}</span><span className="text-xs text-muted">gap {Math.round(g.gap)}</span></div>
                <Progress value={(g.current / g.target) * 100} label={`${g.name} current vs target`} />
                <p className="mt-1 text-xs text-muted">{Math.round(g.current)}/100 ({g.basis}, {g.confidence} confidence) → target {g.target}</p>
              </li>
            ))}</ul>
            <div className="mt-4"><Link to="/assessment"><Button>Next: take the adaptive assessment</Button></Link></div>
          </Card>
        </div>
      )}
    </>
  );
}
