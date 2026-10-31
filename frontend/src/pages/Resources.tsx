import { useMutation, useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { api, errorText, post } from "@/lib/api";
import { useActiveTransition, useRefreshAll } from "@/lib/hooks";
import type { ResourceItem } from "@/lib/types";
import { Alert, Badge, Button, Card, CardTitle, Empty, PageHeader, Spinner, statusTone } from "@/components/ui";

type Recs = { groups: { skill_id: string; items: ResourceItem[] }[]; discovery: { provider: string; configured: boolean; note: string | null }[] };

export function ResourcesPage() {
  const { transition: t } = useActiveTransition();
  const refresh = useRefreshAll();
  const recs = useQuery({ queryKey: ["resources", t?.id], queryFn: () => api<Recs>(`/transitions/${t!.id}/resources`), enabled: !!t });
  const again = useMutation({ mutationFn: () => post(`/transitions/${t!.id}/resources/refresh`), onSuccess: refresh });
  const verify = useMutation({ mutationFn: (id: string) => post(`/resources/${id}/verify`), onSuccess: refresh });
  if (!t) return <Empty title="Create a career goal first" />;
  if (recs.isLoading) return <Spinner />;
  return (
    <>
      <PageHeader title="Learning resources" actions={<Button variant="outline" onClick={() => again.mutate()} loading={again.isPending}>Refresh recommendations</Button>}>
        Ranked for your gaps, level, budget and preferred formats. Course details are never invented: unknown prices and durations are shown as unknown.
      </PageHeader>
      <div className="mb-4"><Alert tone="brand" title="Sources">
        Curated catalogue of reviewed links. {recs.data?.discovery.map((d) => `${d.provider}: ${d.configured ? "live search on" : "not configured (placeholder)"}`).join(" · ")}
      </Alert></div>
      {(again.isError || verify.isError) && <div className="mb-4"><Alert tone="bad">{errorText(again.error ?? verify.error)}</Alert></div>}
      {!recs.data?.groups.length ? <Empty title="No recommendations yet">Generate your plan or refresh recommendations after adding a job.</Empty> : (
        <div className="space-y-4">{recs.data.groups.map((g) => (
          <Card key={g.skill_id}>
            <CardTitle>{g.skill_id}</CardTitle>
            <ul className="space-y-3">{g.items.map((r) => (
              <li key={r.id} className="rounded-lg border border-line p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">#{r.rank}</span>
                  <a href={r.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 font-medium text-brand underline">{r.title}<ExternalLink className="size-3" aria-hidden /></a>
                  <span className="text-muted">· {r.provider}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  <Badge tone={r.cost_type === "free" ? "good" : "neutral"}>{r.cost_type === "unknown" ? "cost not verified" : r.cost_type}</Badge>
                  <Badge>{r.level}</Badge><Badge>{r.type}</Badge>{r.formats.map((f) => <Badge key={f}>{f}</Badge>)}
                  <Badge tone={statusTone(r.verification_status)}>{r.verification_status}{r.last_checked_at ? ` ${new Date(r.last_checked_at).toLocaleDateString()}` : ""}</Badge>
                  <Badge>{r.duration_minutes ? `${Math.round(r.duration_minutes / 60)} h` : "duration not verified"}</Badge>
                </div>
                <p className="mt-2 text-xs text-muted">{r.rationale}</p>
                <Button size="sm" variant="ghost" className="mt-1" onClick={() => verify.mutate(r.id)} loading={verify.isPending && verify.variables === r.id}>Check link now</Button>
              </li>
            ))}</ul>
          </Card>
        ))}</div>
      )}
    </>
  );
}
