import { useEffect, useState } from "react";
import { Download, FileJson, FileSpreadsheet, FileText, RefreshCw, ShieldCheck } from "lucide-react";
import { api } from "../api";
import { useFetch } from "../hooks";
import { Badge, Button, DataTable, EmptyState, ErrorNotice, Field, Panel, ScopeNote } from "../components/ui";
import { formatDate, formatMetric } from "../lib/format";

export default function Reports() {
  const experiments = useFetch("/api/experiments");
  const reports = useFetch("/api/reports");
  const [experimentId, setExperimentId] = useState("");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);

  const completed = (experiments.data || []).filter((item) => item.status === "completed");
  useEffect(() => {
    if (!experimentId && completed.length) setExperimentId(completed[0].id);
  }, [completed, experimentId]);

  const selected = completed.find((experiment) => experiment.id === experimentId);

  const generate = async () => {
    if (!experimentId) return;
    setGenerating(true);
    setError(null);
    setMessage(null);
    try {
      const report = await api.createReport(experimentId);
      await reports.refresh();
      setMessage("Report generated from the stored experiment, prediction and containment artifacts.");
      window.open(api.reportDownloadUrl(report.id), "_blank", "noopener");
    } catch (exc) {
      setError(exc);
    } finally {
      setGenerating(false);
    }
  };

  if (experiments.loading && !experiments.data) return <div className="skeleton h-72" />;

  return (
    <div className="space-y-4">
      {error && <ErrorNotice error={error} onRetry={() => setError(null)} />}
      {message && <div className="rounded-lg border border-normal/20 bg-normal/[0.05] px-3.5 py-2.5 text-[11.5px] text-normal/90">{message}</div>}

      <div className="grid gap-4 xl:grid-cols-[1.1fr_1fr]">
        <Panel title="Generate an experimental report" subtitle="The PDF is built from stored metrics, per-family results, containment events and resource samples.">
          {!completed.length ? (
            <EmptyState icon={FileText} title="No completed experiments" description="Train and evaluate a model before generating a report." />
          ) : (
            <div className="space-y-3">
              <Field label="Experiment">
                <select className="select" value={experimentId} onChange={(event) => setExperimentId(event.target.value)}>
                  {completed.map((experiment) => <option key={experiment.id} value={experiment.id}>{experiment.name}</option>)}
                </select>
              </Field>
              {selected && (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <div className="rounded-md border border-line/50 p-2.5"><div className="text-[9px] uppercase tracking-wide text-slate-600">Accuracy</div><div className="font-mono text-sm text-slate-200">{formatMetric(selected.metrics?.accuracy)}</div></div>
                  <div className="rounded-md border border-line/50 p-2.5"><div className="text-[9px] uppercase tracking-wide text-slate-600">F1</div><div className="font-mono text-sm text-slate-200">{formatMetric(selected.metrics?.f1)}</div></div>
                  <div className="rounded-md border border-line/50 p-2.5"><div className="text-[9px] uppercase tracking-wide text-slate-600">FPR</div><div className="font-mono text-sm text-suspicious">{formatMetric(selected.metrics?.false_positive_rate)}</div></div>
                  <div className="rounded-md border border-line/50 p-2.5"><div className="text-[9px] uppercase tracking-wide text-slate-600">Unknown recall</div><div className="font-mono text-sm text-threat">{formatMetric(selected.metrics?.unknown_attack_recall)}</div></div>
                </div>
              )}
              <Button className="w-full" onClick={generate} loading={generating} disabled={!experimentId}>
                <FileText size={13} /> Generate PDF report
              </Button>
              <div className="rounded-lg border border-line/50 bg-ink-950/30 p-3">
                <div className="flex items-center gap-2 text-[10.5px] font-semibold text-slate-300"><ShieldCheck size={12} className="text-cyan/70" /> Included in the report</div>
                <ul className="mt-2 grid gap-1 text-[10px] text-slate-500 sm:grid-cols-2">
                  {["Dataset and version", "Target and benign labels", "Preprocessing split and leakage controls", "Model and hyperparameters", "Held-out test metrics", "Confusion matrix", "Per-class and per-family results", "Unknown-attack protocol", "Containment events", "Measured resource observations", "Scope and limitations"].map((item) => (
                    <li key={item} className="flex gap-1.5"><span className="text-normal/70">✓</span>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </Panel>

        <Panel title="Raw exports" subtitle="Read directly from the experiment record; no recomputation on the client.">
          {selected ? (
            <div className="space-y-2">
              <a className="flex items-center justify-between rounded-lg border border-line/60 px-3 py-3 transition hover:border-cyan/30 hover:bg-ink-800/40" href={api.exportUrl(selected.id, "csv")}>
                <div className="flex items-center gap-2.5"><FileSpreadsheet size={16} className="text-normal/80" /><div><div className="text-[11.5px] font-semibold text-slate-200">Metrics CSV</div><div className="text-[9.5px] text-slate-600">One row per stored metric</div></div></div>
                <Download size={13} className="text-slate-500" />
              </a>
              <a className="flex items-center justify-between rounded-lg border border-line/60 px-3 py-3 transition hover:border-cyan/30 hover:bg-ink-800/40" href={api.exportUrl(selected.id, "json")}>
                <div className="flex items-center gap-2.5"><FileJson size={16} className="text-suspicious/80" /><div><div className="text-[11.5px] font-semibold text-slate-200">Full experiment JSON</div><div className="text-[9.5px] text-slate-600">Experiment, dataset, preprocessing, containment</div></div></div>
                <Download size={13} className="text-slate-500" />
              </a>
              <div className="rounded-lg border border-line/50 bg-ink-950/30 p-3 text-[10px] leading-relaxed text-slate-500">
                The PDF includes the research scope note: containment and edge budgets are simulated, host timings are measured, and withheld-family recall is not evidence of zero-day detection.
              </div>
            </div>
          ) : <EmptyState icon={FileText} title="Select an experiment" description="Choose a completed experiment to export." />}
        </Panel>
      </div>

      <Panel
        title="Generated reports"
        subtitle="Reports are versioned files; regenerate after changing an experiment."
        action={<Button variant="ghost" onClick={reports.refresh}><RefreshCw size={12} /> Refresh</Button>}
        flush
      >
        <DataTable
          columns={[
            { key: "title", label: "Report", render: (row) => <span className="text-slate-200">{row.title}</span> },
            { key: "format", label: "Format", render: (row) => <Badge tone="blue">{row.format.toUpperCase()}</Badge> },
            { key: "experiment", label: "Experiment", render: (row) => <span className="font-mono text-[9.5px] text-slate-500">{row.experiment_id}</span> },
            { key: "created", label: "Created", render: (row) => <span className="whitespace-nowrap text-slate-500">{formatDate(row.created_at)}</span> },
            { key: "exists", label: "File", render: (row) => <Badge tone={row.exists ? "green" : "red"}>{row.exists ? "available" : "missing"}</Badge> },
            { key: "download", label: "", align: "right", render: (row) => <a className="inline-flex items-center gap-1 text-[10px] font-semibold text-cyan/80 hover:text-cyan" href={api.reportDownloadUrl(row.id)}><Download size={11} /> PDF</a> },
          ]}
          rows={reports.data || []}
          empty="No reports generated yet."
        />
      </Panel>

      <ScopeNote>
        PDF generation uses reportlab on the backend and reads only stored artifacts. If a report fails, no placeholder or invented metrics are created.
      </ScopeNote>
    </div>
  );
}
