import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { DesktopShell } from "@/layout/DesktopShell";
import { CasesPage } from "@/pages/CasesPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { CaseLayout } from "@/pages/case/CaseLayout";
import { CaseOverviewPage } from "@/pages/case/CaseOverviewPage";
import { CaseJobsPage } from "@/pages/case/CaseJobsPage";
import { CaseEvidenceCatalogPage } from "@/pages/case/CaseEvidenceCatalogPage";
import { CaseAcquirePage } from "@/pages/case/CaseAcquirePage";
import { CaseDeviceIdPage } from "@/pages/case/CaseDeviceIdPage";
import { CaseRecoverPage } from "@/pages/case/CaseRecoverPage";
import { CaseTimelinePage } from "@/pages/case/CaseTimelinePage";
import { CaseCustodyPage } from "@/pages/case/CaseCustodyPage";
import { CaseReportPage } from "@/pages/case/CaseReportPage";
import { CaseAiAnalyticsPage } from "@/pages/case/CaseAiAnalyticsPage";
import { CaseLiveDevicesPage } from "@/pages/case/CaseLiveDevicesPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<DesktopShell />}>
          <Route path="/" element={<Navigate to="/cases" replace />} />
          <Route path="/cases" element={<CasesPage />} />
          <Route path="/cases/:caseId" element={<CaseLayout />}>
            <Route index element={<CaseOverviewPage />} />
            <Route path="evidence" element={<CaseEvidenceCatalogPage />} />
            <Route path="jobs" element={<CaseJobsPage />} />
            <Route path="live" element={<CaseLiveDevicesPage />} />
            <Route path="acquire" element={<CaseAcquirePage />} />
            <Route path="device-id" element={<CaseDeviceIdPage />} />
            <Route path="recover" element={<CaseRecoverPage />} />
            <Route path="timeline" element={<CaseTimelinePage />} />
            <Route path="custody" element={<CaseCustodyPage />} />
            <Route path="report" element={<CaseReportPage />} />
            <Route path="ai-analytics" element={<CaseAiAnalyticsPage />} />
          </Route>
          <Route
            path="/tool-verification"
            element={<Navigate to="/settings" replace />}
          />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/cases" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
