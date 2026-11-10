import { useEffect, useState } from "react";
import { ChevronDown, Play, RefreshCw, RotateCcw, ShieldCheck, ShieldOff, ShieldX } from "lucide-react";
import { api } from "../api";
import { useFetch, useJob } from "../hooks";
import { Badge, Button, DataTable, EmptyState, ErrorNotice, KeyValue, LoadingBlock, Panel, Progress, ScopeNote, Stat, StatusBadge } from "../components/ui";
import { actionTone, formatDate, formatMetric, formatNumber, titleCase } from "../lib/format";

const STAGE_COLORS = ["#22d3ee", "#3b82f6", "#a78bfa", "#fbbf24", "#34d399", "#f87171"];

export default function Containment() {
  const status = useFetch("/api/containment/status", { poll: 5000 });
  const experiments = useFetch("/api/experiments");
  const [experimentId, setExperimentId] = useState("");
  const [maxEvents, setMaxEvents] = useState(8);
  const [jobId, setJobId] = useState(null);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const job = useJob(jobId, async (finished) => {
    if (finished.status === "completed") await status.refresh();
  });

  const completed = (experiments.data || []).filter((item) => item.status === "completed" && item.predictions_available);
  useEffect(() => {
    if (!experimentId && completed.length) setExperimentId(completed[0].id);
  }, [completed, experimentId]);

  const devices = status.data?.devices || [];
  const events = status.data?.events || [];
  const stages = status.data?.pipeline?.stages || [];
  const contained = events.filter((event) => event.status === "CONTAINED").length;
  const failed = events.filter((event) => event.status === "FAILED").length;
  const inconclusive = events.filter((event) => event.verification === "INCONCLUSIVE").length;

  const run = async () => {
    setError(null);
    try {
      const response = await api.simulateContainment({ experiment_id: experimentId || undefined, max_events: Number(maxEvents) });
      setJobId(response.job.id);
    } catch (exc) {
      setError(exc);
    }
  };

  const act = async (fn) => {
    setActionError(null);
    try {
      await fn();
      await status.refresh();
    } catch (exc) {
      setActionError(exc);
    }
  };

  return (
    <div className="space-y-4">
      {(error || actionError) && <ErrorNotice error={error || actionError} onRetry={() => { setError(null); setActionError(null); }} />}

      <Panel
        title="Closed-loop pipeline"
        subtitle="A replay of historical held-out records. Every action is simulated and verified against subsequent records."
        action={
          <div className="flex flex-wrap items-center gap-2">
            <select className="select !w-auto !py-1.5 !text-[11px]" value={experimentId} onChange={(event) => setExperimentId(event.target.value)}>
              {completed.map((experiment) => <option key={experiment.id} value={experiment.id}>{experiment.name}</option>)}
            </select>
            <input className="input !w-20 !py-1.5 !text-[11px]" type="number" min="1" max="25" value={maxEvents} onChange={(event) => setMaxEvents(event.target.value)} title="Maximum events per replay" />
            <Button onClick={run} disabled={!completed.length} loading={job?.status === "running"}>
              <Play size={12} /> Run replay
            </Button>
          </div>
        }
      >
        {status.loading && !status.data ? <LoadingBlock rows={3} /> : (
          <>
            <div className="grid gap-2 md:grid-cols-6 md:gap-1.5">
              {stages.map((stage, index) => (
                <div key={stage.key} className="relative flex items-center gap-1">
                  <div className="w-full rounded-lg border border-line/60 bg-ink-900/50 p-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] font-bold uppercase tracking-[0.14em]" style={{ color: STAGE_COLORS[index] }}>{stage.label}</span>
                      <span className="font-mono text-sm text-slate-200">{formatNumber(stage.count)}</span>
                    </div>
                    <p className="mt-1 text-[9px] leading-snug text-slate-600">{stage.description}</p>
                  </div>
                  {index < stages.length - 1 && <span className="hidden text-slate-700 md:block">›</span>}
                </div>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[10px] text-slate-600">
              <span>Historical dataset replay · simulated responses · verification re-scores real held-out features</span>
              <Button variant="ghost" onClick={status.refresh}><RefreshCw size={11} /> Refresh state</Button>
            </div>
            {job && <div className="mt-3"><Progress value={job.progress} message={job.message} tone={job.status === "failed" ? "red" : "cyan"} /></div>}
            {job?.error && <p className="mt-1 text-[10.5px] text-threat">{job.error}</p>}
          </>
        )}
      </Panel>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Devices" value={formatNumber(devices.length)} hint={`${formatNumber(devices.filter((device) => device.status === "ACTIVE").length)} active`} tone="cyan" icon={ShieldCheck} />
        <Stat label="Events" value={formatNumber(events.length)} hint="Containment records" tone="amber" icon={ShieldOff} />
        <Stat label="Contained" value={formatNumber(contained)} hint="Verification SUCCESS" tone="green" />
        <Stat label="Failed / inconclusive" value={`${formatNumber(failed)} / ${formatNumber(inconclusive)}`} hint="Reported, not hidden" tone="red" icon={ShieldX} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1.3fr]">
        <Panel title="Simulated fleet" subtitle="Device states change only inside this simulator.">
          {devices.length === 0 ? <LoadingBlock rows={4} /> : (
            <div className="grid gap-2 sm:grid-cols-2">
              {devices.map((device) => (
                <div key={device.id} className="rounded-lg border border-line/50 bg-ink-900/40 p-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-[11px] font-semibold text-slate-200">{device.name}</div>
                      <div className="mt-0.5 flex items-center gap-1.5 text-[9px] text-slate-600">
                        <span className="font-mono">{device.ip}</span>
                        <span>·</span>
                        <span>{device.type}</span>
                      </div>
                    </div>
                    <StatusBadge status={device.status} />
                  </div>
                  <div className="mt-2 flex items-center justify-between text-[9px] text-slate-600">
                    <span>Criticality <span className={device.criticality === "critical" ? "text-threat" : device.criticality === "high" ? "text-suspicious" : "text-slate-400"}>{titleCase(device.criticality)}</span></span>
                    <span>Policy L{device.policy_level}</span>
                  </div>
                  {device.status !== "ACTIVE" && (
                    <button
                      className="mt-2 inline-flex items-center gap-1 text-[9.5px] font-semibold text-cyan/80 hover:text-cyan"
                      onClick={() => {
                        const latest = events.find((event) => event.device_id === device.id && event.status !== "RELEASED");
                        if (latest) act(() => api.releaseEvent(latest.id));
                      }}
                    >
                      <RotateCcw size={10} /> Release latest event
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
          <ScopeNote>Simulated device fleet. Nothing here changes a host firewall, network interface or real IoT device.</ScopeNote>
        </Panel>

        <Panel title="Containment events" subtitle="Click a row to inspect the guard rationale and verification detail." flush>
          {status.loading && !events.length ? <div className="p-4"><LoadingBlock rows={5} /></div> : (
            <div className="max-h-[560px] overflow-auto">
              {events.length === 0 ? (
                <EmptyState icon={ShieldOff} title="No containment events" description="Run a replay with a completed experiment. Flagged held-out rows become simulated containment events." />
              ) : events.map((event) => (
                <div key={event.id} className="border-b border-line/40 last:border-0">
                  <button className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition hover:bg-ink-800/40" onClick={() => setExpanded(expanded === event.id ? null : event.id)}>
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${event.verification === "SUCCESS" ? "bg-normal" : event.verification === "FAILURE" ? "bg-threat" : "bg-suspicious"}`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[11px] font-semibold text-slate-200">{event.device_name}</span>
                        <Badge tone={actionTone(event.action)}>{event.action}</Badge>
                        <StatusBadge status={event.status} />
                      </div>
                      <div className="mt-0.5 truncate text-[9.5px] text-slate-600">
                        severity {formatMetric(event.severity, 0)} · risk {formatMetric(event.risk, 0)} · {formatDate(event.created_at)}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-mono text-[10.5px] text-slate-300">{formatMetric(event.before_score, 3)} → {formatMetric(event.after_score, 3)}</div>
                      <div className={`text-[9px] font-semibold ${event.verification === "SUCCESS" ? "text-normal" : event.verification === "FAILURE" ? "text-threat" : "text-suspicious"}`}>{event.verification || "pending"}</div>
                    </div>
                    <ChevronDown size={13} className={`text-slate-600 transition ${expanded === event.id ? "rotate-180" : ""}`} />
                  </button>
                  {expanded === event.id && (
                    <div className="bg-ink-950/50 px-4 pb-3">
                      <div className="grid gap-3 sm:grid-cols-2">
                        <KeyValue items={[
                          { label: "Reason", value: event.reason },
                          { label: "Guard", value: event.metadata?.guard || "none" },
                          { label: "Attack family", value: event.metadata?.family },
                          { label: "Source", value: event.metadata?.episode },
                        ]} />
                        <KeyValue items={[
                          { label: "Row index", value: event.metadata?.row_index },
                          { label: "Allowance", value: formatMetric(event.metadata?.allowance, 2) },
                          { label: "Confidence", value: formatMetric(event.confidence, 3) },
                          { label: "Verification", value: event.verification || "pending" },
                        ]} />
                      </div>
                      <p className="mt-2 rounded-md border border-line/40 bg-ink-900/50 px-2.5 py-2 text-[10px] leading-relaxed text-slate-500">{event.verification_detail || "Verification runs after the action is applied."}</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <Button variant="ghost" className="!px-2 !py-1 !text-[10px]" onClick={() => act(() => api.verifyEvent(event.id))}>Verify</Button>
                        <Button variant="ghost" className="!px-2 !py-1 !text-[10px]" onClick={() => act(() => api.releaseEvent(event.id))} disabled={event.status === "RELEASED"}>Release / recover</Button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Event log" subtitle="Full audit trail of simulated actions and their verification outcomes." flush>
        <DataTable
          dense
          columns={[
            { key: "created_at", label: "Time", render: (row) => <span className="whitespace-nowrap text-slate-500">{formatDate(row.created_at)}</span> },
            { key: "device", label: "Device", render: (row) => <span className="text-slate-300">{row.device_name}</span> },
            { key: "action", label: "Action", render: (row) => <Badge tone={actionTone(row.action)}>{row.action}</Badge> },
            { key: "severity", label: "Severity", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.severity, 1)}</span> },
            { key: "risk", label: "Risk", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.risk, 1)}</span> },
            { key: "before", label: "Before", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.before_score, 3)}</span> },
            { key: "after", label: "After", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.after_score, 3)}</span> },
            { key: "verification", label: "Verification", render: (row) => <Badge tone={row.verification === "SUCCESS" ? "green" : row.verification === "FAILURE" ? "red" : "amber"}>{row.verification || "pending"}</Badge> },
            { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
          ]}
          rows={events}
          empty="No events recorded."
        />
      </Panel>

      <ScopeNote>
        Containment is simulated. Verification applies each action's traffic allowance to recognised volume features of subsequent held-out rows and re-scores them with the saved model.
        A FAILURE means the detector still flags the behaviour; INCONCLUSIVE means no offending records or no measurable effect. These outcomes are not hidden or counted as successes.
      </ScopeNote>
    </div>
  );
}
