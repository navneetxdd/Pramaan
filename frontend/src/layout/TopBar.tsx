import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

const links = [
  { to: "/", label: "Cases" },
  { to: "/acquire", label: "Acquire" },
  { to: "/recover", label: "Recover" },
  { to: "/analyze", label: "Analyze" },
  { to: "/custody", label: "Custody" },
];

export function TopBar() {
  return (
    <header className="sticky top-0 z-40 border-b border-hairline bg-canvas/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-6 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-accent-line bg-accent-soft font-serif text-lg text-accent">
            P
          </div>
          <div>
            <p className="font-serif text-lg leading-none text-ink">Pramaan</p>
            <p className="text-xs text-ink-faint">DVR / NVR forensic workstation</p>
          </div>
        </div>

        <nav className="hidden items-center gap-1 rounded-full border border-hairline bg-surface p-1 md:flex">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === "/"}
              className={({ isActive }) =>
                cn(
                  "rounded-full px-4 py-2 text-sm transition",
                  isActive
                    ? "bg-raised text-ink"
                    : "text-ink-muted hover:text-ink",
                )
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  );
}
