import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Play, RefreshCw, ShieldAlert, ShieldOff } from "lucide-react";
import { api } from "../api";
import { useFetch, useJob } from "../hooks";
import { Badge, Button, DataTable, EmptyState, ErrorNotice, Field, KeyValue, LoadingBlock, Panel, Progress, ScopeNote, Stat } from "../components/ui";
import { CompositionChart, CurveChart, ScoreHistogram } from "../components/charts";
import { formatMetric, formatNumber, titleCase } from "../lib/format";

export default function UnknownAttacks() {
  const runs = useFetch("/api/preprocess/runs");
  const models = useFetch("/api/models");
  const experiments = useFetch("/api/experiments?kind=unknown");
  const [runId, setRunId] = useState("");
  const [mode, setMode] = useState("holdout");
  const [selectedFamilies, setSelectedFamilies] = useState([]);
  const [supervisedModel, setSupervisedModel] = useState("random_forest");
  const [anomalyModel, setAnomalyModel] = useState("isolation_forest");
  const [thresholdQuantile, setThresholdQuantile] = useState(0.99);
  const [maxFamilies, setMaxFamilies] = useState(5);
  const [jobId, setJobId] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);

  const families = useFetch(runId ? `/api/preprocess/runs/${runId}/families` : null);
  const job = useJob(jobId, async (finished) => {
    if (finished.status === "completed") {
      setMessage("Unknown-attack evaluation finished. Held-out families were excluded from training.");
      await experiments.refresh();
      setSelectedId(finished.result?.id || null);
    }
  });

  useEffect(() => {
    if (!runId && runs.data?.length) setRunId(runs.data[0].id);
  }, [runs.data, runId]);

  useEffect(() => {
    if (!selectedId && experiments.data?.length) setSelectedId(experiments.data[0].id);
  }, [experiments.data, selectedId]);

  useEffect(() => {
    const available = families.data?.families || [];
    setSelectedFamilies((current) => current.filter((family) => available.includes(family)).slice(0, 3));
  }, [families.data]);

  const detail = useFetch(selectedId ? `/api/experiments/${selectedId}` : null);
  const experiment = detail.data;
  const metrics = experiment?.metrics || {};
  const curves = experiment?.curves || {};
  const run = runs.data?.find((item) => item.id === runId) || null;

  const histogram = (curves.score_histogram || []).map((row) => ({
    bin: row.bin,
    benign: row.benign,
    known: row.known,
    unknown: row.unknown,
  }));
  const composition = curves.composition || {};
  const compositionData = useMemo(() => ([
    { name: "Benign correct", value: composition.benign || 0, color: "#34d399" },
    { name: "Known detected", value: composition.known_malicious || 0, color: "#fbbf24" },
    { name: "Suspected unknown", value: composition.suspected_unknown || 0, color: "#f87171" },
    { name: "Missed attacks", value: (composition.known_missed || 0) + (composition.unknown_missed || 0), color: "#475569" },
  ]), [composition]);
  const rocSeries = curves.known_vs_benign?.roc?.length
    ? [{ name: "Known vs benign", color: "#22d3ee", points: curves.known_vs_benign.roc }]
    : [];

  const start = async () => {
    if (!runId) return;
    setError(null);
    setMessage(null);
    if (mode === "holdout" && !selectedFamilies.length) {
      setError(new Error("Select at least one attack family to withhold."));
      return;
    }
    try {
      const response = await api.startUnknown({
        preprocess_id: runId,
        mode,
        holdout_families: selectedFamilies,
        supervised_model: supervisedModel,
        anomaly_model: anomalyModel,
        threshold_quantile: Number(thresholdQuantile),
        max_families: Number(maxFamilies),
      });
      setJobId(response.job.id);
      setSelectedId(response.experiment.id);
    } catch (exc) {
      setError(exc);
    }
  };

  const supervisedOptions = (models.data || []).filter((model) => model.family === "supervised" && model.available);
  const anomalyOptions = (models.data || []).filter((model) => model.family === "anomaly" && model.available);

  return (
    <div className="space-y-4">
      {error && <ErrorNotice error={error} onRetry={() => setError(null)} />}
      {message && <div className="rounded-lg border border-normal/20 bg-normal/[0.05] px-3.5 py-2.5 text-[11.5px] text-normal/90">{message}</div>}

      <div className="grid gap-4 xl:grid-cols-[0.9fr_1.45fr]">
        <Panel title="Unknown-attack protocol" subtitle="Held-out families never contribute to fitting or threshold calibration.">
          <div className="space-y-3">
            <Field label="Preprocessed dataset">
              <select className="select" value={runId} onChange={(event) => setRunId(event.target.value)}>
                <option value="" disabled>Select a preprocessing run…</option>
                {(runs.data || []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </Field>
            {run && (
              <div className="rounded-md border border-line/50 bg-ink-950/30 px-3 py-2 text-[10px] text-slate-500">
                {formatNumber(run.train_rows)} train · {formatNumber(run.test_rows)} test · {run.families?.length || 0} attack families available
              </div>
            )}

            <div>
              <span className="label mb-1.5 block">Evaluation design</span>
              <div className="grid grid-cols-2 gap-2">
                {[
                  ["holdout", "Withhold families", "Train without selected families once."],
                  ["lofo", "Leave-one-family-out", "Retrain per family; honest generalisation table."],
                ].map(([value, label, hint]) => (
                  <button
                    key={value}
                    onClick={() => setMode(value)}
                    className={`rounded-lg border px-2.5 py-2 text-left transition ${mode === value ? "border-cyan/40 bg-cyan/[0.06]" : "border-line/60 hover:border-slate-500/50"}`}
                  >
                    <div className="text-[11px] font-semibold text-slate-200">{label}</div>
                    <div className="mt-0.5 text-[9px] leading-snug text-slate-600">{hint}</div>
                  </button>
                ))}
              </div>
            </div>

            {mode === "holdout" && (
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="label">Families to withhold</span>
                  <span className="text-[9px] text-slate-600">{selectedFamilies.length} selected</span>
                </div>
                {families.loading ? <LoadingBlock rows={2} /> : (
                  <div className="max-h-[150px] space-y-1 overflow-auto rounded-lg border border-line/50 p-2">
                    {(families.data?.families || []).length === 0 && <p className="text-[10px] text-slate-600">No attack families in the test split.</p>}
                    {(families.data?.families || []).map((family) => (
                      <label key={family} className="flex cursor-pointer items-center justify-between gap-2 rounded px-1 py-0.5 text-[10.5px] text-slate-400 hover:bg-ink-800/50">
                        <span className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            className="h-3 w-3 accent-cyan"
                            checked={selectedFamilies.includes(family)}
                            onChange={(event) => setSelectedFamilies((current) => event.target.checked ? [...current, family] : current.filter((item) => item !== family))}
                          />
                          {family}
                        </span>
                        <span className="font-mono text-[9px] text-slate-600">{formatNumber(families.data?.test_counts?.[family] || 0)} test</span>
                      </label>
                    ))}
                  </div>
                )}
                <p className="mt-1 text-[9px] leading-relaxed text-slate-600">Families must exist in the test split. Rows from selected families are removed from train and validation.</p>
              </div>
            )}

            <div className="grid grid-cols-2 gap-2">
              <Field label="Supervised detector">
                <select className="select" value={supervisedModel} onChange={(event) => setSupervisedModel(event.target.value)}>
                  {supervisedOptions.map((model) => <option key={model.key} value={model.key}>{model.label}</option>)}
                </select>
              </Field>
              <Field label="Anomaly detector">
                <select className="select" value={anomalyModel} onChange={(event) => setAnomalyModel(event.target.value)}>
                  {anomalyOptions.map((model) => <option key={model.key} value={model.key}>{model.label}</option>)}
                </select>
              </Field>
              <Field label="Anomaly threshold quantile">
                <input className="input" type="number" step="0.005" min="0.5" max="0.999" value={thresholdQuantile} onChange={(event) => setThresholdQuantile(event.target.value)} />
              </Field>
              <Field label={mode === "lofo" ? "Max LOFO families" : "Random seed"}>
                {mode === "lofo" ? (
                  <input className="input" type="number" min="1" max="12" value={maxFamilies} onChange={(event) => setMaxFamilies(event.target.value)} />
                ) : <input className="input" type="number" value="42" disabled />}
              </Field>
            </div>

            {job && <Progress value={job.progress} message={job.message} tone={job.status === "failed" ? "red" : "cyan"} />}
            {job?.error && <p className="text-[10.5px] leading-relaxed text-threat">{job.error}</p>}
            <Button className="w-full" onClick={start} disabled={!runId || (mode === "holdout" && !selectedFamilies.length)} loading={job?.status === "running"}>
              <Play size={13} /> Run unknown-attack experiment
            </Button>
            <ScopeNote>Held-out recall is a proxy for unknown-attack sensitivity, not proof of zero-day detection.</ScopeNote>
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel
            title={experiment ? experiment.name : "Experiment result"}
            subtitle={experiment ? `${metrics.mode === "lofo" ? "Leave-one-family-out" : "Withheld families"} · ${experiment.model_name}` : "Run or select an unknown-attack experiment."}
            action={experiment && <Badge tone="blue">{titleCase(experiment.status)}</Badge>}
          >
            {detail.loading && !experiment ? <LoadingBlock rows={5} /> : !experiment ? (
              <EmptyState icon={ShieldOff} title="No unknown-attack experiment" description="Choose families to withhold, then run the protocol." />
            ) : experiment.status !== "completed" ? (
              <div className="space-y-2"><Progress value={experiment.progress} message={experiment.message} tone={experiment.status === "failed" ? "red" : "cyan"} />{experiment.status === "failed" && <p className="text-[10.5px] text-threat">{experiment.message}</p>}</div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <Stat label="Known recall" value={formatMetric(metrics.known_attack_recall)} tone="amber" />
                  <Stat label={metrics.mode === "lofo" ? "LOFO unknown recall" : "Withheld recall"} value={formatMetric(metrics.unknown_attack_recall)} tone="red" />
                  <Stat label="Benign FPR" value={formatMetric(metrics.benign_false_positive_rate)} tone="green" />
                  <Stat label="Threshold" value={formatMetric(metrics.threshold)} tone="cyan" />
                </div>
                <div className="grid gap-4 md:grid-cols-[1fr_220px]">
                  <div>
                    <div className="eyebrow mb-1">Fused score distribution by group</div>
                    <ScoreHistogram
                      series={[
                        { key: "benign", name: "Benign", color: "#34d399" },
                        { key: "known", name: "Known attacks", color: "#fbbf24" },
                        { key: "unknown", name: "Withheld / unknown", color: "#f87171" },
                      ]}
                      data={histogram}
                      height={220}
                    />
                  </div>
                  <div>
                    <div className="eyebrow mb-1">Test composition</div>
                    <CompositionChart data={compositionData} height={200} />
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <div className="eyebrow mb-1">Known attack vs benign ROC</div>
                    <CurveChart series={rocSeries} height={210} />
                  </div>
                  <div>
                    <div className="eyebrow mb-2">Protocol details</div>
                    <KeyValue
                      items={[
                        { label: "Mode", value: metrics.mode === "lofo" ? "LOFO retraining" : "Single holdout" },
                        { label: "Withheld families", value: (metrics.heldout_families || []).join(", ") || "—" },
                        { label: "Known test rows", value: formatNumber(metrics.n_known) },
                        { label: "Withheld test rows", value: formatNumber(metrics.n_unknown) },
                        { label: "Benign test rows", value: formatNumber(metrics.n_benign) },
                        { label: "Supervised model", value: metrics.supervised_model },
                        { label: "Anomaly model", value: metrics.anomaly_model },
                        { label: "LOFO mean unknown recall", value: formatMetric(metrics.lofo_mean_unknown_recall) },
                      ]}
                    />
                  </div>
                </div>

                {(curves.lofo || []).length > 0 ? (
                  <div>
                    <div className="eyebrow mb-2">Leave-one-family-out results</div>
                    <DataTable
                      dense
                      columns={[
                        { key: "family", label: "Withheld family", render: (row) => <span className="text-slate-200">{row.family}</span> },
                        { key: "support", label: "Support", align: "right" },
                        { key: "fused_recall", label: "Fused recall", align: "right", render: (row) => <span className="font-mono text-cyan/80">{formatMetric(row.fused_recall)}</span> },
                        { key: "anomaly_recall", label: "Anomaly recall", align: "right", render: (row) => <span className="font-mono text-slate-300">{formatMetric(row.anomaly_recall)}</span> },
                        { key: "benign_fpr", label: "Benign FPR", align: "right", render: (row) => <span className="font-mono text-suspicious">{formatMetric(row.benign_fpr)}</span> },
                        { key: "mean_score", label: "Mean score", align: "right", render: (row) => <span className="font-mono text-slate-400">{formatMetric(row.mean_score)}</span> },
                      ]}
                      rows={curves.lofo}
                      empty="No LOFO folds completed."
                    />
                  </div>
                ) : (
                  <div>
                    <div className="eyebrow mb-2">Recall per family</div>
                    <DataTable
                      dense
                      columns={[
                        { key: "family", label: "Family", render: (row) => <span className="text-slate-200">{row.family}</span> },
                        { key: "support", label: "Support", align: "right" },
                        { key: "withheld", label: "Held out", render: (row) => <Badge tone={row.withheld ? "red" : "neutral"}>{row.withheld ? "yes" : "no"}</Badge> },
                        { key: "supervised_recall", label: "Supervised", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.supervised_recall)}</span> },
                        { key: "anomaly_recall", label: "Anomaly", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.anomaly_recall)}</span> },
                        { key: "fused_recall", label: "Fused", align: "right", render: (row) => <span className="font-mono text-cyan/80">{formatMetric(row.fused_recall)}</span> },
                      ]}
                      rows={experiment.per_family || []}
                      empty="No per-family test rows."
                    />
                  </div>
                )}

                <ScopeNote>
                  {metrics.mode === "lofo"
                    ? "Each row is a fresh model trained without that family. LOFO mean recall is the average across the completed folds. This is a stronger generalization test than a single holdout but still depends on this dataset."
                    : "The supervised model never saw the withheld family; the anomaly detector was fitted on benign rows only. Report both known and withheld recall together with the benign false-positive rate."}
                </ScopeNote>
              </div>
            )}
          </Panel>
        </div>
      </div>

      <Panel
        title="Unknown-attack history"
        subtitle="Every study keeps its held-out families, threshold and per-family results."
        action={<Button variant="ghost" onClick={experiments.refresh}><RefreshCw size={12} /> Refresh</Button>}
        flush
      >
        <DataTable
          columns={[
            { key: "name", label: "Study", render: (row) => <button onClick={() => setSelectedId(row.id)} className={selectedId === row.id ? "text-cyan" : "text-slate-200"}>{row.name}</button> },
            { key: "mode", label: "Mode", render: (row) => <Badge tone="blue">{row.metrics?.mode || "—"}</Badge> },
            { key: "known", label: "Known recall", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.metrics?.known_attack_recall)}</span> },
            { key: "unknown", label: "Unknown recall", align: "right", render: (row) => <span className="font-mono text-threat">{formatMetric(row.metrics?.unknown_attack_recall)}</span> },
            { key: "fpr", label: "Benign FPR", align: "right", render: (row) => <span className="font-mono text-suspicious">{formatMetric(row.metrics?.benign_false_positive_rate)}</span> },
            { key: "status", label: "Status", render: (row) => <Badge tone={row.status === "completed" ? "green" : row.status === "failed" ? "red" : "amber"}>{row.status}</Badge> },
            { key: "actions", label: "", align: "right", render: (row) => <Link to="/analytics" className="text-[10px] font-semibold text-cyan/80">Analytics</Link> },
          ]}
          rows={experiments.data || []}
          empty="No unknown-attack experiments yet."
        />
      </Panel>

      <ScopeNote>
        <ShieldAlert size={11} className="mt-0.5 inline" /> Do not describe these results as zero-day detection. Withheld families come from the same dataset and the same feature pipeline, and the dataset label decides ground truth.
      </ScopeNote>
    </div>
  );
}
