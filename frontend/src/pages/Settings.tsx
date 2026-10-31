import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api, del, errorText, post, put } from "@/lib/api";
import { useConfig, useRefreshAll, useSession } from "@/lib/hooks";
import { Alert, Button, Card, CardTitle, Field, Input, PageHeader, Select, Textarea } from "@/components/ui";

const authSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(10, "At least 10 characters"),
  display_name: z.string().max(120).optional(),
});
type AuthForm = z.infer<typeof authSchema>;

export function AuthForm({ onDone, importGuest = false }: { onDone: () => void; importGuest?: boolean }) {
  const [mode, setMode] = useState<"register" | "login">("register");
  const { data: config } = useConfig();
  const { register, handleSubmit, formState: { errors } } = useForm<AuthForm>({ resolver: zodResolver(authSchema) });
  const submit = useMutation({
    mutationFn: async (v: AuthForm) => {
      await post(`/auth/${mode}`, mode === "login" ? { email: v.email, password: v.password } : v);
      if (importGuest) await post("/auth/migrate-guest");
    },
    onSuccess: onDone,
  });
  if (config?.auth_mode === "supabase") return <Alert tone="warn">Supabase sign-in is configured for this deployment but its UI is a placeholder in the local demo. See docs/FUTURE.md.</Alert>;
  return (
    <form onSubmit={handleSubmit((v) => submit.mutate(v))} className="space-y-3" noValidate>
      <div className="flex gap-2">
        <Button type="button" size="sm" variant={mode === "register" ? "default" : "outline"} onClick={() => setMode("register")}>Create account</Button>
        <Button type="button" size="sm" variant={mode === "login" ? "default" : "outline"} onClick={() => setMode("login")}>Sign in</Button>
      </div>
      <Field label="Email" htmlFor="email" error={errors.email?.message}><Input id="email" type="email" autoComplete="email" {...register("email")} /></Field>
      <Field label="Password" htmlFor="password" error={errors.password?.message}><Input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} {...register("password")} /></Field>
      {mode === "register" && <Field label="Name (optional)" htmlFor="name"><Input id="name" {...register("display_name")} /></Field>}
      {submit.isError && <Alert tone="bad">{errorText(submit.error)}</Alert>}
      <Button type="submit" loading={submit.isPending}>{importGuest ? (mode === "register" ? "Create account & save progress" : "Sign in & save progress") : mode === "register" ? "Create account" : "Sign in"}</Button>
    </form>
  );
}

type Profile = { full_name: string | null; employment_status: string | null; current_role: string | null; current_industry: string | null;
  years_experience: number | null; education: string | null; location: string | null; preferred_formats: string[]; language: string;
  self_reported_skills: { skill_id: string; level: number }[] };

export function SettingsPage() {
  const { data: session } = useSession();
  const { data: config } = useConfig();
  const refresh = useRefreshAll();
  const [confirm, setConfirm] = useState("");
  const wipe = useMutation({ mutationFn: () => del("/workspace?confirm=DELETE"), onSuccess: refresh });
  return (
    <>
      <PageHeader title="Account & privacy" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle>{session?.kind === "guest" ? "Save My Progress" : "Account"}</CardTitle>
          {session?.kind === "guest" ? (<>
            <p className="mb-3 text-sm text-muted">{session.retention_notice} Creating an account moves everything in this guest workspace into your account in one step.</p>
            <AuthForm importGuest onDone={refresh} />
          </>) : <p className="text-sm">Signed in as <strong>{session?.user_email}</strong>. Your goals are available on any device where you sign in.</p>}
        </Card>
        <ProfileCard />
        <Card>
          <CardTitle>How your data is used</CardTitle>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            <li>Your resume and answers are stored on this PivotPilot server only, never in your browser's storage.</li>
            <li>AI provider: <strong>{config?.ai_provider === "rules" ? "none (local rules only)" : config?.ai_provider}</strong>.
              {config?.resume_sent_to_hosted_ai ? " Resume text is sent to the hosted AI provider for extraction." : " Your resume is not sent to any external AI service."}</li>
            <li>Learning resources and scores are computed by documented, versioned rules.</li>
          </ul>
        </Card>
        <Card>
          <CardTitle>Delete all my data</CardTitle>
          <p className="text-sm text-muted">Permanently deletes every goal, resume, assessment, plan, interview and application{session?.kind === "user" ? ", and your account" : ""}.</p>
          <Field label='Type DELETE to confirm' htmlFor="confirm"><Input id="confirm" value={confirm} onChange={(e) => setConfirm(e.target.value)} /></Field>
          <Button className="mt-2" variant="danger" disabled={confirm !== "DELETE"} loading={wipe.isPending} onClick={() => wipe.mutate()}>Delete everything</Button>
          {wipe.isError && <Alert tone="bad">{errorText(wipe.error)}</Alert>}
        </Card>
      </div>
    </>
  );
}

function ProfileCard() {
  const refresh = useRefreshAll();
  const profile = useQuery({ queryKey: ["profile"], queryFn: () => api<Profile>("/profile") });
  const { register, handleSubmit } = useForm<Profile>({ values: profile.data });
  const save = useMutation({ mutationFn: (v: Profile) => put("/profile", { ...v, years_experience: v.years_experience === null || (v.years_experience as unknown) === "" ? null : Number(v.years_experience), employment_status: v.employment_status || null }), onSuccess: refresh });
  return (
    <Card>
      <CardTitle>Profile</CardTitle>
      <form onSubmit={handleSubmit((v) => save.mutate(v))} className="grid gap-3 sm:grid-cols-2">
        <Field label="Name" htmlFor="pn"><Input id="pn" {...register("full_name")} /></Field>
        <Field label="Location" htmlFor="pl"><Input id="pl" {...register("location")} /></Field>
        <Field label="Current role" htmlFor="pr"><Input id="pr" {...register("current_role")} /></Field>
        <Field label="Years of experience" htmlFor="py"><Input id="py" type="number" step="0.5" {...register("years_experience")} /></Field>
        <Field label="Employment status" htmlFor="pe"><Select id="pe" {...register("employment_status")}>
          <option value="">Prefer not to say</option>{["employed", "unemployed", "student", "self_employed", "career_break", "other"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}</Select></Field>
        <Field label="Language" htmlFor="plang"><Input id="plang" {...register("language")} /></Field>
        <div className="sm:col-span-2"><Field label="Education" htmlFor="ped"><Textarea id="ped" rows={2} {...register("education")} /></Field></div>
        {save.isError && <div className="sm:col-span-2"><Alert tone="bad">{errorText(save.error)}</Alert></div>}
        <div><Button type="submit" loading={save.isPending}>Save profile</Button></div>
      </form>
    </Card>
  );
}
