import { BrowserRouter, Route, Routes } from "react-router-dom";
import { JobsPanel } from "./components/JobsPanel";
import { StatusBanner } from "./components/StatusBanner";
import { AnimationsPage } from "./pages/AnimationsPage";
import { ExportPage } from "./pages/ExportPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ReferencePage } from "./pages/ReferencePage";
import { ReviewPage } from "./pages/ReviewPage";
import { ViewsPage } from "./pages/ViewsPage";

export function App() {
  return (
    <BrowserRouter>
      <StatusBanner />
      <div className="layout">
        <main className="content">
          <Routes>
            <Route path="/" element={<ProjectsPage />} />
            <Route path="/p/:id/reference" element={<ReferencePage />} />
            <Route path="/p/:id/views" element={<ViewsPage />} />
            <Route path="/p/:id/animations" element={<AnimationsPage />} />
            <Route path="/p/:id/review" element={<ReviewPage />} />
            <Route path="/p/:id/export" element={<ExportPage />} />
          </Routes>
        </main>
        <JobsPanel />
      </div>
    </BrowserRouter>
  );
}
