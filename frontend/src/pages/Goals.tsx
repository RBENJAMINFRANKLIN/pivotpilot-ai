import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { errorText, post } from "@/lib/api";
import { useRefreshAll, useTransitions } from "@/lib/hooks";
import type { Transition } from "@/lib/types";
import { Alert, Badge, Button, Card, CardTitle, Empty, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";

const FORMATS = ["video", "reading", "interactive", "practice", "project"] as const;

export const constraintsSchema = z.object({
  deadline: z.string().optional().refine((v) => !v || new Date(v) > new Date(), "Choose a future date"),
  weekly_hours: z.coerce.number().min(1, "At least 1 hour").max(80, "At most 80 hours"),
  study_days_per_week: z.coerce.number().int().min(1).max(7),
  budget_amount: z.union([z.literal(""), z.coerce.number().min(0, "Cannot be negative")]).optional(),
  budget_currency: z.string().length(3, "Use a 3-letter code like USD"),
  learning_formats: z.array(z.enum(FORMATS)).default([]),
});

const goalSchema = z.object({
  title: z.string().min(1, "Give the goal a name").max(200),
  current_role: z.string().max(160).optional(),
  current_industry: z.string().max(160).optional(),
  employment_status: z.enum(["", "employed", "unemployed", "student", "self_employed", "career_break", "other"]).optional(),
  target_role: z.string().min(2, "Enter the role you want").max(160),
  target_location: z.string().max(160).optional(),
}).merge(constraintsSchema);
type GoalForm = z.infer<typeof goalSchema>;

export function toPayload(v: Partial<GoalForm>) {
  return {
    ...v,
    deadline: v.deadline || null,
    budget_amount: v.budget_amount === "" || v.budget_amount === undefined ? null : Number(v.budget_amount),
    employment_status: v.employment_status || null,
    budget_currency: v.budget_currency?.toUpperCase(),
  };
}

export function ConstraintFields({ register, errors }: { register: ReturnType<typeof useForm<GoalForm>>["register"]; errors: Record<string, { message?: string } | undefined> }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label="Preparation deadline" htmlFor="deadline" error={errors.deadline?.message}><Input id="deadline" type="date" {...register("deadline")} /></Field>
      <Field label="Hours per week you can study" htmlFor="weekly_hours" error={errors.weekly_hours?.message}><Input id="weekly_hours" type="number" step="0.5" {...register("weekly_hours")} /></Field>
      <Field label="Study days per week" htmlFor="days" error={errors.study_days_per_week?.message}><Input id="days" type="number" {...register("study_days_per_week")} /></Field>
      <div className="grid grid-cols-3 gap-2">
        <div className="col-span-2"><Field label="Budget" htmlFor="budget" hint="0 = free resources only" error={errors.budget_amount?.message}><Input id="budget" type="number" step="1" {...register("budget_amount")} /></Field></div>
        <Field label="Currency" htmlFor="cur" error={errors.budget_currency?.message}><Input id="cur" maxLength={3} {...register("budget_currency")} /></Field>
      </div>
      <fieldset className="sm:col-span-2">
        <legend className="mb-1 text-sm font-medium">Preferred learning formats</legend>
        <div className="flex flex-wrap gap-3">{FORMATS.map((f) => (
          <label key={f} className="flex items-center gap-1 text-sm"><input type="checkbox" value={f} {...register("learning_formats")} />{f}</label>
        ))}</div>
      </fieldset>
    </div>
  );
}

export function GoalsPage() {
  const { data, isLoading } = useTransitions();
  const refresh = useRefreshAll();
  const { register, handleSubmit, reset, formState: { errors } } = useForm<GoalForm>({
    resolver: zodResolver(goalSchema),
    defaultValues: { weekly_hours: 6, study_days_per_week: 5, budget_currency: "USD", learning_formats: [] },
  });
  const create = useMutation({ mutationFn: (v: GoalForm) => post<Transition>("/transitions", toPayload(v)), onSuccess: () => { reset(); refresh(); } });
  const act = useMutation({ mutationFn: ({ id, op }: { id: string; op: string }) => post(`/transitions/${id}/${op}`), onSuccess: refresh });

  return (
    <>
      <PageHeader title="Career goals">Keep several goals; one is active at a time. Switching keeps each goal's history.</PageHeader>
      {isLoading ? <Spinner /> : data?.length ? (
        <div className="mb-6 grid gap-3 sm:grid-cols-2">
          {data.map((t) => (
            <Card key={t.id}>
              <div className="flex items-start justify-between gap-2">
                <div><p className="font-semibold">{t.title}</p><p className="text-sm text-muted">{t.current_role ? `${t.current_role} → ` : ""}{t.target_role}</p></div>
                {t.is_active ? <Badge tone="brand">active</Badge> : t.archived_at ? <Badge>archived</Badge> : null}
              </div>
              <p className="mt-2 text-xs text-muted">{t.weekly_hours} h/week{t.deadline ? ` · deadline ${t.deadline}` : ""}{t.budget_amount != null ? ` · budget ${t.budget_amount} ${t.budget_currency}` : ""}</p>
              <div className="mt-3 flex gap-2">
                {!t.is_active && !t.archived_at && <Button size="sm" onClick={() => act.mutate({ id: t.id, op: "activate" })}>Make active</Button>}
                {!t.archived_at && <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: t.id, op: "archive" })}>Archive</Button>}
                {t.archived_at && <Button size="sm" variant="outline" onClick={() => act.mutate({ id: t.id, op: "restore" })}>Restore</Button>}
              </div>
            </Card>
          ))}
        </div>
      ) : <div className="mb-6"><Empty title="No goals yet">Create your first career goal below.</Empty></div>}
      {act.isError && <Alert tone="bad">{errorText(act.error)}</Alert>}

      <Card>
        <CardTitle>New career goal</CardTitle>
        <form onSubmit={handleSubmit((v) => create.mutate(v))} className="space-y-4" noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Goal name" htmlFor="title" error={errors.title?.message}><Input id="title" placeholder="e.g. Teacher to data analyst" {...register("title")} /></Field>
            <Field label="Target role" htmlFor="target_role" error={errors.target_role?.message}><Input id="target_role" placeholder="e.g. Junior Data Analyst" {...register("target_role")} /></Field>
            <Field label="Current role" htmlFor="current_role"><Input id="current_role" {...register("current_role")} /></Field>
            <Field label="Current industry" htmlFor="industry"><Input id="industry" {...register("current_industry")} /></Field>
            <Field label="Employment status" htmlFor="emp">
              <Select id="emp" {...register("employment_status")}>
                <option value="">Prefer not to say</option><option value="employed">Employed</option><option value="unemployed">Not working</option>
                <option value="student">Student</option><option value="self_employed">Self-employed</option><option value="career_break">Career break</option><option value="other">Other</option>
              </Select>
            </Field>
            <Field label="Target location (optional)" htmlFor="loc"><Input id="loc" {...register("target_location")} /></Field>
          </div>
          <ConstraintFields register={register} errors={errors as never} />
          {create.isError && <Alert tone="bad">{errorText(create.error)}</Alert>}
          <Button type="submit" loading={create.isPending}>Create goal</Button>
        </form>
      </Card>
    </>
  );
}
