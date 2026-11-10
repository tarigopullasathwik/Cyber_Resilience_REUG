import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Database,
  FlaskConical,
  Gauge,
  Layers,
  Radar,
  ShieldCheck,
  ShieldOff,
  Siren,
} from "lucide-react";
import { useFetch } from "../hooks";
import { Badge, Button, DataTable, EmptyState, ErrorNotice, KeyValue, LoadingBlock, MetricBar, Panel, ScopeNote, Stat, StatusBadge } from "../components/ui";
import { formatDate, formatMetric, formatNumber, formatPercent, titleCase } from "../lib/format";

const DEVICE_COLORS = {
  ACTIVE: "#34d399",
  MONITORED: "#22d3ee",
  THROTTLED: "#fbbf24",
  REAUTH_REQUIRED: "#fbbf24",
  QUARANTINED: "#f87171",
};

function Topology({ devices, selected, onSelect }) {
  const nodes = devices.slice(0, 12).map((device, index) => {
    const ring = index % 2;
    const count = Math.ceil(devices.length / 2);
    const position = Math.floor(index / 2);
    const angle = (position / Math.max(count, 1)) * Math.PI * 2 + (ring ? 0.35 : 0);
    const radius = ring ? 76 : 120;
    return {
      ...device,
      x: 220 + Math.cos(angle) * radius,
      y: 148 + Math.sin(angle) * (radius * 0.72),
      color: DEVICE_COLORS[device.status] || "#64748b",
    };
  });
  return (
    <svg viewBox="0 0 440 300" className="h-auto w-full" role="img" aria-label="Simulated IoT fleet topology">
      <defs>
        <radialGradient id="gatewayGlow" cx="50%" cy="50%">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.2" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="220" cy="148" r="118" fill="none" stroke="#1b3049" strokeDasharray="2 6" opacity="0.55" />
      <circle cx="220" cy="148" r="76" fill="none" stroke="#1b3049" strokeDasharray="2 6" opacity="0.4" />
      {nodes.map((node) => (
        <line key={`line-${node.id}`} x1="220" y1="148" x2={node.x} y2={node.y} stroke={node.color} strokeOpacity="0.16" strokeWidth="1" />
      ))}
      <circle cx="220" cy="148" r="58" fill="url(#gatewayGlow)" />
      <rect x="190" y="122" width="60" height="52" rx="10" fill="#0d1c2d" stroke="#22d3ee" strokeOpacity="0.4" />
      <rect x="200" y="132" width="40" height="7" rx="2" fill="#22d3ee" opacity="0.5" />
      <rect x="200" y="144" width="26" height="5" rx="2" fill="#334155" />
      <rect x="200" y="154" width="34" height="5" rx="2" fill="#334155" />
      <text x="220" y="196" textAnchor="middle" fill="#5b7088" fontSize="8" letterSpacing="1.4">
        EDGE GATEWAY
      </text>
      {nodes.map((node) => (
        <g key={node.id} onClick={() => onSelect(node)} className="cursor-pointer">
          <circle cx={node.x} cy={node.y} r="13" fill={node.color} opacity={selected?.id === node.id ? 0.28 : 0.1} />
          <circle cx={node.x} cy={node.y} r="5" fill={node.color} stroke="#07111d" strokeWidth="2" />
          <text x={node.x} y={node.y + 21} textAnchor="middle" fill={selected?.id === node.id ? "#e6eef8" : "#5b7088"} fontSize="7.5">
            {node.id}
          </text>
        </g>
      ))}
      <text x="20" y="286" fill="#3f536a" fontSize="7.5">
        Simulated fleet · click a node to inspect
      </text>
    </svg>
  );
}

export default function CommandCenter() {
  const { data, error, loading, refresh } = useFetch("/api/command-center", { poll: 5000 });
  const [selected, setSelected] = useState(null);

  if (loading && !data) {
    return (
      <div className="space-y-4">
        <LoadingBlock rows={2} />
        <div className="grid gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => <div key={index} className="skeleton h-24" />)}
        </div>
        <LoadingBlock rows={6} />
      </div>
    );
  }

  if (error && !data) {
    return (
      <Panel title="Backend unavailable">
        <ErrorNotice error={error} onRetry={refresh} title="Could not load the command center" />
        <p className="mt-3 text-[11.5px] leading-relaxed text-slate-500">
          Start the API with <code className="rounded bg-ink-950 px-1 py-0.5 font-mono text-cyan/80">python -m uvicorn backend.main:app --reload --port 8000</code> and the web app with
          <code className="ml-1 rounded bg-ink-950 px-1 py-0.5 font-mono text-cyan/80">npm run dev</code> in the frontend folder.
        </p>
      </Panel>
    );
  }

  const counts = data?.counts || {};
  const predictions = data?.latest_predictions || {};
  const model = data?.active_model;
  const devices = data?.devices || [];
  const events = data?.latest_events || [];
  const host = data?.resources?.host || {};
  const edge = data?.resources?.edge || {};
  const experiments = data?.recent_experiments || [];
  const selectedDevice = selected ? devices.find((device) => device.id === selected.id) || selected : null;
  const onboard = (counts.completed_experiments || 0) === 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="amber" dot>Analysis mode: historical dataset replay</Badge>
          <Badge tone="neutral">No live capture</Badge>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-slate-600">
          <span className={`h-1.5 w-1.5 rounded-full ${error ? "bg-threat" : "bg-normal animate-pulse-soft"}`} />
          {error ? "Reconnecting" : `Updated ${new Date().toLocaleTimeString()}`}
          <Button variant="ghost" onClick={refresh} className="!px-2 !py-1">Refresh</Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Stat label="Datasets" value={formatNumber(counts.datasets)} hint={`${formatNumber(counts.preprocess_runs)} preprocessing runs`} tone="cyan" icon={Database} />
        <Stat label="Experiments" value={formatNumber(counts.experiments)} hint={`${formatNumber(counts.completed_experiments)} completed`} tone="blue" icon={FlaskConical} />
        <Stat label="Analyzed records" value={formatNumber(predictions.total_records)} hint="Held-out test records across the latest experiment" tone="green" icon={Layers} />
        <Stat label="Contained threats" value={formatNumber(counts.contained_threats)} hint={`${formatNumber(counts.containment_events)} containment events`} tone="amber" icon={ShieldCheck} />
      </div>

      {onboard ? (
        <Panel title="Start the research workflow" subtitle="The platform ships without embedded results. Run the pipeline on a dataset to populate every module.">
          <div className="grid gap-3 md:grid-cols-4">
            {[
              { icon: Database, title: "1 · Import a dataset", text: "Upload Edge-IIoTset, CICIoT2023, ToN-IoT or your own CSV.", to: "/datasets" },
              { icon: Gauge, title: "2 · Preprocess", text: "Choose the label column and leakage-safe transformations.", to: "/preprocessing" },
              { icon: Activity, title: "3 · Train & evaluate", text: "Fit a supervised model or a benign-only anomaly detector.", to: "/models" },
              { icon: ShieldOff, title: "4 · Replay response", text: "Run withheld-family tests and simulated containment.", to: "/unknown" },
            ].map((step) => (
              <Link key={step.title} to={step.to} className="group rounded-lg border border-line/70 bg-ink-900/40 p-3.5 transition hover:border-cyan/30 hover:bg-ink-800/50">
                <step.icon size={17} className="text-cyan/80" />
                <div className="mt-3 text-[12px] font-semibold text-slate-200">{step.title}</div>
                <p className="mt-1 text-[10.5px] leading-relaxed text-slate-500">{step.text}</p>
                <span className="mt-2 inline-flex items-center gap-1 text-[10px] font-semibold text-cyan/70">
                  Open <ArrowRight size={10} />
                </span>
              </Link>
            ))}
          </div>
        </Panel>
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Benign records" value={formatNumber(predictions.benign)} hint="Synthetic / dataset ground truth" tone="green" />
          <Stat label="Malicious records" value={formatNumber(predictions.malicious)} hint="Dataset-provided attack labels" tone="red" />
          <Stat label="Flagged by model" value={formatNumber(predictions.flagged)} hint="Latest experiment test split" tone="amber" />
          <Stat label="Suspected unknown" value={formatNumber(predictions.unknown_suspected)} hint="Only from withheld family experiments" tone="blue" />
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[1.55fr_1fr]">
        <Panel title="Simulated IoT fleet" subtitle="Node colour reflects the containment state; this is a simulated fleet, not a network scan." action={<Badge tone="green" dot>{formatNumber(counts.healthy_devices)}/{formatNumber(counts.simulated_devices)} active</Badge>}>
          <Topology devices={devices} selected={selected} onSelect={setSelected} />
          {selectedDevice && (
            <div className="mt-2 grid gap-3 rounded-lg border border-line/60 bg-ink-950/40 p-3 sm:grid-cols-2">
              <KeyValue
                items={[
                  { label: "Device", value: `${selectedDevice.name} (${selectedDevice.id})` },
                  { label: "Address", value: <span className="font-mono">{selectedDevice.ip}</span> },
                  { label: "Type", value: selectedDevice.type },
                ]}
              />
              <KeyValue
                items={[
                  { label: "Criticality", value: titleCase(selectedDevice.criticality) },
                  { label: "Containment state", value: <StatusBadge status={selectedDevice.status} /> },
                  { label: "Policy level", value: `${selectedDevice.policy_level}/3` },
                ]}
              />
            </div>
          )}
        </Panel>

        <Panel title="Edge gateway" subtitle="Host measurements and simulated edge budget are kept separate.">
          <div className="space-y-3.5">
            <div>
              <div className="mb-1 flex justify-between text-[10.5px]"><span className="text-slate-500">Host CPU (measured)</span><span className="font-mono text-slate-300">{formatMetric(host.host_cpu_percent, 1)}%</span></div>
              <MetricBar value={(host.host_cpu_percent || 0) / 100} tone="cyan" />
            </div>
            <div>
              <div className="mb-1 flex justify-between text-[10.5px]"><span className="text-slate-500">Host memory (measured)</span><span className="font-mono text-slate-300">{formatMetric(host.host_memory_percent, 1)}%</span></div>
              <MetricBar value={(host.host_memory_percent || 0) / 100} tone="blue" />
            </div>
            <div>
              <div className="mb-1 flex justify-between text-[10.5px]"><span className="text-slate-500">Simulated edge CPU</span><span className="font-mono text-suspicious">{formatPercent(edge.simulated_cpu_utilisation)}</span></div>
              <MetricBar value={edge.simulated_cpu_utilisation || 0} tone="amber" />
            </div>
            <div className="rounded-lg border border-line/60 bg-ink-950/40 p-2.5">
              <KeyValue
                items={[
                  { label: "Backend RSS", value: `${formatMetric(host.process_rss_mb, 1)} MB` },
                  { label: "Simulated devices", value: formatNumber(counts.simulated_devices) },
                  { label: "Active actions", value: formatNumber(edge.active_containment_actions) },
                  { label: "Edge CPU budget", value: formatMetric(edge.budget?.cpu_capacity, 2) },
                ]}
              />
            </div>
            <Link to="/resources" className="inline-flex items-center gap-1 text-[10.5px] font-semibold text-cyan/80 hover:text-cyan">
              Open resource monitor <ArrowRight size={11} />
            </Link>
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.25fr_1fr]">
        <Panel title="Latest security events" subtitle="Containment events generated from held-out dataset replays." action={<Link to="/containment" className="text-[10.5px] font-semibold text-cyan/80 hover:text-cyan">View all</Link>} flush>
          <DataTable
            dense
            columns={[
              { key: "created_at", label: "Time", render: (row) => <span className="whitespace-nowrap text-slate-500">{formatDate(row.created_at)}</span> },
              { key: "device_name", label: "Device", render: (row) => <span className="text-slate-200">{row.device_name}</span> },
              { key: "action", label: "Action", render: (row) => <Badge tone={row.action === "QUARANTINE" ? "red" : row.action === "OBSERVE" ? "neutral" : "amber"}>{row.action}</Badge> },
              { key: "severity", label: "Severity", align: "right", render: (row) => <span className="font-mono text-slate-300">{formatMetric(row.severity, 0)}</span> },
              { key: "verification", label: "Verification", render: (row) => <StatusBadge status={row.verification || row.status} /> },
            ]}
            rows={events}
            empty="No containment events yet. Run a replay from the Containment module."
          />
        </Panel>

        <Panel
          title="Active model"
          subtitle="The most recent completed experiment with saved test predictions."
          action={<Link to="/analytics" className="text-[10.5px] font-semibold text-cyan/80 hover:text-cyan">Analytics</Link>}
        >
          {model ? (
            <div className="space-y-3">
              <div className="rounded-lg border border-line/60 bg-ink-950/40 p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12px] font-semibold text-slate-100">{model.model}</span>
                  <Badge tone="cyan">active</Badge>
                </div>
                <p className="mt-1 truncate text-[10.5px] text-slate-500">{model.name}</p>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                  <div><div className="text-[9px] uppercase tracking-wide text-slate-600">F1</div><div className="font-mono text-sm text-slate-200">{formatMetric(model.f1)}</div></div>
                  <div><div className="text-[9px] uppercase tracking-wide text-slate-600">Recall</div><div className="font-mono text-sm text-slate-200">{formatMetric(model.recall)}</div></div>
                  <div><div className="text-[9px] uppercase tracking-wide text-slate-600">Unknown</div><div className="font-mono text-sm text-slate-200">{formatMetric(model.unknown_recall)}</div></div>
                </div>
              </div>
              <div className="space-y-1.5">
                <div className="eyebrow">Recent experiments</div>
                {experiments.length === 0 && <p className="text-[11px] text-slate-600">No completed experiments.</p>}
                {experiments.slice(0, 4).map((experiment) => (
                  <div key={experiment.id} className="flex items-center justify-between gap-2 rounded-md border border-line/40 px-2.5 py-1.5">
                    <div className="min-w-0">
                      <div className="truncate text-[10.5px] text-slate-300">{experiment.name}</div>
                      <div className="text-[9px] text-slate-600">{titleCase(experiment.kind)} · {formatDate(experiment.completed_at)}</div>
                    </div>
                    <span className="font-mono text-[10px] text-cyan/80">{formatMetric(experiment.metrics?.f1)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState icon={FlaskConical} title="No active model" description="Train a model in the ML Laboratory to populate the command center." action={<Link to="/models" className="btn btn-primary">Open ML Laboratory</Link>} />
          )}
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Fleet health" className="lg:col-span-1">
          <div className="flex items-end gap-3">
            <div className="font-mono text-3xl font-semibold text-normal">{formatMetric(data?.network_health, 1)}%</div>
            <span className="pb-1 text-[10px] text-slate-600">devices in ACTIVE state</span>
          </div>
          <div className="mt-3"><MetricBar value={(data?.network_health || 0) / 100} tone="green" /></div>
          <div className="mt-4 grid grid-cols-2 gap-2">
            {["ACTIVE", "MONITORED", "THROTTLED", "QUARANTINED"].map((status) => {
              const count = devices.filter((device) => device.status === status).length;
              return (
                <div key={status} className="rounded-md border border-line/50 px-2 py-1.5">
                  <div className="text-[9px] uppercase tracking-wide text-slate-600">{status}</div>
                  <div className="font-mono text-sm text-slate-300">{count}</div>
                </div>
              );
            })}
          </div>
        </Panel>
        <Panel title="Detection composition" subtitle="Latest experiment test predictions." className="lg:col-span-2">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-normal/15 bg-normal/[0.04] p-3"><div className="text-[9px] uppercase tracking-wide text-normal/70">Benign</div><div className="mt-1 font-mono text-xl text-slate-100">{formatNumber(predictions.benign)}</div></div>
            <div className="rounded-lg border border-threat/15 bg-threat/[0.04] p-3"><div className="text-[9px] uppercase tracking-wide text-threat/70">Malicious</div><div className="mt-1 font-mono text-xl text-slate-100">{formatNumber(predictions.malicious)}</div></div>
            <div className="rounded-lg border border-suspicious/15 bg-suspicious/[0.04] p-3"><div className="text-[9px] uppercase tracking-wide text-suspicious/80">Flagged</div><div className="mt-1 font-mono text-xl text-slate-100">{formatNumber(predictions.flagged)}</div></div>
            <div className="rounded-lg border border-cyan/15 bg-cyan/[0.04] p-3"><div className="text-[9px] uppercase tracking-wide text-cyan/80">Suspected unknown</div><div className="mt-1 font-mono text-xl text-slate-100">{formatNumber(predictions.unknown_suspected)}</div></div>
          </div>
          <ScopeNote><span className="text-slate-500">{data?.mode_note}</span></ScopeNote>
        </Panel>
      </div>

      <ScopeNote>
        Devices, attacks and containment actions are simulated. Records shown are historical dataset rows replayed through the trained model.
        Host CPU, memory and latency are measured on the backend machine. No live network is monitored or blocked.
      </ScopeNote>
    </div>
  );
}
