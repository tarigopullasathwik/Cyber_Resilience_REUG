import { useEffect, useMemo, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { ArrowRight, FlaskConical, Play, RefreshCw, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { api } from "../api";
import { useFetch, useJob } from "../hooks";
import { Badge, Button, DataTable, EmptyState, ErrorNotice, Field, KeyValue, LoadingBlock, Panel, Progress, ScopeNote, Stat } from "../components/ui";
import { formatMetric, formatNumber, formatPercent } from "../lib/format";

const DEFAULTS = {
  missing_strategy: "median",
  scaling: "standard",
  imbalance: "class_weight",
  max_missing_fraction: 0.6,
  max_onehot_categories: 24,
  top_k: 0,
  test_size: 0.2,
  val_size: 0.15,
  random_state: 42,
  max_rows: 250000,
  drop_identifiers: true,
  remove_duplicates: true,
  handle_infinite: true,
};

export default function Preprocessing() {
  const [params] = useSearchParams();
  const datasets = useFetch("/api/datasets");
  const runs = useFetch("/api/preprocess/runs");
  const [datasetId, setDatasetId] = useState(params.get("dataset") || "");
  const [config, setConfig] = useState(DEFAULTS);
  const [target, setTarget] = useState("");
  const [jobId, setJobId] = useState(null);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const job = useJob(jobId, async (finished) => {
    if (finished.status === "completed") {
      setMessage("Preprocessing completed. The fitted pipeline was applied to validation and test.");
      await runs.refresh();
      setSelectedRunId(finished.result?.id || null);
    }
  });

  const dataset = datasets.data?.find((item) => item.id === datasetId) || null;
  const runList = runs.data || [];
  const selectedRun = runList.find((item) => item.id === selectedRunId) || (runList.length ? runList[0] : null);

  useEffect(() => {
    if (!datasetId && datasets.data?.length) setDatasetId(datasets.data[0].id);
  }, [datasets.data, datasetId]);

  useEffect(() => {
    if (dataset) setTarget(dataset.target_column || "");
  }, [dataset]);

  useEffect(() => {
    if (!selectedRunId && runList.length) setSelectedRunId(runList[0].id);
  }, [runList, selectedRunId]);

  const update = (key, value) => setConfig((current) => ({ ...current, [key]: value }));

  const start = async () => {
    if (!datasetId) return;
    if (!target) {
      setError(new Error("Select a target/label column before preprocessing."));
      return;
    }
    setError(null);
    setMessage(null);
    try {
      const response = await api.startPreprocessing({
        dataset_id: datasetId,
        target_column: target,
        ...config,
        max_rows: Number(config.max_rows),
        top_k: Number(config.top_k),
        test_size: Number(config.test_size),
        val_size: Number(config.val_size),
        max_missing_fraction: Number(config.max_missing_fraction),
        max_onehot_categories: Number(config.max_onehot_categories),
      });
      setJobId(response.job.id);
    } catch (exc) {
      setError(exc);
    }
  };

  const stats = selectedRun?.stats;
  const splitTotal = useMemo(() => {
    const split = stats?.split;
    if (!split) return 0;
    return (split.train_rows || 0) + (split.val_rows || 0) + (split.test_rows || 0);
  }, [stats]);

  return (
    <div className="space-y-4">
      {error && <ErrorNotice error={error} onRetry={() => setError(null)} />}
      {message && <div className="rounded-lg border border-normal/20 bg-normal/[0.05] px-3.5 py-2.5 text-[11.5px] text-normal/90">{message}</div>}

      <div className="grid gap-4 xl:grid-cols-[0.95fr_1.35fr]">
        <Panel title="Configure preprocessing" subtitle="All transformations are fitted on the training split and then applied to validation and test.">
          {datasets.loading && !datasets.data ? <LoadingBlock rows={5} /> : (
            <div className="space-y-3">
              <Field label="Dataset">
                <select className="select" value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>
                  <option value="" disabled>Select a dataset…</option>
                  {(datasets.data || []).map((item) => <option key={item.id} value={item.id}>{item.name} · v{item.version} · {formatNumber(item.rows)} rows</option>)}
                </select>
              </Field>
              {dataset && (
                <Field label="Target / label column" hint="Benign labels are resolved from this column; all other labels become attack families.">
                  <select className="select" value={target} onChange={(event) => setTarget(event.target.value)}>
                    <option value="" disabled>Select a column…</option>
                    {dataset.columns.map((column) => <option key={column} value={column}>{column}</option>)}
                  </select>
                </Field>
              )}
              <div className="grid grid-cols-2 gap-3">
                <Field label="Missing values">
                  <select className="select" value={config.missing_strategy} onChange={(event) => update("missing_strategy", event.target.value)}>
                    <option value="median">Median imputation</option>
                    <option value="mean">Mean imputation</option>
                    <option value="drop_rows">Drop incomplete rows</option>
                  </select>
                </Field>
                <Field label="Scaling">
                  <select className="select" value={config.scaling} onChange={(event) => update("scaling", event.target.value)}>
                    <option value="standard">Standard</option>
                    <option value="minmax">Min-max</option>
                    <option value="robust">Robust</option>
                    <option value="none">None</option>
                  </select>
                </Field>
                <Field label="Class imbalance">
                  <select className="select" value={config.imbalance} onChange={(event) => update("imbalance", event.target.value)}>
                    <option value="class_weight">Class weights (train-only)</option>
                    <option value="oversample">Random oversample train</option>
                    <option value="none">No handling</option>
                  </select>
                </Field>
                <Field label="Feature selection (top-k)">
                  <input className="input" type="number" min="0" value={config.top_k} onChange={(event) => update("top_k", event.target.value)} />
                </Field>
                <Field label="Test fraction">
                  <input className="input" type="number" step="0.05" min="0.05" max="0.5" value={config.test_size} onChange={(event) => update("test_size", event.target.value)} />
                </Field>
                <Field label="Validation fraction">
                  <input className="input" type="number" step="0.05" min="0.05" max="0.4" value={config.val_size} onChange={(event) => update("val_size", event.target.value)} />
                </Field>
                <Field label="Max rows (stratified cap)">
                  <input className="input" type="number" min="200" value={config.max_rows} onChange={(event) => update("max_rows", event.target.value)} />
                </Field>
                <Field label="Random seed">
                  <input className="input" type="number" value={config.random_state} onChange={(event) => update("random_state", Number(event.target.value))} />
                </Field>
              </div>
              <div className="space-y-2 rounded-lg border border-line/60 bg-ink-950/40 p-3">
                {[
                  ["remove_duplicates", "Remove duplicate rows before splitting"],
                  ["handle_infinite", "Replace infinite numeric values"],
                  ["drop_identifiers", "Exclude identifier / IP / timestamp columns"],
                ].map(([key, label]) => (
                  <label key={key} className="flex cursor-pointer items-center justify-between gap-3 text-[11px] text-slate-400">
                    <span>{label}</span>
                    <input type="checkbox" checked={config[key]} onChange={(event) => update(key, event.target.checked)} className="h-3.5 w-3.5 accent-cyan" />
                  </label>
                ))}
              </div>
              {job && <Progress value={job.progress} message={job.message} tone={job.status === "failed" ? "red" : "cyan"} />}
              {job?.error && <p className="text-[10.5px] text-threat">{job.error}</p>}
              <Button className="w-full" onClick={start} loading={job?.status === "running" || job?.status === "queued"} disabled={!datasetId || !target}>
                <Play size={13} /> Run preprocessing
              </Button>
              {dataset && !target && <p className="text-[10.5px] text-suspicious">This dataset has no target column. Set one in Dataset Management first.</p>}
              {!datasetId && <Link to="/datasets" className="text-[10.5px] font-semibold text-cyan/80">Upload a dataset first →</Link>}
            </div>
          )}
        </Panel>

        <Panel
          title="Before → after"
          subtitle={selectedRun ? `${selectedRun.name} · ${selectedRun.target_column}` : "Run preprocessing to generate a leakage-safe split."}
          action={selectedRun && <Badge tone="green" dot>pipeline persisted</Badge>}
        >
          {!selectedRun ? (
            <EmptyState icon={SlidersHorizontal} title="No preprocessing run" description="Choose a dataset and configuration, then run preprocessing." />
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Stat label="Rows in" value={formatNumber(stats?.before?.rows)} tone="neutral" />
                <Stat label="Rows kept" value={formatNumber(stats?.after?.rows)} tone="cyan" />
                <Stat label="Features" value={formatNumber(stats?.after?.features)} tone="green" />
                <Stat label="Missing after" value={formatNumber(stats?.after?.missing_cells)} tone="blue" />
              </div>

              <div>
                <div className="eyebrow mb-2">Split sizes (stratified)</div>
                <div className="flex h-3 overflow-hidden rounded-full bg-ink-700">
                  {[["Train", stats?.split?.train_rows, "bg-cyan"], ["Validation", stats?.split?.val_rows, "bg-electric"], ["Test", stats?.split?.test_rows, "bg-normal"]].map(([label, value, color]) => (
                    <div key={label} className={`${color}`} style={{ width: `${splitTotal ? (value / splitTotal) * 100 : 0}%` }} title={`${label}: ${value}`} />
                  ))}
                </div>
                <div className="mt-1.5 flex flex-wrap gap-3 text-[10px] text-slate-500">
                  <span><span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-cyan" />Train {formatNumber(stats?.split?.train_rows)}</span>
                  <span><span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-electric" />Validation {formatNumber(stats?.split?.val_rows)}</span>
                  <span><span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-normal" />Test {formatNumber(stats?.split?.test_rows)}</span>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-line/50 p-3">
                  <div className="eyebrow mb-2">Benign labels</div>
                  <div className="flex flex-wrap gap-1">
                    {(stats?.benign_labels || []).map((label) => <Badge key={label} tone="green">{label}</Badge>)}
                  </div>
                  <div className="eyebrow mb-2 mt-3">Attack families</div>
                  <div className="flex flex-wrap gap-1">
                    {(stats?.attack_families || []).slice(0, 10).map((label) => <Badge key={label} tone="red">{label}</Badge>)}
                    {!stats?.attack_families?.length && <span className="text-[10px] text-slate-600">No attack family found in test.</span>}
                  </div>
                </div>
                <div className="rounded-lg border border-line/50 p-3">
                  <div className="eyebrow mb-2">Handling summary</div>
                  <KeyValue
                    items={[
                      { label: "Duplicates removed", value: formatNumber(stats?.removed?.duplicates) },
                      { label: "Dropped columns", value: formatNumber(stats?.removed?.dropped_columns?.length) },
                      { label: "Oversampling", value: stats?.config?.oversampled_train_only ? "train only" : "not used" },
                      { label: "Rows sampled", value: stats?.sampled ? `capped at ${formatNumber(stats?.row_cap_applied)}` : "no" },
                    ]}
                  />
                </div>
              </div>

              <div className="rounded-lg border border-normal/15 bg-normal/[0.03] p-3">
                <div className="flex items-center gap-2 text-[10.5px] font-semibold text-normal"><ShieldCheck size={13} /> Leakage controls</div>
                <ul className="mt-2 space-y-1">
                  {(stats?.leakage_controls || []).map((item) => <li key={item} className="flex gap-2 text-[10.5px] leading-relaxed text-slate-500"><span className="text-normal/70">✓</span>{item}</li>)}
                </ul>
              </div>

              {stats?.removed?.identifier_columns?.length > 0 && (
                <div>
                  <div className="eyebrow mb-1.5">Excluded identifier columns</div>
                  <div className="flex flex-wrap gap-1">{stats.removed.identifier_columns.slice(0, 14).map((column) => <code key={column} className="rounded bg-ink-950 px-1.5 py-0.5 font-mono text-[9.5px] text-slate-500">{column}</code>)}</div>
                </div>
              )}
            </div>
          )}
        </Panel>
      </div>

      <Panel
        title="Preprocessing runs"
        subtitle="Fitted pipelines and split files are persisted so training, prediction and verification reuse exactly the same transformation."
        action={<Button variant="ghost" onClick={runs.refresh}><RefreshCw size={12} /> Refresh</Button>}
        flush
      >
        <DataTable
          columns={[
            { key: "name", label: "Run", render: (row) => <button onClick={() => setSelectedRunId(row.id)} className={selectedRun?.id === row.id ? "text-cyan" : "text-slate-200"}>{row.name}</button> },
            { key: "target", label: "Target", render: (row) => <code className="font-mono text-[10px] text-slate-400">{row.target_column}</code> },
            { key: "train", label: "Train", align: "right", render: (row) => <span className="font-mono">{formatNumber(row.train_rows)}</span> },
            { key: "val", label: "Val", align: "right", render: (row) => <span className="font-mono">{formatNumber(row.val_rows)}</span> },
            { key: "test", label: "Test", align: "right", render: (row) => <span className="font-mono">{formatNumber(row.test_rows)}</span> },
            { key: "features", label: "Features", align: "right", render: (row) => <span className="font-mono">{formatNumber(row.feature_names?.length)}</span> },
            { key: "families", label: "Families", render: (row) => <span className="text-slate-400">{row.families?.length || 0}</span> },
            { key: "actions", label: "", align: "right", render: (row) => <Link to={`/models?run=${row.id}`} className="inline-flex items-center gap-1 text-[10px] font-semibold text-cyan/80 hover:text-cyan">Train <ArrowRight size={10} /></Link> },
          ]}
          rows={runList}
          empty="No preprocessing runs yet."
        />
      </Panel>

      <ScopeNote>
        Preprocessing statistics are computed from the actual file. Oversampling, when enabled, is applied only to the training split after splitting.
        Identifier-like columns are excluded by name and can be removed manually by choosing a different dataset export.
      </ScopeNote>
    </div>
  );
}
