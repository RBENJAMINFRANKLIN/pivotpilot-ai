import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import type { GapItem, Readiness } from "@/lib/types";
import { Alert, Badge, Card, CardTitle, Empty, PageHeader, Progress, Score, Spinner, statusTone } from "@/components/ui";

type Dashboard = {
  is_demo: boolean;
  transition: null | { id: string; title: string; current_role: string | null; target_role: string; deadline: string | null; weekly_hours: number };
  next_actions: { id: string; label: string; route: string }[];
  resume: null | { version: number; created_at: string; source: string };
  scores?: { resume_quality: number | null; role_fit: number | null; readiness: Readiness };
  gaps?: { status: string; items: GapItem[] };
  proficiency?: { skill_id: string; name: string; latest: { score: number | null; confidence: string } }[];
  plan?: null | { version: number; status: string; plan_status: string; weeks: number; current_week: number; conflict: boolean; progress_percent: number;
    this_week: { planned_minutes: number; completed_minutes: number; capacity_minutes: number };
    upcoming_checkpoints: { skill_id: string; name: string; date: string }[] };
  weekly_hours?: { week: string; hours: number }[];
  projects?: { id: string; title: string; status: string; next_milestone: string | null; done: number; total: number }[];
  interviews?: { id: string; status: string; overall_score: number | null; started_at: string }[];
  applications: { total: number; pipeline: Record<string, number>; insights: string[] };
};

const COMPONENT_LABEL: Record<string, string> = {
  resume_quality: "Resume quality", role_fit: "Role fit", assessed_proficiency: "Assessed skills",
  experience_alignment: "Experience", project_evidence: "Projects", interview_performance: "Interviews",
};

export function DashboardPage() {
  const { data: d, isLoading, error } = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dashboard>("/dashboard") });
  if (isLoading) return <Spinner />;
  if (error || !d) return <Alert tone="bad">Could not load your dashboard.</Alert>;
  const t = d.transition;

  return (
    <>
      <PageHeader title={t ? t.title : "Welcome"}>
        {t ? <>{t.current_role ?? "Current role"} → <strong>{t.target_role}</strong>{t.deadline ? ` · deadline ${t.deadline}` : ""} · {t.weekly_hours} h/week</> : "Start by creating a career goal."}
      </PageHeader>
      {d.is_demo && <div className="mb-4"><Alert tone="warn" title="Demo workspace">This is fictional sample data so you can explore every screen.</Alert></div>}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardTitle>Next recommended actions</CardTitle>
          {d.next_actions.length ? (
            <ol className="space-y-2">
              {d.next_actions.map((a, i) => (
                <li key={a.id}>
                  <Link to={a.route} className="flex items-center gap-3 rounded-lg border border-line p-3 hover:bg-bg">
                    <span className="flex size-6 items-center justify-center rounded-full bg-brand-soft text-xs font-semibold text-brand">{i + 1}</span>
                    <span className="flex-1 text-sm">{a.label}</span><ArrowRight className="size-4 text-muted" aria-hidden />
                  </Link>
                </li>
              ))}
            </ol>
          ) : <p className="text-sm text-muted">You are up to date.</p>}
        </Card>
        <Card>
          <CardTitle>Readiness</CardTitle>
          {d.scores ? (
            <>
              <Score value={d.scores.readiness.overall} label="Overall preparation" sub={d.scores.readiness.provisional ? "Provisional until you complete the assessment" : undefined} />
              <ul className="mt-3 space-y-1 text-sm">
                {Object.keys(d.scores.readiness.weights).map((k) => (
                  <li key={k} className="flex justify-between"><span className="text-muted">{COMPONENT_LABEL[k]}</span>
                    <span className="tabular-nums">{d.scores!.readiness.components[k] ? Math.round(d.scores!.readiness.components[k].score) : "not yet"}</span></li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted">{d.scores.readiness.caveat}</p>
            </>
          ) : <p className="text-sm text-muted">Appears after your first analysis.</p>}
        </Card>
      </div>

      {t && (
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          <Card>
            <CardTitle>Resume</CardTitle>
            {d.resume ? (
              <div className="grid grid-cols-2 gap-3">
                <Score value={d.scores?.resume_quality} label="Resume quality" />
                <Score value={d.scores?.role_fit} label="Role fit (evidence)" />
                <p className="col-span-2 text-xs text-muted">Latest version: v{d.resume.version} ({d.resume.source}), {new Date(d.resume.created_at).toLocaleDateString()}</p>
              </div>
            ) : <Empty title="No resume yet" action={<Link className="text-brand underline" to="/intake">Add your resume</Link>} />}
          </Card>
          <Card className="lg:col-span-2">
            <CardTitle>Assessed skills</CardTitle>
            {d.proficiency?.length ? (
              <div className="h-56">
                <ResponsiveContainer>
                  <BarChart data={d.proficiency.map((p) => ({ name: p.name, score: p.latest.score ?? 0, conf: p.latest.confidence }))} margin={{ left: -20 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-15} height={50} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v, _n, item) => [`${v}/100 (${(item.payload as { conf: string }).conf} confidence)`, "Assessed"]} />
                    <Bar dataKey="score" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : <Empty title="No assessed skills yet" action={<Link className="text-brand underline" to="/assessment">Take the assessment</Link>}>Scores here only come from quizzes, never from keywords on your resume.</Empty>}
          </Card>
        </div>
      )}

      {t && (
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardTitle>Skill gaps <Badge tone={statusTone(d.gaps?.status ?? "")}>{d.gaps?.status.replace("_", " ")}</Badge></CardTitle>
            {d.gaps?.items.length ? (
              <ul className="space-y-3">
                {d.gaps.items.map((g) => (
                  <li key={g.skill_id}>
                    <div className="flex items-center justify-between text-sm">
                      <span>{g.name} <Badge tone={g.importance === "mandatory" ? "brand" : "neutral"}>{g.importance}</Badge></span>
                      <span className="text-xs text-muted">{Math.round(g.current)} → {g.target} ({g.basis})</span>
                    </div>
                    <Progress value={(g.current / g.target) * 100} label={`${g.name} progress to target`} />
                    {g.job_excerpt && <p className="mt-1 text-xs text-muted">Job: “{g.job_excerpt}”</p>}
                  </li>
                ))}
              </ul>
            ) : <Empty title="No gaps yet">Add a job description to see gaps.</Empty>}
          </Card>
          <Card>
            <CardTitle>Learning plan</CardTitle>
            {d.plan ? (
              <div className="space-y-3 text-sm">
                <p>Version {d.plan.version} <Badge tone={statusTone(d.plan.status)}>{d.plan.status}</Badge> {d.plan.plan_status === "paused" && <Badge tone="warn">paused</Badge>}</p>
                <div><p className="text-xs text-muted">Overall progress</p><Progress value={d.plan.progress_percent} label="Plan progress" /></div>
                <div>
                  <p className="text-xs text-muted">This week (week {d.plan.current_week} of {d.plan.weeks})</p>
                  <p className="tabular-nums">{Math.round(d.plan.this_week.completed_minutes / 6) / 10} of {Math.round(d.plan.this_week.planned_minutes / 6) / 10} h done · capacity {d.plan.this_week.capacity_minutes / 60} h</p>
                </div>
                {d.plan.conflict && <Alert tone="warn">Your deadline is not achievable at this pace. See the plan for options.</Alert>}
                {d.plan.upcoming_checkpoints.length > 0 && (
                  <div><p className="text-xs text-muted">Upcoming assessments</p>
                    <ul>{d.plan.upcoming_checkpoints.map((c) => <li key={c.skill_id}>{c.name} checkpoint · {c.date}</li>)}</ul></div>
                )}
              </div>
            ) : <Empty title="No plan yet" action={<Link className="text-brand underline" to="/plan">Create your plan</Link>} />}
          </Card>
        </div>
      )}

      {t && (
        <div className="mt-4 grid gap-4 lg:grid-cols-4">
          <Card className="lg:col-span-2">
            <CardTitle>Study hours (last 8 weeks)</CardTitle>
            {d.weekly_hours?.length ? (
              <div className="h-40"><ResponsiveContainer><BarChart data={d.weekly_hours} margin={{ left: -20 }}>
                <XAxis dataKey="week" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} /><Tooltip /><Bar dataKey="hours" fill="#15803d" radius={[4, 4, 0, 0]} />
              </BarChart></ResponsiveContainer></div>
            ) : <p className="text-sm text-muted">Tick off plan tasks to track your hours.</p>}
          </Card>
          <Card>
            <CardTitle>Projects</CardTitle>
            {d.projects?.length ? d.projects.map((p) => (
              <div key={p.id} className="mb-2 text-sm"><p className="font-medium">{p.title}</p>
                <p className="text-xs text-muted">{p.done}/{p.total} milestones{p.next_milestone ? ` · next: ${p.next_milestone}` : ""}</p></div>
            )) : <p className="text-sm text-muted">Suggested after your analysis.</p>}
          </Card>
          <Card>
            <CardTitle>Interviews & applications</CardTitle>
            <p className="text-sm">{d.interviews?.filter((i) => i.status === "completed").length ?? 0} mock interviews completed
              {d.interviews?.[0]?.overall_score != null && <> · last score {Math.round(d.interviews[0].overall_score)}</>}</p>
            <ul className="mt-2 grid grid-cols-2 gap-1 text-xs">
              {Object.entries(d.applications.pipeline).filter(([, n]) => n > 0).map(([s, n]) => <li key={s}><Badge>{s.replace("_", " ")}</Badge> {n}</li>)}
            </ul>
            {d.applications.total === 0 && <p className="text-sm text-muted">No applications tracked yet.</p>}
          </Card>
        </div>
      )}
    </>
  );
}
