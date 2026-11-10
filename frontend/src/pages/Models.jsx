import { useEffect, useMemo, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { ArrowRight, Boxes, FlaskConical, Gauge, Play, RefreshCw, Save, Upload } from "lucide-react";
import { api } from "../api";
import { useFetch, useJob } from "../hooks";
import { Badge, Button, DataTable, EmptyState, ErrorNotice, Field, KeyValue, LoadingBlock, Panel, Progress, ScopeNote, Stat } from "../components/ui";
import { CurveChart, FeatureImportance } from "../components/charts";
import { formatDate, formatMetric, formatNumber, titleCase } from "../lib/format";

const PARAM_FIELDS = {
  random_forest: [
    { key: "n_estimators", label: "Trees", type: "number", min: 10, max: 800 },
    { key: "max_depth", label: "Max depth", type: "number", min: 1, max: 60, optional: true },
    { key: "min_samples_leaf", label: "Min samples / leaf", type: "number", min: 1, max: 50 },
  ],
  xgboost: [
    { key: "n_estimators", label: "Boosting rounds", type: "number", min: 20, max: 800 },
    { key: "max_depth", label: "Max depth", type: "number", min: 1, max: 16 },
    { key: "learning_rate", label: "Learning rate", type: "number", step: 0.01, min: 0.01, max: 1 },
  ],
  decision_tree: [
    { key: "max_depth", label: "Max depth", type: "number", min: 1, max: 60 },
    { key: "min_samples_leaf", label: "Min samples / leaf", type: "number", min: 1, max: 50 },
  ],
  logistic_regression: [
    { key: "C", label: "Inverse regularisation (C)", type: "number", step: 0.1, min: 0.01, max: 100 },
    { key: "max_iter", label: "Max iterations", type: "number", min: 100, max: 5000 },
  ],
  isolation_forest: [{ key: "n_estimators", label: "Trees", type: "number", min: 20, max: 600 }],
  one_class_svm: [{ key: "nu", label: "Nu (outlier fraction)", type: "number", step: 0.01, min: 0.01, max: 0.5 }],
  autoencoder: [
    { key: "hidden", label: "Hidden units", type: "number", min: 8, max: 128 },
    { key: "max_iter", label: "Max epochs", type: "number", min: 20, max: 600 },
  ],
};

function defaultParams(modelKey) {
  return Object.fromEntries((PARAM_FIELDS[modelKey] || []).map((field) => [field.key, field.optional ? "" : ""]));
}

function ConfusionMatrix({ metrics }) {
  if (!metrics) return null;
  return (
    <div className="grid grid-cols-[auto_1fr_1fr] gap-1 text-center text-[10px]">
      <div />
      <div className="eyebrow !text-[9px]">Pred benign</div>
      <div className="eyebrow !text-[9px]">Pred malicious</div>
      <div className="flex items-center justify-end pr-1 text-[9px] uppercase tracking-wide text-slate-500">True benign</div>
      <div className="rounded-md border border-normal/20 bg-normal/[0.06] p-3 font-mono text-lg text-normal">{formatNumber(metrics.tn)}</div>
      <div className="rounded-md border border-suspicious/20 bg-suspicious/[0.06] p-3 font-mono text-lg text-suspicious">{formatNumber(metrics.fp)}</div>
      <div className="flex items-center justify-end pr-1 text-[9px] uppercase tracking-wide text-slate-500">True malicious</div>
      <div className="rounded-md border border-threat/20 bg-threat/[0.06] p-3 font-mono text-lg text-threat">{formatNumber(metrics.fn)}</div>
      <div className="rounded-md border border-cyan/20 bg-cyan/[0.06] p-3 font-mono text-lg text-cyan">{formatNumber(metrics.tp)}</div>
    </div>
  );
}

export default function Models() {
  const [params] = useSearchParams();
  const models = useFetch("/api/models");
  const runs = useFetch("/api/preprocess/runs");
  const experiments = useFetch("/api/experiments");
  const [runId, setRunId] = useState(params.get("run") || "");
  const [modelKey, setModelKey] = useState("random_forest");
  const [hyper, setHyper] = useState({});
  const [name, setName] = useState("");
  const [jobId, setJobId] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [predicting, setPredicting] = useState(false);
  const [predictionError, setPredictionError] = useState(null);

  const job = useJob(jobId, async (finished) => {
    if (finished.status === "completed") {
      setMessage("Training finished. Metrics were computed on the untouched test split.");
      await experiments.refresh();
      setSelectedId(finished.result?.id || finished.meta?.experiment_id || null);
    }
  });

  useEffect(() => {
    if (!runId && runs.data?.length) setRunId(runs.data[0].id);
  }, [runs.data, runId]);

  useEffect(() => {
    if (!selectedId && experiments.data?.length) {
      const first = experiments.data.find((experiment) => experiment.status === "completed");
      if (first) setSelectedId(first.id);
    }
  }, [experiments.data, selectedId]);

  const run = runs.data?.find((item) => item.id === runId) || null;
  const selectedModel = models.data?.find((model) => model.key === modelKey) || null;
  const detail = useFetch(selectedId ? `/api/experiments/${selectedId}` : null);
  const experiment = detail.data;
  const completed = experiments.data?.filter((item) => item.status === "completed") || [];

  const fields = PARAM_FIELDS[modelKey] || [];
  const canTrain = Boolean(runId) && Boolean(selectedModel?.available) && models.data && !(job?.status === "running");

  const train = async () => {
    if (!runId) return;
    setError(null);
    setMessage(null);
    try {
      const cleanParams = Object.fromEntries(
        Object.entries(hyper).filter(([, value]) => value !== "" && value !== null && value !== undefined).map(([key, value]) => [key, Number(value)]),
      );
      const response = await api.train({
        preprocess_id: runId,
        dataset_id: run?.dataset_id,
        model_name: modelKey,
        params: cleanParams,
        name: name.trim() || undefined,
      });
      setJobId(response.job.id);
      setSelectedId(response.experiment.id);
    } catch (exc) {
      setError(exc);
    }
  };

  const runPrediction = async (file) => {
    if (!file || !selectedId) return;
    setPredictionError(null);
    setPredicting(true);
    try {
      setPrediction(await api.predict(selectedId, file));
    } catch (exc) {
      setPredictionError(exc);
    } finally {
      setPredicting(false);
    }
  };

  const metrics = experiment?.metrics || {};
  const curves = experiment?.curves || {};
  const rocSeries = curves.roc?.length ? [{ name: experiment.name, color: "#22d3ee", points: curves.roc }] : [];

  return (
    <div className="space-y-4">
      {error && <ErrorNotice error={error} onRetry={() => setError(null)} />}
      {message && <div className="rounded-lg border border-normal/20 bg-normal/[0.05] px-3.5 py-2.5 text-[11.5px] text-normal/90">{message}</div>}

      <div className="grid gap-4 xl:grid-cols-[0.92fr_1.4fr]">
        <Panel title="Experiment setup" subtitle="Training runs as a background job; progress is streamed over WebSocket.">
          {!runs.data ? <LoadingBlock rows={4} /> : (
            <div className="space-y-3">
              <Field label="Preprocessed dataset">
                <select className="select" value={runId} onChange={(event) => setRunId(event.target.value)}>
                  <option value="" disabled>Select a preprocessing run…</option>
                  {(runs.data || []).map((item) => <option key={item.id} value={item.id}>{item.name} · {formatNumber(item.train_rows)} train</option>)}
                </select>
              </Field>
              {!runs.data?.length && <p className="text-[10.5px] text-suspicious">No preprocessing runs yet. <Link to="/preprocessing" className="font-semibold text-cyan/80">Run preprocessing →</Link></p>}

              <div>
                <span className="label mb-1.5 block">Algorithm</span>
                <div className="grid gap-1.5 sm:grid-cols-2">
                  {(models.data || []).map((model) => (
                    <button
                      key={model.key}
                      disabled={!model.available}
                      onClick={() => { setModelKey(model.key); setHyper(defaultParams(model.key)); }}
                      className={`rounded-lg border px-2.5 py-2 text-left transition ${
                        modelKey === model.key ? "border-cyan/40 bg-cyan/[0.06]" : "border-line/60 hover:border-slate-500/50"
                      } ${!model.available ? "cursor-not-allowed opacity-40" : ""}`}
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[11px] font-semibold text-slate-200">{model.label}</span>
                        <span className={`badge ${model.family === "anomaly" ? "badge-blue" : "badge-neutral"} !px-1.5 !py-0`}>{model.family}</span>
                      </div>
                      <div className="mt-0.5 line-clamp-2 text-[9px] leading-snug text-slate-600">{model.description}</div>
                      {!model.available && <div className="mt-1 text-[9px] text-suspicious">not installed</div>}
                    </button>
                  ))}
                </div>
              </div>

              {selectedModel && (
                <div className="rounded-lg border border-line/60 bg-ink-950/40 p-3">
                  <div className="eyebrow mb-2">{selectedModel.family === "supervised" ? "Hyperparameters" : "Detector settings"}</div>
                  {fields.length === 0 ? <p className="text-[10.5px] text-slate-600">Default settings.</p> : (
                    <div className="grid grid-cols-2 gap-2">
                      {fields.map((field) => (
                        <Field key={field.key} label={field.label}>
                          <input
                            className="input !py-1.5"
                            type={field.type}
                            step={field.step}
                            min={field.min}
                            max={field.max}
                            placeholder={String(selectedModel.params?.[field.key] ?? "")}
                            value={hyper[field.key] ?? ""}
                            onChange={(event) => setHyper((current) => ({ ...current, [field.key]: event.target.value }))}
                          />
                        </Field>
                      ))}
                    </div>
                  )}
                  <p className="mt-2 text-[9.5px] leading-relaxed text-slate-600">
                    {selectedModel.family === "supervised"
                      ? "Trained on benign + attack rows. Test metrics use a 0.5 decision threshold."
                      : "Fitted on benign training rows only. The decision threshold is calibrated on benign validation scores."}
                  </p>
                </div>
              )}

              <Field label="Experiment name (optional)">
                <input className="input" placeholder={run ? `${selectedModel?.label || "Model"} · ${run.name}` : "Experiment name"} value={name} onChange={(event) => setName(event.target.value)} />
              </Field>

              {job && <Progress value={job.progress} message={job.message} tone={job.status === "failed" ? "red" : "cyan"} />}
              {job?.error && <p className="text-[10.5px] leading-relaxed text-threat">{job.error}</p>}
              <Button className="w-full" onClick={train} disabled={!canTrain} loading={job?.status === "running"}>
                <Play size={13} /> Train & evaluate
              </Button>
              <p className="text-[9.5px] leading-relaxed text-slate-600">
                Metrics are computed once on the held-out test split. No value is hardcoded or seeded for display.
              </p>
            </div>
          )}
        </Panel>

        <div className="space-y-4">
          <Panel
            title={experiment ? experiment.name : "Experiment results"}
            subtitle={experiment ? `${experiment.model_name} · ${titleCase(experiment.kind)} · ${formatDate(experiment.completed_at)}` : "Train a model or select a previous experiment."}
            action={experiment && <Badge tone={experiment.status === "completed" ? "green" : experiment.status === "failed" ? "red" : "amber"} dot>{titleCase(experiment.status)}</Badge>}
          >
            {detail.loading && !experiment ? <LoadingBlock rows={6} /> : !experiment ? (
              <EmptyState icon={FlaskConical} title="No experiment selected" description="Configure a model and start training." />
            ) : experiment.status !== "completed" ? (
              <div className="space-y-3">
                <Progress value={experiment.progress} message={experiment.message} tone={experiment.status === "failed" ? "red" : "cyan"} />
                {experiment.status === "failed" && <p className="text-[10.5px] text-threat">{experiment.message}</p>}
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <Stat label="Accuracy" value={formatMetric(metrics.accuracy)} tone="cyan" />
                  <Stat label="Precision" value={formatMetric(metrics.precision)} tone="blue" />
                  <Stat label="Recall" value={formatMetric(metrics.recall)} tone="green" />
                  <Stat label="F1-score" value={formatMetric(metrics.f1)} tone="amber" />
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="rounded-md border border-line/50 py-2"><div className="text-[9px] uppercase tracking-wide text-slate-600">False-positive rate</div><div className="font-mono text-sm text-suspicious">{formatMetric(metrics.false_positive_rate)}</div></div>
                  <div className="rounded-md border border-line/50 py-2"><div className="text-[9px] uppercase tracking-wide text-slate-600">ROC AUC</div><div className="font-mono text-sm text-cyan">{formatMetric(metrics.roc_auc)}</div></div>
                  <div className="rounded-md border border-line/50 py-2"><div className="text-[9px] uppercase tracking-wide text-slate-600">Latency (mean)</div><div className="font-mono text-sm text-slate-200">{formatMetric(metrics.inference_latency_ms_mean, 2)} ms</div></div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <div className="eyebrow mb-2">Confusion matrix · {formatNumber(metrics.n_test)} test rows</div>
                    <ConfusionMatrix metrics={metrics} />
                    <div className="mt-3 grid grid-cols-2 gap-2 text-[10px] text-slate-500">
                      <span>Threshold <span className="font-mono text-slate-300">{metrics.threshold}</span></span>
                      <span>Test rows <span className="font-mono text-slate-300">{formatNumber(metrics.n_test)}</span></span>
                      <span>Training rows <span className="font-mono text-slate-300">{formatNumber(metrics.n_train)}</span></span>
                      <span>Features <span className="font-mono text-slate-300">{formatNumber(metrics.n_features)}</span></span>
                    </div>
                  </div>
                  <div>
                    <div className="eyebrow mb-1">ROC curve</div>
                    <CurveChart series={rocSeries} height={210} />
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <div className="eyebrow mb-2">Per-family recall</div>
                    <DataTable
                      dense
                      columns={[
                        { key: "family", label: "Family", render: (row) => <span className="text-slate-300">{row.family}</span> },
                        { key: "support", label: "Support", align: "right" },
                        { key: "detected", label: "Detected", align: "right" },
                        { key: "recall", label: "Recall", align: "right", render: (row) => <span className="font-mono text-cyan/80">{formatMetric(row.recall)}</span> },
                      ]}
                      rows={experiment.per_family || []}
                      empty="No attack family labels in the test split."
                    />
                  </div>
                  <div>
                    <div className="eyebrow mb-1">Feature importance</div>
                    <FeatureImportance items={experiment.feature_importance} height={210} />
                  </div>
                </div>

                <div className="rounded-lg border border-line/50 bg-ink-950/30 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2 text-[10.5px] font-semibold text-slate-300"><Save size={12} className="text-cyan/70" /> Model artifact</div>
                    <Badge tone={experiment.artifact_saved ? "green" : "amber"}>{experiment.artifact_saved ? "saved to backend" : "not persisted"}</Badge>
                  </div>
                  <div className="mt-2 grid gap-2 text-[10px] text-slate-500 sm:grid-cols-3">
                    <span>Size <span className="font-mono text-slate-300">{formatMetric(metrics.model_size_mb, 3)} MB</span></span>
                    <span>Throughput <span className="font-mono text-slate-300">{formatMetric(metrics.throughput_records_per_sec, 0)}/s</span></span>
                    <span>Train time <span className="font-mono text-slate-300">{formatMetric(metrics.training_seconds, 1)} s</span></span>
                  </div>
                </div>

                <div className="rounded-lg border border-line/50 p-3">
                  <div className="eyebrow mb-1.5">Prediction using the saved model</div>
                  <p className="text-[10px] leading-relaxed text-slate-600">Upload a CSV/Parquet with the same raw feature columns to score it with this artifact.</p>
                  <label className="btn btn-ghost mt-2 cursor-pointer">
                    <Upload size={12} /> {predicting ? "Scoring…" : "Choose prediction file"}
                    <input type="file" className="hidden" accept=".csv,.parquet" onChange={(event) => runPrediction(event.target.files?.[0])} />
                  </label>
                  {predictionError && <p className="mt-2 text-[10px] text-threat">{predictionError.message}</p>}
                  {prediction && (
                    <div className="mt-2 rounded-md border border-line/50 bg-ink-950/40 p-2.5">
                      <div className="flex flex-wrap justify-between gap-2 text-[10px] text-slate-500">
                        <span>Scored <span className="font-mono text-slate-300">{formatNumber(prediction.scored_rows)}</span></span>
                        <span>Flagged <span className="font-mono text-threat">{formatNumber(prediction.flagged)}</span></span>
                        <span>Threshold <span className="font-mono text-slate-300">{prediction.threshold}</span></span>
                      </div>
                      <div className="mt-2 max-h-28 overflow-auto font-mono text-[9.5px] text-slate-500">
                        {prediction.predictions.slice(0, 8).map((row) => <div key={row.row} className="flex justify-between"><span>row {row.row}</span><span className={row.predicted ? "text-threat" : "text-normal"}>{row.label} · {row.score}</span></div>)}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </Panel>
        </div>
      </div>

      <Panel
        title="Experiment history"
        subtitle="All runs, including anomaly detectors and failed jobs, are kept for the audit trail."
        action={<Button variant="ghost" onClick={experiments.refresh}><RefreshCw size={12} /> Refresh</Button>}
        flush
      >
        <DataTable
          columns={[
            { key: "name", label: "Experiment", render: (row) => <button onClick={() => setSelectedId(row.id)} className={selectedId === row.id ? "text-cyan" : "text-slate-200"}>{row.name}</button> },
            { key: "kind", label: "Kind", render: (row) => <Badge tone={row.kind === "unknown" ? "blue" : row.kind === "anomaly" ? "amber" : "neutral"}>{row.kind}</Badge> },
            { key: "model", label: "Model", render: (row) => <span className="text-slate-400">{row.model_name}</span> },
            { key: "accuracy", label: "Accuracy", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.metrics?.accuracy)}</span> },
            { key: "f1", label: "F1", align: "right", render: (row) => <span className="font-mono text-cyan/80">{formatMetric(row.metrics?.f1)}</span> },
            { key: "recall", label: "Recall", align: "right", render: (row) => <span className="font-mono">{formatMetric(row.metrics?.recall)}</span> },
            { key: "status", label: "Status", render: (row) => <Badge tone={row.status === "completed" ? "green" : row.status === "failed" ? "red" : "amber"}>{row.status}</Badge> },
            { key: "created", label: "Created", render: (row) => <span className="whitespace-nowrap text-slate-500">{formatDate(row.created_at)}</span> },
          ]}
          rows={experiments.data || []}
          empty="No experiments yet."
        />
      </Panel>

      <ScopeNote>
        Reported metrics are computed from actual test predictions stored with the experiment. Anomaly detector thresholds are calibrated on benign validation rows only.
        The saved artifact and preprocessing pipeline are reused for prediction, containing no refit on test data.
      </ScopeNote>
    </div>
  );
}
