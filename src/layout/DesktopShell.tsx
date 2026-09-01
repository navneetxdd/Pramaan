import { Outlet, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AppHeader } from "./AppHeader";
import { ModuleSidebar } from "./ModuleSidebar";
import { StatusBar } from "./StatusBar";
import { TitleBar } from "./TitleBar";
import { FfmpegWarningBanner } from "@/components/FfmpegWarningBanner";

export function DesktopShell() {
  const location = useLocation();

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden" style={{ background: "var(--surface-0)" }}>
      <TitleBar />
      <FfmpegWarningBanner />

      <div className="flex min-h-0 flex-1">
        <ModuleSidebar />

        <div className="flex min-w-0 flex-1 flex-col bg-[var(--surface-1)]">
          <AppHeader />

          <main
            className={`flex-1 overflow-x-hidden p-4 md:p-5 ${
              location.pathname.includes("/evidence") ? "overflow-hidden" : "overflow-y-auto"
            }`}
          >
            <Outlet />
          </main>

          <StatusBar />
        </div>
      </div>

      <Toaster
        theme="light"
        position="bottom-right"
        toastOptions={{
          classNames: {
            toast: "visily-card border-[var(--border-subtle)] bg-white text-[var(--text-primary)]",
            description: "text-[var(--text-secondary)]",
          },
        }}
      />
    </div>
  );
}
