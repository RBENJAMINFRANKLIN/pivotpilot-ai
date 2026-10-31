import { useMutation } from "@tanstack/react-query";
import { BarChart3, BookOpen, Briefcase, ClipboardCheck, FileText, FolderKanban, Gauge, Map, MessageSquare, Settings, Target } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { post } from "@/lib/api";
import { useActiveTransition, useRefreshAll, useSession } from "@/lib/hooks";
import { CommandBar } from "./CommandBar";
import { Badge, Button, cn } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: Gauge },
  { to: "/goals", label: "Career goals", icon: Target },
  { to: "/intake", label: "Resume & job", icon: FileText },
  { to: "/analysis", label: "Fit analysis", icon: BarChart3 },
  { to: "/assessment", label: "Assessment", icon: ClipboardCheck },
  { to: "/plan", label: "Learning plan", icon: Map },
  { to: "/resources", label: "Resources", icon: BookOpen },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/interviews", label: "Mock interviews", icon: MessageSquare },
  { to: "/applications", label: "Applications", icon: Briefcase },
  { to: "/settings", label: "Account & privacy", icon: Settings },
];

export function Layout() {
  const { data: session } = useSession();
  const { transition } = useActiveTransition();
  const refresh = useRefreshAll();
  const nav = useNavigate();
  const logout = useMutation({ mutationFn: () => post("/auth/logout"), onSuccess: () => { refresh(); nav("/"); } });

  return (
    <div className="flex min-h-full flex-col md:flex-row">
      <aside className="border-b border-line bg-surface md:w-60 md:shrink-0 md:border-r md:border-b-0">
        <div className="flex items-center justify-between p-4">
          <p className="text-lg font-semibold">PivotPilot <span className="text-brand">AI</span></p>
        </div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:overflow-visible">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/"}
              className={({ isActive }) => cn("flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm",
                isActive ? "bg-brand-soft font-medium text-brand" : "text-muted hover:bg-bg")}>
              <Icon className="size-4" aria-hidden />{label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="border-b border-line bg-surface px-4 py-3 md:px-8">
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            {transition ? (
              <span className="text-muted">Active goal: <strong className="text-ink">{transition.current_role ? `${transition.current_role} → ` : ""}{transition.target_role}</strong></span>
            ) : <span className="text-muted">No active goal yet</span>}
            <span className="ml-auto flex items-center gap-2">
              {session?.kind === "guest" ? (
                <>
                  <Badge tone="warn" title={session.retention_notice}>Guest</Badge>
                  <Button size="sm" onClick={() => nav("/settings")}>Save My Progress</Button>
                </>
              ) : session ? (
                <>
                  <Badge tone="good">{session.user_email}</Badge>
                  <Button size="sm" variant="ghost" onClick={() => logout.mutate()}>Sign out</Button>
                </>
              ) : null}
            </span>
          </div>
          <CommandBar />
        </header>
        <main className="mx-auto max-w-6xl p-4 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
