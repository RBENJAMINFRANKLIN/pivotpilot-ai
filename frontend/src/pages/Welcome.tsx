import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { errorText, post } from "@/lib/api";
import { useConfig, useRefreshAll } from "@/lib/hooks";
import { Alert, Button, Card } from "@/components/ui";
import { AuthForm } from "./Settings";

export function WelcomePage() {
  const refresh = useRefreshAll();
  const { data: config } = useConfig();
  const [showLogin, setShowLogin] = useState(false);
  const guest = useMutation({ mutationFn: () => post("/session/guest"), onSuccess: refresh });
  const demo = useMutation({ mutationFn: () => post("/demo/start"), onSuccess: refresh });

  return (
    <main className="mx-auto flex min-h-full max-w-3xl flex-col justify-center p-6">
      <h1 className="text-3xl font-semibold">PivotPilot <span className="text-brand">AI</span></h1>
      <p className="mt-2 text-lg text-muted">
        Plan your move into a new role: compare your resume with real job requirements, check your skills with an adaptive quiz,
        and follow a weekly plan that fits the hours you actually have.
      </p>
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        <Card>
          <h2 className="font-semibold">Start as a guest</h2>
          <p className="mt-1 text-sm text-muted">No account needed. Your work is kept on the server for {config?.guest_retention_days ?? 14} days; save it to an account any time.</p>
          <Button className="mt-4 w-full" onClick={() => guest.mutate()} loading={guest.isPending}>Start</Button>
        </Card>
        <Card>
          <h2 className="font-semibold">Sign in</h2>
          <p className="mt-1 text-sm text-muted">Keep your goals across devices and sessions.</p>
          <Button className="mt-4 w-full" variant="outline" onClick={() => setShowLogin((v) => !v)}>Sign in or register</Button>
        </Card>
        {config?.demo_mode_enabled && (
          <Card>
            <h2 className="font-semibold">Explore the demo</h2>
            <p className="mt-1 text-sm text-muted">A fictional teacher moving into data analysis, with results already filled in.</p>
            <Button className="mt-4 w-full" variant="subtle" onClick={() => demo.mutate()} loading={demo.isPending}>Open demo</Button>
          </Card>
        )}
      </div>
      {(guest.isError || demo.isError) && <div className="mt-4"><Alert tone="bad">{errorText(guest.error ?? demo.error)}</Alert></div>}
      {showLogin && <Card className="mt-6"><AuthForm onDone={refresh} /></Card>}
    </main>
  );
}
