import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  BarChart3,
  BookOpen,
  Cpu,
  Database,
  FileText,
  FlaskConical,
  LayoutDashboard,
  Menu,
  Radar,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useFetch } from "../hooks";

const NAV = [
  {
    section: "Operations",
    items: [
      { to: "/", label: "Command Center", icon: LayoutDashboard, title: "Command Center", description: "Security posture, fleet health and recent activity across stored experiments." },
      { to: "/threats", label: "Threat Intelligence", icon: Radar, title: "Threat Intelligence", description: "Benign, known-malicious and suspected-unknown traffic from held-out test predictions." },
      { to: "/containment", label: "Autonomous Containment", icon: ShieldCheck, title: "Autonomous Containment", description: "Closed-loop MONITOR → DETECT → ASSESS → CONTAIN → VERIFY → LEARN replay in a simulated fleet." },
      { to: "/resources", label: "Edge Resources", icon: Cpu, title: "Edge Resource Monitoring", description: "Measured host cost separated from the configurable simulated edge budget." },
    ],
  },
  {
    section: "Research Pipeline",
    items: [
      { to: "/datasets", label: "Datasets", icon: Database, title: "Dataset Management", description: "Upload, profile, version and select public IoT datasets with explicit target columns." },
      { to: "/preprocessing", label: "Preprocessing", icon: SlidersHorizontal, title: "Data Preprocessing", description: "Leakage-safe imputation, encoding, scaling, feature selection and class balancing." },
      { to: "/models", label: "ML Laboratory", icon: FlaskConical, title: "ML Model Laboratory", description: "Train supervised and anomaly detectors with real background jobs and test metrics." },
      { to: "/unknown", label: "Unknown Attacks", icon: ShieldAlert, title: "Unknown Attack Detection", description: "Withhold attack families and run leave-one-attack-family-out experiments." },
      { to: "/analytics", label: "Research Analytics", icon: BarChart3, title: "Research Analytics", description: "Model comparison, ROC, precision-recall, per-class and per-family performance." },
      { to: "/reports", label: "Experimental Reports", icon: FileText, title: "Experimental Reports", description: "Generate PDF reports and export experiment results as CSV or JSON." },
    ],
  },
  {
    section: "Reference",
    items: [
      { to: "/documentation", label: "Research Documentation", icon: BookOpen, title: "Research Documentation", description: "Abstract, methodology, architecture, experimental protocol, limitations and references." },
    ],
  },
];

const ALL_ITEMS = NAV.flatMap((group) => group.items);

export default function Layout() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const health = useFetch("/api/health", { poll: 30000 });
  const current = ALL_ITEMS.find((item) => item.to === location.pathname) || ALL_ITEMS[0];
  const online = Boolean(health.data) && !health.error;

  useEffect(() => {
    setOpen(false);
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [location.pathname]);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[258px_minmax(0,1fr)]">
      {open && (
        <button
          aria-label="Close navigation"
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-40 bg-ink-950/70 backdrop-blur-sm lg:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-[258px] flex-col border-r border-line/70 bg-ink-900/95 backdrop-blur-xl transition-transform duration-200 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 pb-4 pt-5">
          <div className="flex items-center gap-2.5">
            <div className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-cyan/30 bg-gradient-to-br from-cyan/20 to-electric/10">
              <ShieldCheck size={17} className="text-cyan" />
              <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full border border-ink-900 bg-normal" />
            </div>
            <div>
              <div className="text-[13.5px] font-bold leading-tight tracking-tight text-slate-50">EDGEGUARD <span className="text-cyan">AI</span></div>
              <div className="text-[9.5px] uppercase tracking-[0.16em] text-slate-500">Edge Cyber-Resilience</div>
            </div>
          </div>
          <button className="rounded-md p-1.5 text-slate-500 hover:bg-ink-800 hover:text-slate-200 lg:hidden" onClick={() => setOpen(false)}>
            <X size={16} />
          </button>
        </div>

        <div className="mx-4 mb-4 rounded-lg border border-line/60 bg-ink-950/50 px-2.5 py-2">
          <div className="flex items-center justify-between">
            <span className="text-[9px] uppercase tracking-[0.14em] text-slate-600">Environment</span>
            <span className="flex items-center gap-1 text-[9.5px] font-semibold uppercase tracking-wide text-suspicious">
              <span className="h-1.5 w-1.5 rounded-full bg-suspicious" /> Simulation
            </span>
          </div>
          <p className="mt-1 text-[9.5px] leading-snug text-slate-600">Historical replay · no live capture</p>
        </div>

        <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-4">
          {NAV.map((group) => (
            <div key={group.section}>
              <div className="mb-1.5 px-2.5 text-[9px] font-semibold uppercase tracking-[0.18em] text-slate-600">{group.section}</div>
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === "/"}
                    className={({ isActive }) => `nav-item ${isActive ? "nav-item-active" : ""}`}
                  >
                    <item.icon size={14.5} strokeWidth={1.8} />
                    <span>{item.label}</span>
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-line/60 px-4 py-3.5">
          <div className="flex items-center justify-between text-[10px]">
            <span className="text-slate-600">Backend</span>
            <span className={`flex items-center gap-1.5 font-semibold ${online ? "text-normal" : "text-threat"}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${online ? "bg-normal" : "bg-threat"}`} />
              {online ? "online" : "offline"}
            </span>
          </div>
          <div className="mt-2 flex items-center justify-between text-[9px] text-slate-700">
            <span>v2.0 · REUG prototype</span>
            <span className="font-mono">REST + WS</span>
          </div>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b border-line/60 bg-ink-950/80 backdrop-blur-xl">
          <div className="flex items-center gap-3 px-4 py-3.5 sm:px-6 lg:px-7">
            <button className="rounded-md border border-line p-1.5 text-slate-400 lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation">
              <Menu size={17} />
            </button>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-[9.5px] font-semibold uppercase tracking-[0.16em] text-slate-600">
                <span>EDGEGUARD</span>
                <span className="text-slate-700">/</span>
                <span className="truncate text-cyan/80">{current.label}</span>
              </div>
              <h1 className="mt-0.5 truncate text-[15px] font-semibold tracking-tight text-slate-100">{current.title}</h1>
            </div>
            <div className="hidden items-center gap-2 md:flex">
              <span className="badge badge-amber">Research prototype</span>
              <span className="badge badge-neutral">No live network access</span>
            </div>
            <a
              href="/api/docs"
              target="_blank"
              rel="noreferrer"
              className="hidden rounded-lg border border-line px-2.5 py-1.5 text-[10px] font-semibold text-slate-400 transition hover:border-cyan/30 hover:text-cyan sm:inline-flex"
            >
              API
            </a>
          </div>
          <p className="hidden border-t border-line/30 px-6 py-2 text-[10.5px] leading-relaxed text-slate-600 lg:block lg:px-7">
            {current.description}
          </p>
        </header>

        <main className="mx-auto w-full max-w-[1560px] px-4 py-5 sm:px-6 lg:px-7 lg:py-6">
          <Outlet />
        </main>
        <footer className="mx-auto flex w-full max-w-[1560px] flex-wrap items-center justify-between gap-2 border-t border-line/30 px-4 py-4 text-[10px] text-slate-700 sm:px-6 lg:px-7">
          <span>EDGEGUARD AI · Adaptive Edge Cyber-Resilience Mechanism</span>
          <span>Containment, devices and edge budgets are simulated. Host metrics are measured.</span>
        </footer>
      </div>
    </div>
  );
}
