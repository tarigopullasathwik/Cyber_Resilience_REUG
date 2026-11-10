import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { BarChart3, Download, FileText, RefreshCw } from "lucide-react";
import { api } from "../api";
import { useFetch } from "../hooks";
import { Badge, Button, DataTable, EmptyState, ErrorNotice, LoadingBlock, Panel, ScopeNote } from "../components/ui";
import { CurveChart, FeatureImportance, MetricComparison } from "../components/charts";
import { formatDate, formatMetric, formatNumber, titleCase } from "../lib/format";

const METRICS = [
  { key: "accuracy", label: "Accuracy" },
  { key: "precision", label: "Precision" },
  { key: "recall", label: "Recall" },
  { key: "f1", label: "F1" },
];

export default function Analytics() {
  const experiments = useFetch("/api/experiments");
  const [selectedIds, setSelectedIds] = useState([]);
  const [detailId, setDetailId] = useState(null);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const [generating, setGenerating] = useState(false);

  const completed = useMemo(() => (experiments.data || []).filter((item) => item.status === "completed"), [experiments.data]);

  useEffect(() => {
    if (!selectedIds.length && completed.length) setSelectedIds(completed.slice(0, 3).map((item) => item.id));
  }, [completed, selectedIds]);

  useEffect(() => {
    if (!detailId && selectedIds.length) setDetailId(selectedIds[0]);
  }, [selectedIds, detailId]);

  const compare = useFetch(selectedIds.length ? `/api/analytics/compare?ids=${selectedIds.join(",")}` : "/api/analytics/compare");
  const detail = useFetch(detailId ? `/api/experiments/${detailId}` : null);

  const selectedExperiments = compare.data?.experiments || [];
  const metricRows = selectedExperiments.map((experiment) => ({
    label: experiment.model_name.replaceAll("_", " ").slice(0, 14),
    ...Object.fromEntries(METRICS.map((metric) => [metric.key, experiment.metrics?.[metric.key] ?? null])),
  }));
  const rocSeries = selectedExperiments.map((experiment, index) => ({
    name: experiment.name,
    color: ["#22d3ee", "#fbbf24", "#a78bfa", "#34d399"][index % 4],
    points: experiment.curves?.roc || experiment.curves?.known_vs_benign?.roc || [],
  }));
  const prSeries = selectedExperiments.map((experiment, index) => ({
    name: experiment.name,
    color: ["#22d3ee", "#fbbf24", "#a78bfa", "#34d399"][index % 4],
    points: experiment.curves?.pr || experiment.curves?.known_vs_benign?.pr || [],
  }));

  const toggle = (id) => {
    setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id].slice(-4));
  };

  const downloadPdf = async () => {
    if (!detailId) return;
    setGenerating(true);
    setError(null);
    try {
      const report = await api.createReport(detailId);
      window.open(api.reportDownloadUrl(report.id), "_blank", "noopener");
      setMessage("Report generated from stored experiment artifacts.");
    } catch (exc) {
      setError(exc);
    } finally {
      setGenerating(false);
    }
  };

  if (experiments.loading && !experiments.data) return <LoadingBlock rows={7} />;

  return (
    <div className="space-y-4">
      {error && <ErrorNotice error={error} onRetry={() => setError(null)} />}
      {message && <div className="rounded-lg border border-normal/20 bg-normal/[0.05] px-3.5 py-2.5 text-[11.5px] text-normal/90">{message}</div>}

      {!completed.length ? (
        <Panel><EmptyState icon={BarChart3} title="No completed experiments" description="Train a model to populate research analytics." action={<Link to="/models" className="btn btn-primary">Open ML Laboratory</Link>} /></Panel>
      ) : (
        <>
          <Panel
            title="Model comparison"
            subtitle="Select up to four completed experiments. All metrics come from their stored held-out test predictions."
            action={<Button variant="ghost" onClick={experiments.refresh}><RefreshCw size={12} /> Refresh</Button>}
          >
            <div className="mb-3 flex flex-wrap gap-1.5">
              {completed.map((experiment) => (
                <button
                  key={experiment.id}
                  onClick={() => toggle(experiment.id)}
                  className={`badge normal-case tracking-normal ${selectedIds.includes(experiment.id) ? "badge-cyan" : "badge-neutral"}`}
                >
                  {experiment.model_name} · {experiment.id.slice(-4)}
                </button>
              ))}
            </div>
            {compare.loading && !compare.data ? <LoadingBlock rows={4} /> : (
              <div className="grid gap-4 xl:grid-cols-2">
                <div>
                  <div className="eyebrow mb-1">Detection metrics</div>
                  <MetricComparison rows={metricRows} metrics={METRICS} height={270} />
                </div>
                <div>
                  <div className="eyebrow mb-1">ROC · known attack vs benign</div>
                  <CurveChart series={rocSeries} height={270} />
                </div>
                <div>
                  <div className="eyebrow mb-1">Precision-recall</div>
                  <CurveChart series={prSeries} xKey="recall" yKey="precision" xLabel="Recall" yLabel="Precision" height={250} />
                </div>
                <div>
                  <div className="eyebrow mb-2">Measured inference cost</div>
                  <DataTable
                    dense
                    columns={[
                      { key: "name", label: "Experiment", render: (row) => <button onClick={() => setDetailId(row.id)} className={detailId === row.id ? "text-cyan" : "text-slate-300"}>{row.model_name}</button> },
                      { key: "latency", label: "Latency", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.metrics?.inference_latency_ms_mean, 2)} ms</span> },
                      { key: "throughput", label: "Throughput", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.metrics?.throughput_records_per_sec, 0)}/s</span> },
                      { key: "size", label: "Model", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.metrics?.model_size_mb, 3)} MB</span> },
                      { key: "fpr", label: "FPR", align: "right", render: (row) => <span className="font-mono text-suspicious">{formatMetric(row.metrics?.false_positive_rate)}</span> },
                    ]}
                    rows={selectedExperiments}
                    empty="Select experiments."
                  />
                </div>
              </div>
            )}
          </Panel>

          <Panel
            title="Comparison table"
            subtitle="Download exports or generate a PDF report for the selected experiment."
            action={
              <div className="flex flex-wrap gap-2">
                <a className="btn btn-ghost" href={detailId ? api.exportUrl(detailId, "csv") : "#"} aria-disabled={!detailId}><Download size={12} /> CSV</a>
                <a className="btn btn-ghost" href={detailId ? api.exportUrl(detailId, "json") : "#"} aria-disabled={!detailId}><Download size={12} /> JSON</a>
                <Button onClick={downloadPdf} loading={generating} disabled={!detailId}><FileText size={12} /> PDF report</Button>
              </div>
            }
            flush
          >
            <DataTable
              columns={[
                { key: "name", label: "Experiment", render: (row) => <button onClick={() => setDetailId(row.id)} className={detailId === row.id ? "text-cyan" : "text-slate-200"}>{row.name}</button> },
                { key: "kind", label: "Kind", render: (row) => <Badge tone={row.kind === "unknown" ? "blue" : row.kind === "anomaly" ? "amber" : "neutral"}>{row.kind}</Badge> },
                { key: "accuracy", label: "Accuracy", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.accuracy)}</span> },
                { key: "precision", label: "Precision", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.precision)}</span> },
                { key: "recall", label: "Recall", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.recall)}</span> },
                { key: "f1", label: "F1", align: "right", render: (row) => <span className="font-mono text-cyan/80">{formatMetric(row.f1)}</span> },
                { key: "fpr", label: "FPR", align: "right", render: (row) => <span className="font-mono text-suspicious">{formatMetric(row.false_positive_rate)}</span> },
                { key: "roc", label: "ROC AUC", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.roc_auc)}</span> },
                { key: "unknown", label: "Unknown recall", align: "right", render: (row) => <span className="font-mono text-threat">{formatMetric(row.unknown_recall)}</span> },
                { key: "date", label: "Completed", render: (row) => <span className="whitespace-nowrap text-slate-500">{formatDate(row.completed_at)}</span> },
              ]}
              rows={compare.data?.table || []}
              empty="No comparison rows."
            />
          </Panel>

          <Panel
            title={detail.data ? detail.data.name : "Experiment detail"}
            subtitle="Per-class performance, per-family recall and feature attribution for the selected experiment."
            action={detail.data && <Badge tone="green">{titleCase(detail.data.kind)}</Badge>}
          >
            {detail.loading && !detail.data ? <LoadingBlock rows={4} /> : !detail.data ? <EmptyState icon={BarChart3} title="Select an experiment" description="Choose a row in the comparison table." /> : (
              <div className="grid gap-4 lg:grid-cols-2">
                <div>
                  <div className="eyebrow mb-2">Per-class performance · {formatNumber(detail.data.metrics?.n_test)} test rows</div>
                  <DataTable
                    dense
                    columns={[
                      { key: "class", label: "Class", render: (row) => <span className="text-slate-200">{titleCase(row.class)}</span> },
                      { key: "support", label: "Support", align: "right", render: (row) => <span className="font-mono">{formatNumber(row.support)}</span> },
                      { key: "predicted_positive", label: "Detected", align: "right", render: (row) => <span className="font-mono">{formatNumber(row.predicted_positive)}</span> },
                      { key: "recall", label: "Recall", align: "right", render: (row) => <span className="font-mono text-cyan/80">{formatMetric(row.recall)}</span> },
                      { key: "mean_score", label: "Mean score", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.mean_score)}</span> },
                    ]}
                    rows={detail.data.per_class || []}
                    empty="No per-class rows."
                  />
                  <div className="mt-3">
                    <div className="eyebrow mb-2">Per-family recall</div>
                    <DataTable
                      dense
                      columns={[
                        { key: "family", label: "Family", render: (row) => <span className="text-slate-300">{row.family}</span> },
                        { key: "support", label: "Support", align: "right" },
                        { key: "recall", label: "Recall", align: "right", render: (row) => <span className="font-mono text-cyan/80">{formatMetric(row.recall ?? row.fused_recall)}</span> },
                      ]}
                      rows={detail.data.per_family || []}
                      empty="No family labels."
                    />
                  </div>
                </div>
                <div>
                  <div className="eyebrow mb-1">Feature importance</div>
                  <FeatureImportance items={detail.data.feature_importance} height={320} />
                </div>
              </div>
            )}
          </Panel>
        </>
      )}

      <ScopeNote>
        Comparison metrics are calculated from each experiment's saved test predictions. Exports and PDF reports read stored artifacts; changing a chart filter never changes the underlying metric.
      </ScopeNote>
    </div>
  );
}
