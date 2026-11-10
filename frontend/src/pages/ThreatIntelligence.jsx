import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Play, Radar, ShieldAlert } from "lucide-react";
import { api } from "../api";
import { useDebouncedValue, useFetch, useJob } from "../hooks";
import { Badge, Button, DataTable, EmptyState, ErrorNotice, LoadingBlock, Panel, Progress, ScopeNote, Stat } from "../components/ui";
import { CompositionChart, ScoreHistogram } from "../components/charts";
import { formatMetric, formatNumber } from "../lib/format";

export default function ThreatIntelligence() {
  const experiments = useFetch("/api/experiments");
  const [experimentId, setExperimentId] = useState("");
  const [threshold, setThreshold] = useState(0.5);
  const debouncedThreshold = useDebouncedValue(threshold, 250);
  const [jobId, setJobId] = useState(null);
  const [actionError, setActionError] = useState(null);

  const completed = (experiments.data || []).filter((item) => item.status === "completed");
  const threats = useFetch(
    completed.length ? `/api/threats?experiment_id=${experimentId || completed[0]?.id}&threshold=${debouncedThreshold}` : null,
  );
  const job = useJob(jobId);

  useEffect(() => {
    if (!experimentId && completed.length) setExperimentId(completed[0].id);
  }, [completed, experimentId]);

  const data = threats.data;
  const composition = data?.composition || {};
  const flagged = (composition.known_detected || 0) + (composition.unknown_suspected || 0);
  const compositionData = [
    { name: "Benign correct", value: composition.benign_records || 0, color: "#34d399" },
    { name: "Benign flagged", value: composition.benign_flagged || 0, color: "#fbbf24" },
    { name: "Known detected", value: composition.known_detected || 0, color: "#f87171" },
    { name: "Suspected unknown", value: composition.unknown_suspected || 0, color: "#a78bfa" },
    { name: "Missed attacks", value: (composition.known_missed || 0) + (composition.unknown_missed || 0), color: "#475569" },
  ];

  const startContainment = async () => {
    if (!experimentId) return;
    setActionError(null);
    try {
      const response = await api.simulateContainment({ experiment_id: experimentId, max_events: 8 });
      setJobId(response.job.id);
    } catch (exc) {
      setActionError(exc);
    }
  };

  return (
    <div className="space-y-4">
      {actionError && <ErrorNotice error={actionError} onRetry={() => setActionError(null)} />}
      <Panel
        title="Threat composition"
        subtitle="Computed from stored test predictions; threshold changes are applied without retraining."
        action={
          <div className="flex flex-wrap items-center gap-2">
            <select className="select !w-auto !py-1.5 !text-[11px]" value={experimentId} onChange={(event) => setExperimentId(event.target.value)}>
              {completed.map((experiment) => <option key={experiment.id} value={experiment.id}>{experiment.name}</option>)}
            </select>
            <Button variant="ghost" onClick={startContainment} disabled={!experimentId || job?.status === "running"}>
              <Play size={12} /> Contain flagged
            </Button>
          </div>
        }
      >
        {!completed.length ? (
          <EmptyState icon={Radar} title="No experiment available" description="Train a model first; threat intelligence is derived from its saved test predictions." action={<Link to="/models" className="btn btn-primary">Open ML Laboratory</Link>} />
        ) : threats.loading && !data ? <LoadingBlock rows={4} /> : threats.error ? (
          <ErrorNotice error={threats.error} onRetry={threats.refresh} />
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
              <Stat label="Records" value={formatNumber(composition.total_records)} tone="neutral" />
              <Stat label="Benign" value={formatNumber(composition.benign_records)} tone="green" hint={`${formatNumber(composition.benign_flagged)} false positives`} />
              <Stat label="Known detected" value={formatNumber(composition.known_detected)} tone="red" hint={`${formatNumber(composition.known_missed)} missed`} />
              <Stat label="Suspected unknown" value={formatNumber(composition.unknown_suspected)} tone="blue" hint="Withheld families only" />
              <Stat label="Flagged at threshold" value={formatNumber(flagged)} tone="amber" hint={`threshold ${threshold.toFixed(2)}`} />
            </div>

            <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
              <div>
                <div className="eyebrow mb-1">Score distribution (benign vs malicious)</div>
                <ScoreHistogram
                  data={data?.score_histogram || []}
                  series={[
                    { key: "benign", name: "Benign", color: "#34d399" },
                    { key: "malicious", name: "Malicious", color: "#f87171" },
                  ]}
                  height={220}
                />
              </div>
              <div>
                <div className="eyebrow mb-1">Prediction composition</div>
                <CompositionChart data={compositionData} height={200} />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-line/60 bg-ink-950/40 px-3 py-2.5">
              <span className="label !mb-0">Decision threshold</span>
              <input type="range" min="0.05" max="0.95" step="0.01" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} className="h-1 flex-1 accent-cyan" />
              <span className="w-10 font-mono text-[11px] text-cyan">{threshold.toFixed(2)}</span>
            </div>
            {job && <Progress value={job.progress} message={job.message} tone={job.status === "failed" ? "red" : "cyan"} />}
            {job?.status === "completed" && <Link to="/containment" className="text-[10.5px] font-semibold text-cyan/80">Containment replay created → review events</Link>}
          </div>
        )}
      </Panel>

      {data && (
        <div className="grid gap-4 xl:grid-cols-[1.15fr_1fr]">
          <Panel title="Highest-risk records" subtitle="Actual held-out rows sorted by model score; classification uses the selected threshold." flush>
            <DataTable
              dense
              columns={[
                { key: "row", label: "Row", render: (row) => <span className="font-mono text-slate-500">#{row.row_index}</span> },
                { key: "classification", label: "Classification", render: (row) => <Badge tone={row.classification === "suspected unknown" ? "blue" : row.classification === "known malicious" ? "red" : "green"}>{row.classification}</Badge> },
                { key: "family", label: "Family", render: (row) => <span className="text-slate-300">{row.family}</span> },
                { key: "score", label: "Score", align: "right", render: (row) => <span className="font-mono text-slate-200">{formatMetric(row.score, 4)}</span> },
                { key: "ground", label: "Ground truth", render: (row) => <span className={row.ground_truth === "malicious" ? "text-threat/80" : "text-normal/80"}>{row.ground_truth}</span> },
              ]}
              rows={data.top_records}
              empty="No records."
            />
          </Panel>
          <Panel title="Attack families" subtitle="Detection rate per dataset-provided family." flush>
            <DataTable
              dense
              columns={[
                { key: "family", label: "Family", render: (row) => <span className="text-slate-300">{row.family}</span> },
                { key: "records", label: "Records", align: "right" },
                { key: "flagged", label: "Flagged", align: "right" },
                { key: "rate", label: "Detection", align: "right", render: (row) => <span className="font-mono text-cyan/80">{formatMetric(row.detection_rate)}</span> },
                { key: "withheld", label: "Withheld", render: (row) => <Badge tone={row.withheld ? "blue" : "neutral"}>{row.withheld ? "yes" : "no"}</Badge> },
              ]}
              rows={data.families}
              empty="No labelled attack rows."
            />
          </Panel>
        </div>
      )}

      <ScopeNote>
        <ShieldAlert size={11} className="mt-0.5 inline" /> “Suspected unknown” requires a withheld-family experiment; ordinary supervised experiments have no unknown-labelled records.
        Counts include dataset ground truth for evaluation only. {data?.scope_note}
      </ScopeNote>
    </div>
  );
}
