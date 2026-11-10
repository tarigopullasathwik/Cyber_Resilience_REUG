import { useEffect, useState } from "react";
import { Activity, Cpu, HardDrive, Play, Save, Server, Timer } from "lucide-react";
import { api } from "../api";
import { useFetch, useJob } from "../hooks";
import { Badge, Button, DataTable, EmptyState, ErrorNotice, Field, KeyValue, LoadingBlock, MetricBar, Panel, Progress, ScopeNote, Stat } from "../components/ui";
import { MiniArea } from "../components/charts";
import { formatDate, formatMetric, formatNumber, formatPercent } from "../lib/format";

export default function Resources() {
  const resources = useFetch("/api/resources", { poll: 3500 });
  const experiments = useFetch("/api/experiments");
  const [history, setHistory] = useState([]);
  const [budget, setBudget] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const [experimentId, setExperimentId] = useState("");
  const [sampleSize, setSampleSize] = useState(120);
  const [jobId, setJobId] = useState(null);
  const job = useJob(jobId, async (finished) => {
    if (finished.status === "completed") {
      setMessage("Benchmark completed on real held-out rows.");
      await resources.refresh();
    }
  });

  const data = resources.data;
  const host = data?.host || {};
  const edge = data?.edge || {};

  useEffect(() => {
    if (data?.host) {
      setHistory((current) => [...current.slice(-39), {
        time: new Date().toLocaleTimeString(),
        cpu: data.host.host_cpu_percent,
        memory: data.host.host_memory_percent,
      }]);
    }
  }, [data]);

  useEffect(() => {
    if (data?.edge?.budget && !budget) setBudget({ ...data.edge.budget });
  }, [data, budget]);

  const completed = (experiments.data || []).filter((item) => item.status === "completed");
  useEffect(() => {
    if (!experimentId && completed.length) setExperimentId(completed[0].id);
  }, [completed, experimentId]);

  const updateBudget = (key, value) => setBudget((current) => ({ ...current, [key]: Number(value) }));

  const saveBudget = async () => {
    if (!budget) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await api.setEdgeBudget(budget);
      await resources.refresh();
      setMessage("Simulated edge budget saved.");
    } catch (exc) {
      setError(exc);
    } finally {
      setSaving(false);
    }
  };

  const startBenchmark = async () => {
    if (!experimentId) return;
    setError(null);
    setMessage(null);
    try {
      const response = await api.benchmark({ experiment_id: experimentId, sample_size: Number(sampleSize) });
      setJobId(response.job.id);
    } catch (exc) {
      setError(exc);
    }
  };

  if (resources.loading && !data) return <LoadingBlock rows={7} />;

  return (
    <div className="space-y-4">
      {(error || resources.error) && <ErrorNotice error={error || resources.error} onRetry={resources.refresh} />}
      {message && <div className="rounded-lg border border-normal/20 bg-normal/[0.05] px-3.5 py-2.5 text-[11.5px] text-normal/90">{message}</div>}

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel
          title="Host measurements"
          subtitle="Actual psutil readings from the backend process and machine."
          action={<Badge tone="cyan" dot>MEASURED HOST</Badge>}
        >
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Host CPU" value={`${formatMetric(host.host_cpu_percent, 1)}%`} hint={`${host.logical_cpus || "—"} logical CPUs`} tone="cyan" icon={Cpu} />
            <Stat label="Host memory" value={`${formatMetric(host.host_memory_percent, 1)}%`} hint={`${formatMetric(host.host_memory_used_mb, 0)} / ${formatMetric(host.host_memory_total_mb, 0)} MB`} tone="blue" icon={HardDrive} />
            <Stat label="Backend RSS" value={`${formatMetric(host.process_rss_mb, 1)} MB`} hint={`${host.process_threads || "—"} threads`} tone="green" icon={Server} />
            <Stat label="Process CPU time" value={`${formatMetric(host.process_cpu_seconds, 1)} s`} hint="Cumulative user + system" tone="amber" icon={Timer} />
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div>
              <div className="mb-1 flex justify-between text-[10px] text-slate-500"><span>CPU trend</span><span className="font-mono">{formatMetric(host.host_cpu_percent, 1)}%</span></div>
              <MiniArea data={history} dataKey="cpu" color="#22d3ee" height={80} />
            </div>
            <div>
              <div className="mb-1 flex justify-between text-[10px] text-slate-500"><span>Memory trend</span><span className="font-mono">{formatMetric(host.host_memory_percent, 1)}%</span></div>
              <MiniArea data={history} dataKey="memory" color="#3b82f6" height={80} />
            </div>
          </div>
        </Panel>

        <Panel
          title="Simulated edge budget"
          subtitle="A configurable resource envelope used by the containment policy."
          action={<Badge tone="amber" dot>SIMULATED EDGE</Badge>}
        >
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="mb-1 flex justify-between text-[10px] text-slate-500"><span>CPU utilisation</span><span className="font-mono text-suspicious">{formatPercent(edge.simulated_cpu_utilisation)}</span></div>
              <MetricBar value={edge.simulated_cpu_utilisation || 0} tone="amber" />
            </div>
            <div>
              <div className="mb-1 flex justify-between text-[10px] text-slate-500"><span>Memory utilisation</span><span className="font-mono text-suspicious">{formatPercent(edge.simulated_memory_utilisation)}</span></div>
              <MetricBar value={edge.simulated_memory_utilisation || 0} tone="amber" />
            </div>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <div className="rounded-md border border-line/50 py-2"><div className="text-[9px] uppercase tracking-wide text-slate-600">CPU used</div><div className="font-mono text-sm text-slate-200">{formatMetric(edge.simulated_cpu_used, 3)}</div></div>
            <div className="rounded-md border border-line/50 py-2"><div className="text-[9px] uppercase tracking-wide text-slate-600">Headroom</div><div className="font-mono text-sm text-slate-200">{formatMetric(edge.simulated_cpu_headroom, 3)}</div></div>
            <div className="rounded-md border border-line/50 py-2"><div className="text-[9px] uppercase tracking-wide text-slate-600">Actions</div><div className="font-mono text-sm text-slate-200">{formatNumber(edge.active_containment_actions)}</div></div>
          </div>
          {budget && (
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Field label="CPU capacity (units)">
                <input className="input !py-1.5" type="number" step="0.05" min="0.05" value={budget.cpu_capacity} onChange={(event) => updateBudget("cpu_capacity", event.target.value)} />
              </Field>
              <Field label="Memory capacity (MB)">
                <input className="input !py-1.5" type="number" step="16" min="32" value={budget.memory_capacity_mb} onChange={(event) => updateBudget("memory_capacity_mb", event.target.value)} />
              </Field>
              <Field label="Uplink (kbps)">
                <input className="input !py-1.5" type="number" step="64" min="64" value={budget.bandwidth_capacity_kbps} onChange={(event) => updateBudget("bandwidth_capacity_kbps", event.target.value)} />
              </Field>
              <Field label="Latency budget (ms)">
                <input className="input !py-1.5" type="number" step="1" min="1" value={budget.latency_budget_ms} onChange={(event) => updateBudget("latency_budget_ms", event.target.value)} />
              </Field>
            </div>
          )}
          <Button variant="ghost" className="mt-2 w-full" onClick={saveBudget} loading={saving}><Save size={12} /> Save simulated budget</Button>
          <p className="mt-2 text-[9.5px] leading-relaxed text-slate-600">{edge.note}</p>
        </Panel>
      </div>

      <Panel
        title="Inference benchmark"
        subtitle="Measures end-to-end preprocessing plus scoring on real held-out rows."
        action={<Badge tone="cyan">wall-clock timing</Badge>}
      >
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <Field label="Experiment" className="flex-1">
            <select className="select" value={experimentId} onChange={(event) => setExperimentId(event.target.value)}>
              <option value="" disabled>Select an experiment…</option>
              {completed.map((experiment) => <option key={experiment.id} value={experiment.id}>{experiment.name}</option>)}
            </select>
          </Field>
          <Field label="Rows" className="w-full sm:w-28">
            <input className="input" type="number" min="20" max="500" value={sampleSize} onChange={(event) => setSampleSize(event.target.value)} />
          </Field>
          <Button onClick={startBenchmark} disabled={!experimentId} loading={job?.status === "running"}><Play size={12} /> Run benchmark</Button>
        </div>
        {job && <div className="mt-3"><Progress value={job.progress} message={job.message} tone={job.status === "failed" ? "red" : "cyan"} /></div>}
        {job?.error && <p className="mt-1 text-[10.5px] text-threat">{job.error}</p>}
        {job?.result?.measured && (
          <div className="mt-4 grid gap-3">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              <Stat label="Mean latency" value={`${formatMetric(job.result.measured.latency_mean_ms, 2)} ms`} tone="cyan" />
              <Stat label="p95 latency" value={`${formatMetric(job.result.measured.latency_p95_ms, 2)} ms`} tone="blue" />
              <Stat label="Throughput" value={`${formatMetric(job.result.measured.throughput_records_per_sec, 0)}/s`} tone="green" />
              <Stat label="Model size" value={`${formatMetric(job.result.measured.model_size_mb, 3)} MB`} tone="amber" />
              <Stat label="RSS delta" value={`${formatMetric(job.result.measured.rss_delta_mb, 2)} MB`} tone="neutral" />
            </div>
            <div className="grid gap-3 text-[10.5px] text-slate-500 sm:grid-cols-3">
              <span>Rows scored <span className="font-mono text-slate-300">{job.result.measured.records_scored}</span></span>
              <span>Backend CPU during run <span className="font-mono text-slate-300">{formatMetric(job.result.measured.cpu_percent_backend, 1)}%</span></span>
              <span>Latency budget <span className={`font-mono ${job.result.simulated_edge.meets_latency_budget ? "text-normal" : "text-threat"}`}>{job.result.simulated_edge.meets_latency_budget ? "met" : "exceeded"}</span></span>
            </div>
            <p className="text-[10px] leading-relaxed text-slate-600">{job.result.note}</p>
          </div>
        )}
        {!job?.result && (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-line/50 bg-ink-950/30 p-3 text-[10.5px] leading-relaxed text-slate-500">
              <Activity size={13} className="mb-1 text-cyan/60" /> The benchmark reuses the saved preprocessing pipeline and model artifact. It does not retrain.
            </div>
            <div className="rounded-lg border border-line/50 bg-ink-950/30 p-3 text-[10.5px] leading-relaxed text-slate-500">
              <Cpu size={13} className="mb-1 text-suspicious/70" /> Simulated edge budgets are separate from the host numbers and are used by the containment resource guard.
            </div>
          </div>
        )}
      </Panel>

      <Panel title="Recent benchmarks" subtitle="Stored measurements from this installation." flush>
        {(data?.latest_samples || []).length === 0 ? (
          <EmptyState icon={Timer} title="No benchmark samples" description="Run an inference benchmark to record measured latency and memory." />
        ) : (
          <DataTable
            dense
            columns={[
              { key: "created", label: "When", render: (row) => <span className="whitespace-nowrap text-slate-500">{formatDate(row.created_at)}</span> },
              { key: "experiment", label: "Experiment", render: (row) => <span className="font-mono text-[9.5px] text-slate-500">{row.experiment_id}</span> },
              { key: "latency", label: "Mean latency", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.payload?.measured?.latency_mean_ms, 2)} ms</span> },
              { key: "p95", label: "p95", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.payload?.measured?.latency_p95_ms, 2)} ms</span> },
              { key: "throughput", label: "Throughput", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.payload?.measured?.throughput_records_per_sec, 0)}/s</span> },
              { key: "size", label: "Model", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.payload?.measured?.model_size_mb, 3)} MB</span> },
              { key: "rows", label: "Rows", align: "right", render: (row) => <span className="font-mono">{formatNumber(row.payload?.measured?.records_scored)}</span> },
            ]}
            rows={data?.latest_samples || []}
          />
        )}
      </Panel>

      <ScopeNote>
        Host CPU, memory, RSS and latency are real measurements. The edge gateway budget, its utilisation, and action costs are simulated research parameters, not readings from embedded hardware.
      </ScopeNote>
    </div>
  );
}
