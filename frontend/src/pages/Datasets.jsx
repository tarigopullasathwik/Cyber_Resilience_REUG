import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Database, DownloadCloud, FileUp, Layers, RefreshCw, Trash2, UploadCloud } from "lucide-react";
import { api } from "../api";
import { useFetch, useJob } from "../hooks";
import { Badge, Button, DataTable, EmptyState, ErrorNotice, Field, KeyValue, LoadingBlock, Panel, Progress, ScopeNote } from "../components/ui";
import { formatBytes, formatDate, formatNumber } from "../lib/format";

export default function Datasets() {
  const datasets = useFetch("/api/datasets");
  const kaggle = useFetch("/api/kaggle/status");
  const [selectedId, setSelectedId] = useState(null);
  const preview = useFetch(selectedId ? `/api/datasets/${selectedId}/preview?limit=12` : null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [slug, setSlug] = useState("");
  const fileRef = useRef(null);
  const selected = datasets.data?.find((dataset) => dataset.id === selectedId) || null;
  const job = useJob(jobId, () => {
    datasets.refresh();
    setMessage("Kaggle import finished. New datasets are ready to inspect.");
  });

  useEffect(() => {
    if (!selectedId && datasets.data?.length) setSelectedId(datasets.data[0].id);
  }, [datasets.data, selectedId]);

  const handleFiles = async (files) => {
    const file = files?.[0];
    if (!file) return;
    if (!/\.(csv|parquet)$/i.test(file.name)) {
      setError(new Error("Only .csv and .parquet files are supported."));
      return;
    }
    setError(null);
    setMessage(null);
    setUploading(true);
    setUploadProgress(0);
    try {
      const dataset = await api.uploadDataset(file, setUploadProgress);
      setMessage(`${dataset.name} v${dataset.version} uploaded and profiled.`);
      await datasets.refresh();
      setSelectedId(dataset.id);
    } catch (exc) {
      setError(exc);
    } finally {
      setUploading(false);
    }
  };

  const updateTarget = async (value) => {
    if (!selected) return;
    setError(null);
    try {
      const updated = await api.setTarget(selected.id, value);
      await datasets.refresh();
      setSelectedId(updated.id);
      preview.refresh();
      setMessage(`Target column set to “${value}”.`);
    } catch (exc) {
      setError(exc);
    }
  };

  const remove = async (dataset) => {
    if (!window.confirm(`Delete ${dataset.name} v${dataset.version} and its preprocessing runs? This cannot be undone.`)) return;
    setError(null);
    try {
      await api.deleteDataset(dataset.id);
      setSelectedId(null);
      await datasets.refresh();
      setMessage(`${dataset.name} deleted.`);
    } catch (exc) {
      setError(exc);
    }
  };

  const startKaggle = async (reference) => {
    if (!reference) return;
    setError(null);
    setMessage(null);
    try {
      const response = await api.importKaggle(reference);
      setJobId(response.job.id);
    } catch (exc) {
      setError(exc);
    }
  };

  return (
    <div className="space-y-4">
      {error && <ErrorNotice error={error} onRetry={() => setError(null)} />}
      {message && <div className="rounded-lg border border-normal/20 bg-normal/[0.05] px-3.5 py-2.5 text-[11.5px] text-normal/90">{message}</div>}

      <div className="grid gap-4 xl:grid-cols-[1.05fr_1fr]">
        <Panel
          title="Upload a dataset"
          subtitle="CSV or Parquet. Files are streamed to disk, profiled and assigned a version automatically."
          action={<Badge tone="cyan">{formatBytes(512 * 1024 * 1024)} limit</Badge>}
        >
          <div
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => { event.preventDefault(); setDragging(false); handleFiles(event.dataTransfer.files); }}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed px-4 py-8 text-center transition ${
              dragging ? "border-cyan/60 bg-cyan/[0.05]" : "border-line hover:border-cyan/30 hover:bg-ink-800/30"
            }`}
            onClick={() => fileRef.current?.click()}
          >
            <UploadCloud size={24} className="text-cyan/70" />
            <p className="mt-2 text-[12px] font-semibold text-slate-200">Drop a dataset here, or browse</p>
            <p className="mt-1 text-[10.5px] text-slate-500">Kaggle exports, Edge-IIoTset CSVs, CICIoT2023, ToN-IoT</p>
            <p className="mt-2 text-[9.5px] uppercase tracking-[0.12em] text-slate-600">Streamed upload · automatic profiling</p>
            <input ref={fileRef} type="file" accept=".csv,.parquet" className="hidden" onChange={(event) => handleFiles(event.target.files)} />
          </div>
          {uploading && <div className="mt-3"><Progress value={uploadProgress / 100} message={`Uploading… ${uploadProgress}%`} /></div>}
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <div className="rounded-md border border-line/50 px-2.5 py-2"><div className="text-[9px] uppercase tracking-wide text-slate-600">Versioning</div><div className="mt-0.5 text-[10.5px] text-slate-400">Same name → next version</div></div>
            <div className="rounded-md border border-line/50 px-2.5 py-2"><div className="text-[9px] uppercase tracking-wide text-slate-600">Profiling</div><div className="mt-0.5 text-[10.5px] text-slate-400">Missing, dtypes, duplicates</div></div>
            <div className="rounded-md border border-line/50 px-2.5 py-2"><div className="text-[9px] uppercase tracking-wide text-slate-600">Target</div><div className="mt-0.5 text-[10.5px] text-slate-400">Explicit label selection</div></div>
          </div>
        </Panel>

        <Panel
          title="Kaggle import"
          subtitle="Credentials stay in backend environment variables and are never exposed to this page."
          action={
            <Badge tone={kaggle.data?.status?.configured ? "green" : "amber"} dot>
              {kaggle.data?.status?.configured ? "credentials configured" : "not configured"}
            </Badge>
          }
        >
          <div className="grid gap-2 sm:grid-cols-3">
            {(kaggle.data?.presets || []).map((preset) => (
              <div key={preset.key} className="flex flex-col rounded-lg border border-line/60 bg-ink-900/40 p-2.5">
                <div className="text-[11px] font-semibold text-slate-200">{preset.label}</div>
                <p className="mt-1 flex-1 text-[9.5px] leading-relaxed text-slate-500">{preset.description}</p>
                <Button
                  variant="ghost"
                  className="mt-2 w-full !px-2 !py-1.5 !text-[10px]"
                  disabled={!kaggle.data?.status?.configured}
                  onClick={() => startKaggle(preset.slug)}
                >
                  <DownloadCloud size={11} /> Import
                </Button>
              </div>
            ))}
          </div>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <input
              className="input flex-1"
              placeholder="owner/dataset-slug"
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
            />
            <Button onClick={() => startKaggle(slug.trim())} disabled={!slug.trim() || !kaggle.data?.status?.configured}>
              <DownloadCloud size={13} /> Import slug
            </Button>
          </div>
          {!kaggle.data?.status?.configured && (
            <p className="mt-2 text-[10px] leading-relaxed text-suspicious/80">{kaggle.data?.status?.hint || "Set KAGGLE_USERNAME and KAGGLE_KEY on the backend."}</p>
          )}
          {job && (
            <div className="mt-3">
              <Progress value={job.progress} message={job.message} tone={job.status === "failed" ? "red" : "cyan"} />
              {job.error && <p className="mt-1 text-[10px] text-threat">{job.error}</p>}
            </div>
          )}
        </Panel>
      </div>

      <Panel
        title="Dataset registry"
        subtitle="Every dataset is versioned and keeps its column profile, class distribution and selected target."
        action={
          <div className="flex gap-2">
            <Button variant="ghost" onClick={datasets.refresh}><RefreshCw size={12} /> Refresh</Button>
            {selectedId && <Link to={`/preprocessing?dataset=${selectedId}`} className="btn btn-primary">Use in preprocessing <ArrowUpRight size={12} /></Link>}
          </div>
        }
        flush
      >
        {datasets.loading && !datasets.data ? (
          <div className="p-4"><LoadingBlock rows={4} /></div>
        ) : (
          <DataTable
            columns={[
              {
                key: "name",
                label: "Dataset",
                render: (row) => (
                  <button className="text-left" onClick={() => setSelectedId(row.id)}>
                    <div className="flex items-center gap-2">
                      <Database size={13} className={selectedId === row.id ? "text-cyan" : "text-slate-600"} />
                      <span className={`font-medium ${selectedId === row.id ? "text-cyan" : "text-slate-200"}`}>{row.name}</span>
                      <span className="font-mono text-[9px] text-slate-600">v{row.version}</span>
                    </div>
                    <div className="mt-0.5 truncate text-[9.5px] text-slate-600">{row.filename}</div>
                  </button>
                ),
              },
              { key: "origin", label: "Source", render: (row) => <Badge tone={row.origin === "kaggle" ? "blue" : "neutral"}>{row.origin}</Badge> },
              { key: "rows", label: "Rows", align: "right", render: (row) => <span className="font-mono">{formatNumber(row.rows)}</span> },
              { key: "cols", label: "Cols", align: "right", render: (row) => <span className="font-mono">{formatNumber(row.cols)}</span> },
              { key: "target", label: "Target", render: (row) => row.target_column ? <code className="rounded bg-ink-950 px-1 py-0.5 font-mono text-[10px] text-cyan/80">{row.target_column}</code> : <Badge tone="amber">not set</Badge> },
              { key: "size", label: "Size", align: "right", render: (row) => <span className="font-mono text-slate-400">{formatBytes(row.size_bytes)}</span> },
              { key: "duplicates", label: "Duplicates", align: "right", render: (row) => <span className="font-mono text-slate-400">{formatNumber(row.duplicates)}</span> },
              { key: "created", label: "Added", render: (row) => <span className="whitespace-nowrap text-slate-500">{formatDate(row.created_at)}</span> },
              {
                key: "actions",
                label: "",
                align: "right",
                render: (row) => (
                  <button onClick={() => remove(row)} className="rounded p-1.5 text-slate-600 transition hover:bg-threat/10 hover:text-threat" title="Delete dataset">
                    <Trash2 size={13} />
                  </button>
                ),
              },
            ]}
            rows={datasets.data || []}
            empty="No datasets yet. Upload a CSV or import one from Kaggle."
          />
        )}
      </Panel>

      {selected ? (
        <div className="grid gap-4 xl:grid-cols-[1fr_1.5fr]">
          <Panel
            title={selected.name}
            subtitle={`Version ${selected.version} · ${selected.origin} · ${selected.format.toUpperCase()}`}
            action={<Button variant="ghost" onClick={() => preview.refresh()}><RefreshCw size={12} /> Reload</Button>}
          >
            <KeyValue
              items={[
                { label: "Rows", value: formatNumber(selected.rows) },
                { label: "Columns", value: formatNumber(selected.cols) },
                { label: "File size", value: formatBytes(selected.size_bytes) },
                { label: "Duplicate records", value: formatNumber(selected.duplicates) },
                { label: "Target column", value: selected.target_column || "not selected" },
                { label: "Added", value: formatDate(selected.created_at) },
              ]}
            />
            <div className="mt-4">
              <Field label="Target / label column" hint="Only the selected column is used for benign/malicious mapping and attack families. No column name is assumed.">
                <select className="select" value={selected.target_column || ""} onChange={(event) => updateTarget(event.target.value)}>
                  <option value="" disabled>Select a column…</option>
                  {selected.columns.map((column) => <option key={column} value={column}>{column}</option>)}
                </select>
              </Field>
            </div>
            <div className="mt-4">
              <div className="eyebrow mb-2">Detected target candidates</div>
              <div className="flex flex-wrap gap-1.5">
                {(selected.target_candidates || []).slice(0, 8).map((candidate) => (
                  <button
                    key={candidate.column}
                    onClick={() => updateTarget(candidate.column)}
                    className={`badge ${candidate.column === selected.target_column ? "badge-cyan" : candidate.hinted ? "badge-blue" : "badge-neutral"} normal-case tracking-normal`}
                  >
                    {candidate.column} <span className="opacity-60">({candidate.unique})</span>
                  </button>
                ))}
                {!selected.target_candidates?.length && <span className="text-[10.5px] text-slate-600">No low-cardinality candidates detected.</span>}
              </div>
            </div>
            <div className="mt-4">
              <div className="eyebrow mb-2">Class distribution</div>
              {Object.keys(selected.class_distribution || {}).length ? (
                <div className="space-y-1.5">
                  {Object.entries(selected.class_distribution).slice(0, 6).map(([label, count]) => {
                    const total = Object.values(selected.class_distribution).reduce((sum, value) => sum + value, 0) || 1;
                    return (
                      <div key={label}>
                        <div className="mb-0.5 flex justify-between text-[10px]"><span className="truncate text-slate-400">{label}</span><span className="font-mono text-slate-500">{formatNumber(count)}</span></div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-ink-700"><div className="h-full rounded-full bg-cyan/70" style={{ width: `${Math.max(2, (count / total) * 100)}%` }} /></div>
                      </div>
                    );
                  })}
                </div>
              ) : <p className="text-[10.5px] text-slate-600">Select a target column to compute class distribution.</p>}
            </div>
          </Panel>

          <Panel title="Data preview" subtitle="First 12 rows after upload. Column profile is computed from the stored file." flush>
            {preview.loading && !preview.data ? (
              <div className="p-4"><LoadingBlock rows={5} /></div>
            ) : preview.data ? (
              <>
                <div className="max-h-[330px] overflow-auto">
                  <table className="table min-w-[760px]">
                    <thead><tr>{preview.data.columns.slice(0, 10).map((column) => <th key={column}>{column}</th>)}</tr></thead>
                    <tbody>
                      {preview.data.records.map((record, index) => (
                        <tr key={index}>
                          {preview.data.columns.slice(0, 10).map((column) => (
                            <td key={column} className="max-w-[180px] truncate font-mono text-[10px] text-slate-400">{String(record[column] ?? "—")}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="border-t border-line/50 p-4">
                  <div className="eyebrow mb-2">Column profile</div>
                  <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                    {preview.data.profile.slice(0, 12).map((column) => (
                      <div key={column.column} className="rounded-md border border-line/40 px-2 py-1.5">
                        <div className="truncate text-[10.5px] text-slate-300">{column.column}</div>
                        <div className="mt-0.5 flex justify-between text-[9px] text-slate-600"><span>{column.dtype}</span><span>{column.unique} unique · {column.missing} null</span></div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <EmptyState icon={Layers} title="No preview" description="Select a dataset to inspect its first rows." />
            )}
          </Panel>
        </div>
      ) : (
        <Panel><EmptyState icon={FileUp} title="Select a dataset" description="Choose a dataset above to inspect columns, class distribution and preview rows." /></Panel>
      )}

      <ScopeNote>
        Profiling is computed from the uploaded file. CSV duplicate counting is exact up to 1,000,000 rows and explicitly marked as sampled above that.
        The Kaggle importer uses backend credentials only; the browser never receives tokens.
      </ScopeNote>
    </div>
  );
}
