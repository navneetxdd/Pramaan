import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/layout/AppShell";
import { AcquirePage } from "@/pages/AcquirePage";
import { AnalyzePage } from "@/pages/AnalyzePage";
import { CaseDetailPage } from "@/pages/CaseDetailPage";
import { CasesPage } from "@/pages/CasesPage";
import { CustodyPage } from "@/pages/CustodyPage";
import { ReportPage } from "@/pages/ReportPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<CasesPage />} />
          <Route path="cases/:caseId" element={<CaseDetailPage />} />
          <Route path="acquire" element={<AcquirePage />} />
          <Route path="recover" element={<RecoverPage />} />
          <Route path="analyze" element={<AnalyzePage />} />
          <Route path="custody" element={<CustodyPage />} />
          <Route path="report" element={<ReportPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
