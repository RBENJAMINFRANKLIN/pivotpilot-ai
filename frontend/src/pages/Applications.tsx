import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api, del, errorText, patch, post } from "@/lib/api";
import { useRefreshAll } from "@/lib/hooks";
import type { Application } from "@/lib/types";
import { Alert, Badge, Button, Card, CardTitle, Empty, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";

const STATUSES = ["saved", "applied", "screening", "interview", "offer", "rejected", "withdrawn", "no_response"] as const;
const schema = z.object({
  company: z.string().min(1, "Required").max(200),
  role_title: z.string().min(1, "Required").max(200),
  role_category: z.string().max(80).optional(),
  company_size: z.enum(["startup", "small", "medium", "large", "enterprise", "unknown"]),
  source: z.string().max(60),
  url: z.union([z.literal(""), z.string().url("Enter a full link starting with https://")]).optional(),
  status: z.enum(STATUSES),
});
type Form = z.infer<typeof schema>;
type Analytics = { total: number; sent: number; insights: string[]; min_sample: number;
  by_role_category: { key: string; sent: number; responses: number; positive: number; response_rate: number; enough_data: boolean }[] };

export function ApplicationsPage() {
  const refresh = useRefreshAll();
  const apps = useQuery({ queryKey: ["applications"], queryFn: () => api<Application[]>("/applications") });
  const stats = useQuery({ queryKey: ["applications-analytics"], queryFn: () => api<Analytics>("/applications/analytics") });
  const { register, handleSubmit, reset, formState: { errors } } = useForm<Form>({
    resolver: zodResolver(schema), defaultValues: { company_size: "unknown", source: "job board", status: "applied" },
  });
  const add = useMutation({ mutationFn: (v: Form) => post("/applications", { ...v, url: v.url || null }), onSuccess: () => { reset(); refresh(); } });
  const upd = useMutation({ mutationFn: ({ a, status }: { a: Application; status: string }) => patch(`/applications/${a.id}`, { status, version: a.version }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (id: string) => del(`/applications/${id}`), onSuccess: refresh });

  return (
    <>
      <PageHeader title="Applications">Track where you applied. PivotPilot learns which kinds of roles respond, cautiously, and shows the sample sizes.</PageHeader>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardTitle>Pipeline</CardTitle>
          {apps.isLoading ? <Spinner /> : !apps.data?.length ? <Empty title="No applications yet">Add one with the form, or say "I applied for … at …" in the command box.</Empty> : (
            <div className="overflow-x-auto"><table className="w-full text-left text-sm">
              <thead className="text-xs text-muted"><tr><th className="py-2">Role</th><th>Category</th><th>Status</th><th>History</th><th /></tr></thead>
              <tbody>{apps.data.map((a) => (
                <tr key={a.id} className="border-t border-line align-top">
                  <td className="py-2 pr-2"><p className="font-medium">{a.role_title}</p><p className="text-xs text-muted">{a.company}{a.applied_at ? ` · applied ${a.applied_at}` : ""}</p></td>
                  <td className="pr-2 text-xs">{a.role_category}<br /><span className="text-muted">{a.company_size} · {a.source}</span></td>
                  <td className="pr-2"><Select aria-label={`Status for ${a.company}`} value={a.status} onChange={(e) => upd.mutate({ a, status: e.target.value })}>{STATUSES.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}</Select></td>
                  <td className="pr-2 text-xs text-muted">{a.history.map((h) => h.to.replace("_", " ")).join(" → ")}</td>
                  <td><Button size="sm" variant="ghost" onClick={() => remove.mutate(a.id)} aria-label={`Delete ${a.company}`}>Delete</Button></td>
                </tr>
              ))}</tbody>
            </table></div>
          )}
          {(upd.isError || remove.isError) && <Alert tone="bad">{errorText(upd.error ?? remove.error)}</Alert>}
        </Card>
        <Card>
          <CardTitle>What is working</CardTitle>
          {stats.data && (<>
            <ul className="list-disc space-y-1 pl-5 text-sm">{stats.data.insights.map((s) => <li key={s}>{s}</li>)}</ul>
            <ul className="mt-3 space-y-1 text-xs">{stats.data.by_role_category.map((g) => (
              <li key={g.key} className="flex justify-between gap-2"><span>{g.key}</span><span className="tabular-nums">{g.responses}/{g.sent} replied {g.enough_data ? "" : <Badge>small sample</Badge>}</span></li>
            ))}</ul>
          </>)}
        </Card>
      </div>
      <Card className="mt-4">
        <CardTitle>Add an application</CardTitle>
        <form onSubmit={handleSubmit((v) => add.mutate(v))} className="grid gap-4 sm:grid-cols-3" noValidate>
          <Field label="Company" htmlFor="company" error={errors.company?.message}><Input id="company" {...register("company")} /></Field>
          <Field label="Role title" htmlFor="role" error={errors.role_title?.message}><Input id="role" {...register("role_title")} /></Field>
          <Field label="Role category" htmlFor="cat" hint="Used to compare response rates, e.g. 'data analyst'"><Input id="cat" {...register("role_category")} /></Field>
          <Field label="Company size" htmlFor="size"><Select id="size" {...register("company_size")}>{["unknown", "startup", "small", "medium", "large", "enterprise"].map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Source" htmlFor="source"><Input id="source" {...register("source")} /></Field>
          <Field label="Status" htmlFor="status"><Select id="status" {...register("status")}>{STATUSES.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}</Select></Field>
          <div className="sm:col-span-3"><Field label="Job link (optional)" htmlFor="url" error={errors.url?.message}><Input id="url" {...register("url")} /></Field></div>
          {add.isError && <div className="sm:col-span-3"><Alert tone="bad">{errorText(add.error)}</Alert></div>}
          <div><Button type="submit" loading={add.isPending}>Add</Button></div>
        </form>
      </Card>
    </>
  );
}
