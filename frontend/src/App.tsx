import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Spinner } from "./components/ui";
import { useSession } from "./lib/hooks";
import { AnalysisPage } from "./pages/Analysis";
import { ApplicationsPage } from "./pages/Applications";
import { AssessmentPage } from "./pages/Assessment";
import { DashboardPage } from "./pages/Dashboard";
import { GoalsPage } from "./pages/Goals";
import { IntakePage } from "./pages/Intake";
import { InterviewsPage } from "./pages/Interviews";
import { PlanPage } from "./pages/Plan";
import { ProjectsPage } from "./pages/Projects";
import { ResourcesPage } from "./pages/Resources";
import { SettingsPage } from "./pages/Settings";
import { WelcomePage } from "./pages/Welcome";

export function App() {
  const { data: session, isLoading, isError } = useSession();
  if (isLoading) return <Spinner label="Starting PivotPilot" />;
  if (!session || isError) return <WelcomePage />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="goals" element={<GoalsPage />} />
        <Route path="intake" element={<IntakePage />} />
        <Route path="analysis" element={<AnalysisPage />} />
        <Route path="assessment" element={<AssessmentPage />} />
        <Route path="plan" element={<PlanPage />} />
        <Route path="resources" element={<ResourcesPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="interviews" element={<InterviewsPage />} />
        <Route path="applications" element={<ApplicationsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<DashboardPage />} />
      </Route>
    </Routes>
  );
}
