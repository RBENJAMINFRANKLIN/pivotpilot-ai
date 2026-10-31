import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import { api, errorText, patch, post, put, upload } from "@/lib/api";
import { useActiveTransition, useRefreshAll } from "@/lib/hooks";
import type { Job, Resume } from "@/lib/types";
import { Alert, Badge, Button, Card, CardTitle, Empty, Field, Input, PageHeader, Select, Spinner, Textarea } from "@/components/ui";
import { ConstraintFields, constraintsSchema, toPayload } from "./Goals";

export function IntakePage() {
  const { transition, isLoading } = useActiveTransition();
  if (isLoading) return <Spinner />;
  return (
    <>
      <PageHeader title="Resume & target job">Steps 1-3: tell us where you are, where you want to go, and how much time you have.</PageHeader>
      <div className="space-y-6">
        <ResumeSection />
        {transition ? (
          <>
            <JobSection transitionId={transition.id} />
            <ConstraintsSection />
          </>
        ) : <Empty title="Create a career goal first" />}
      </div>
    </>
  );
}

function ResumeSection() {
  const refresh = useRefreshAll();
  const [mode, setMode] = useState<"upload" | "paste">("upload");
  const [text, setText] = useState("");
  const versions = useQuery({ queryKey: ["resumes"], queryFn: () => api<Resume[]>("/resumes") });
  const latestId = versions.data?.[0]?.id;
  const latest = useQuery({ queryKey: ["resume", latestId], queryFn: () => api<Resume>(`/resumes/${latestId}`), enabled: !!latestId });
  const send = useMutation({
    mutationFn: (f?: File) => (f ? upload<Resume>("/resumes/upload", f) : post<Resume>("/resumes/text", { text })),
    onSuccess: () => { setText(""); refresh(); },
  });

  return (
    <Card>
      <CardTitle>1. Your resume or career details</CardTitle>
      <div className="mb-3 flex gap-2" role="tablist">
        <Button size="sm" variant={mode === "upload" ? "default" : "outline"} onClick={() => setMode("upload")} role="tab" aria-selected={mode === "upload"}>Upload PDF / DOCX</Button>
        <Button size="sm" variant={mode === "paste" ? "default" : "outline"} onClick={() => setMode("paste")} role="tab" aria-selected={mode === "paste"}>Paste or dictate text</Button>
      </div>
      {mode === "upload" ? (
        <Field label="Resume file" htmlFor="file" hint="PDF or DOCX, up to 5 MB. Scanned images are not supported.">
          <Input id="file" type="file" accept=".pdf,.docx" onChange={(e) => { const f = e.target.files?.[0]; if (f) send.mutate(f); e.target.value = ""; }} />
        </Field>
      ) : (
        <div className="space-y-2">
          <Field label="Resume or career summary" htmlFor="resume-text" hint="Include roles, dates, responsibilities, skills and education.">
            <Textarea id="resume-text" rows={8} value={text} onChange={(e) => setText(e.target.value)} />
          </Field>
          <Button onClick={() => send.mutate(undefined)} disabled={text.trim().length < 30} loading={send.isPending}>Save resume</Button>
        </div>
      )}
      {send.isPending && <Spinner label="Reading your resume" />}
      {send.isError && <div className="mt-3"><Alert tone="bad">{errorText(send.error)}</Alert></div>}
      {latest.data && <ExtractedView resume={latest.data} />}
      {versions.data && versions.data.length > 0 && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-muted">Version history ({versions.data.length})</summary>
          <ul className="mt-2 space-y-1">{versions.data.map((v) => (
            <li key={v.id}>v{v.version_number} · {v.source}{v.filename ? ` (${v.filename})` : ""} · {new Date(v.created_at).toLocaleString()}{v.is_user_edited && <Badge className="ml-2">edited</Badge>}</li>
          ))}</ul>
        </details>
      )}
    </Card>
  );
}

function ExtractedView({ resume }: { resume: Resume }) {
  const ex = resume.extracted!;
  const refresh = useRefreshAll();
  const [removed, setRemoved] = useState<string[]>([]);
  const [added, setAdded] = useState("");
  const catalogue = useQuery({ queryKey: ["skills-catalogue"], queryFn: () => api<{ id: string; skills: string[] }[]>("/resources"), staleTime: Infinity });
  const allSkills = Array.from(new Set(catalogue.data?.flatMap((r) => r.skills) ?? [])).sort();
  const save = useMutation({
    mutationFn: () => put(`/resumes/${resume.id}/extracted`, {
      experiences: ex.experiences, education: ex.education, certifications: ex.certifications, total_years_experience: ex.total_years_experience,
      skills: [...ex.skills.filter((s) => !removed.includes(s.skill_id)).map((s) => ({ skill_id: s.skill_id })), ...(added ? [{ skill_id: added }] : [])],
    }),
    onSuccess: () => { setRemoved([]); setAdded(""); refresh(); },
  });
  const dirty = removed.length > 0 || !!added;

  return (
    <div className="mt-5 space-y-3 border-t border-line pt-4 text-sm">
      <p className="text-muted">What we read from v{resume.version_number} ({resume.extraction_method.replace(":", " via ")}). Check it and correct anything wrong.</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <p className="font-medium">Experience ({ex.total_years_experience ?? "?"} years with dates)</p>
          <ul className="list-disc pl-5">{ex.experiences.map((e, i) => <li key={i}>{e.title}{e.organization ? `, ${e.organization}` : ""} <span className="text-muted">{e.start ?? ""}{e.end ? ` – ${e.end}` : ""}</span></li>)}</ul>
          {ex.experiences.length === 0 && <p className="text-muted">No dated roles recognised.</p>}
          <p className="mt-2 font-medium">Education</p>
          <ul className="list-disc pl-5">{ex.education.map((e, i) => <li key={i}>{e}</li>)}</ul>
        </div>
        <div>
          <p className="font-medium">Skills found, with the line that mentions each</p>
          <ul className="space-y-1">{ex.skills.map((s) => (
            <li key={s.skill_id} className={removed.includes(s.skill_id) ? "line-through opacity-50" : ""}>
              <span className="font-medium">{s.name}</span> <Badge>{s.evidence[0]?.context.replace("_", " ")}</Badge>
              <button className="ml-2 text-xs text-bad underline" onClick={() => setRemoved((r) => r.includes(s.skill_id) ? r.filter((x) => x !== s.skill_id) : [...r, s.skill_id])}>
                {removed.includes(s.skill_id) ? "undo" : "remove"}</button>
              <p className="text-xs text-muted">“{s.evidence[0]?.excerpt}”</p>
            </li>
          ))}</ul>
          <div className="mt-2 flex gap-2">
            <label htmlFor="add-skill" className="sr-only">Add a skill</label>
            <Select id="add-skill" value={added} onChange={(e) => setAdded(e.target.value)}>
              <option value="">Add a skill we missed…</option>
              {allSkills.filter((s) => !ex.skills.some((x) => x.skill_id === s)).map((s) => <option key={s} value={s}>{s}</option>)}
            </Select>
          </div>
        </div>
      </div>
      {dirty && <Button size="sm" onClick={() => save.mutate()} loading={save.isPending}>Save corrections as a new version</Button>}
      {save.isError && <Alert tone="bad">{errorText(save.error)}</Alert>}
    </div>
  );
}

function JobSection({ transitionId }: { transitionId: string }) {
  const refresh = useRefreshAll();
  const [mode, setMode] = useState<"url" | "paste" | "role">("paste");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const job = useQuery({ queryKey: ["job", transitionId], queryFn: () => api<Job | null>(`/transitions/${transitionId}/job`) });
  const send = useMutation({
    mutationFn: () => post<{ status: string; message: string }>(`/transitions/${transitionId}/job`, { mode, url: mode === "url" ? url : undefined, text: mode === "paste" ? text : undefined }),
    onSuccess: (r) => {
      setNotice(r.message);
      if (r.status === "needs_paste") setMode("paste");
      else refresh();
    },
  });

  return (
    <Card>
      <CardTitle>2. Target job</CardTitle>
      <div className="mb-3 flex flex-wrap gap-2">
        {(["paste", "url", "role"] as const).map((m) => (
          <Button key={m} size="sm" variant={mode === m ? "default" : "outline"} onClick={() => setMode(m)}>
            {{ paste: "Paste job description", url: "Job link", role: "Role title only" }[m]}
          </Button>
        ))}
      </div>
      {mode === "url" && <Field label="Job posting URL" htmlFor="job-url" hint="Some sites (e.g. LinkedIn) block automated reading; we will ask you to paste the text."><Input id="job-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" /></Field>}
      {mode === "paste" && <Field label="Job description" htmlFor="job-text"><Textarea id="job-text" rows={8} value={text} onChange={(e) => setText(e.target.value)} /></Field>}
      {mode === "role" && <p className="text-sm text-muted">We will use a typical requirement template for your target role. It is clearly labelled and less precise than a real posting.</p>}
      <Button className="mt-3" onClick={() => send.mutate()} loading={send.isPending} disabled={(mode === "url" && !url) || (mode === "paste" && text.trim().length < 100)}>Extract requirements</Button>
      {notice && <div className="mt-3"><Alert tone={send.data?.status === "ok" ? "good" : "warn"}>{notice}</Alert></div>}
      {send.isError && <div className="mt-3"><Alert tone="bad">{errorText(send.error)}</Alert></div>}
      {job.data && (
        <div className="mt-4 border-t border-line pt-3 text-sm">
          <p className="mb-2 text-muted">Current competency map: {job.data.title}{job.data.company ? ` at ${job.data.company}` : ""} · {job.data.source_type === "role_only" ? "role template" : "from job posting"}</p>
          <ul className="grid gap-2 sm:grid-cols-2">
            {job.data.requirements.filter((r) => r.category !== "responsibility").map((r) => (
              <li key={r.id} className="rounded-lg border border-line p-2">
                <span className="font-medium">{r.label}</span> <Badge tone={r.importance === "mandatory" ? "brand" : "neutral"}>{r.importance}</Badge> <Badge>{r.category}</Badge>
                {r.source_excerpt && <p className="mt-1 text-xs text-muted">“{r.source_excerpt}”</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

const cSchema = constraintsSchema;
type CForm = z.infer<typeof cSchema>;

function ConstraintsSection() {
  const { transition: t } = useActiveTransition();
  const refresh = useRefreshAll();
  const nav = useNavigate();
  const { register, handleSubmit, formState: { errors } } = useForm<CForm>({
    resolver: zodResolver(cSchema),
    values: t ? { deadline: t.deadline ?? "", weekly_hours: t.weekly_hours, study_days_per_week: t.study_days_per_week,
      budget_amount: t.budget_amount ?? "", budget_currency: t.budget_currency, learning_formats: t.learning_formats as CForm["learning_formats"] } : undefined,
  });
  const save = useMutation({
    mutationFn: async (v: CForm) => {
      await patch(`/transitions/${t!.id}`, { ...toPayload(v), version: t!.version });
      return post(`/transitions/${t!.id}/analysis`, {});
    },
    onSuccess: () => { refresh(); nav("/analysis"); },
  });
  if (!t) return null;
  return (
    <Card>
      <CardTitle>3. Time, budget and preferences</CardTitle>
      <form onSubmit={handleSubmit((v) => save.mutate(v))} className="space-y-4" noValidate>
        <ConstraintFields register={register as never} errors={errors as never} />
        {save.isError && <Alert tone="bad">{errorText(save.error)}</Alert>}
        <Button type="submit" loading={save.isPending}>Save and analyse my fit</Button>
      </form>
    </Card>
  );
}
