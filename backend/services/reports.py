"""Experimental report generation (PDF, CSV, JSON)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .. import db, settings
from . import containment, datasets, modeling, preprocessing, resources


class ReportError(ValueError):
    pass


def _styles() -> dict[str, Any]:
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="EdgeTitle", parent=styles["Title"], fontSize=19, leading=23,
            textColor=colors.HexColor("#0b2545"), spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="EdgeH2", parent=styles["Heading2"], fontSize=12.5, leading=15,
            textColor=colors.HexColor("#134074"), spaceBefore=12, spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="EdgeBody", parent=styles["BodyText"], fontSize=9, leading=13,
            textColor=colors.HexColor("#1f2933"), spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="EdgeSmall", parent=styles["BodyText"], fontSize=7.5, leading=10,
            textColor=colors.HexColor("#52606d"),
        )
    )
    return styles


def _metric_table(metrics: dict[str, Any], keys: list[tuple[str, str]]) -> Table:
    rows = [["Metric", "Value"]]
    for key, label in keys:
        value = metrics.get(key)
        rows.append([label, "n/a" if value is None else f"{value:.4g}" if isinstance(value, float) else str(value)])
    table = Table(rows, colWidths=[95 * mm, 55 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbe7f3")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0b2545")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#a8b8c8")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8fb")]),
            ]
        )
    )
    return table


def _simple_table(header: list[str], rows: list[list[str]], widths: list[float] | None = None) -> Table:
    table = Table([header] + rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#134074")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#b8c7d8")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f7fa")]),
            ]
        )
    )
    return table


def generate_pdf(experiment_id: str) -> dict[str, Any]:
    row = modeling.get_experiment_row(experiment_id)
    if row["status"] != "completed":
        raise ReportError("Only completed experiments can be reported.")
    experiment = modeling.experiment_record(row)
    dataset = datasets.get_dataset(row["dataset_id"]) if row["dataset_id"] else None
    run = preprocessing.get_run(row["preprocess_id"]) if row["preprocess_id"] else None
    metrics = experiment["metrics"]
    report_id = db.new_id("rp_")
    path = settings.REPORT_DIR / f"{report_id}.pdf"
    styles = _styles()
    document = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"EDGEGUARD AI report · {experiment['name']}",
    )
    story: list[Any] = []
    story.append(Paragraph("EDGEGUARD AI — Experimental Report", styles["EdgeTitle"]))
    story.append(Paragraph(settings.RESEARCH_TITLE, styles["EdgeH2"]))
    story.append(
        Paragraph(
            f"Generated {db.utc_now()} · Experiment <b>{experiment['name']}</b> "
            f"(<font face='Courier'>{experiment['id']}</font>)",
            styles["EdgeBody"],
        )
    )
    story.append(
        Paragraph(
            "Scope: this report describes a research prototype. Containment and edge resource "
            "budgets are simulated. Metrics are computed from the held-out test split recorded "
            "for this experiment; they are not production measurements.",
            styles["EdgeBody"],
        )
    )

    story.append(Paragraph("1. Dataset and preprocessing", styles["EdgeH2"]))
    if dataset:
        story.append(
            Paragraph(
                f"Dataset: <b>{dataset['name']}</b> v{dataset['version']} "
                f"({dataset['origin']}) · {dataset['rows']:,} rows × {dataset['cols']} columns · "
                f"target column <font face='Courier'>{dataset.get('target_column') or 'n/a'}</font>.",
                styles["EdgeBody"],
            )
        )
    if run:
        stats = run["stats"]
        story.append(
            Paragraph(
                f"Preprocessing run <font face='Courier'>{run['id']}</font>: "
                f"{stats.get('split', {}).get('train_rows', 0):,} train / "
                f"{stats.get('split', {}).get('val_rows', 0):,} validation / "
                f"{stats.get('split', {}).get('test_rows', 0):,} test rows; "
                f"{stats.get('after', {}).get('features', 0)} features after encoding; "
                f"benign labels: {', '.join(stats.get('benign_labels', [])[:4])}.",
                styles["EdgeBody"],
            )
        )
        story.append(
            Paragraph(
                "Leakage control: transformations were fitted on the training split only; "
                "validation and test rows were transformed with that fitted pipeline. "
                "Duplicate removal happened before splitting.",
                styles["EdgeSmall"],
            )
        )

    story.append(Paragraph("2. Model configuration", styles["EdgeH2"]))
    story.append(
        Paragraph(
            f"Model: <b>{metrics.get('model_label') or experiment['model_name']}</b> · "
            f"family: {metrics.get('model_family', 'n/a')} · threshold: {metrics.get('threshold')} · "
            f"features: {metrics.get('n_features')} · training rows: {metrics.get('n_train')}.",
            styles["EdgeBody"],
        )
    )
    params = experiment.get("params") or {}
    if params:
        story.append(
            Paragraph(
                "Hyperparameters: " + ", ".join(f"{key}={value}" for key, value in list(params.items())[:12]),
                styles["EdgeSmall"],
            )
        )

    story.append(Paragraph("3. Held-out test results", styles["EdgeH2"]))
    story.append(
        _metric_table(
            metrics,
            [
                ("accuracy", "Accuracy"), ("precision", "Precision"),
                ("recall", "Recall"), ("f1", "F1-score"),
                ("false_positive_rate", "False-positive rate"),
                ("false_negative_rate", "False-negative rate"),
                ("roc_auc", "ROC AUC"), ("pr_auc", "PR AUC"),
                ("tn", "True negatives"), ("fp", "False positives"),
                ("fn", "False negatives"), ("tp", "True positives"),
                ("inference_latency_ms_mean", "Inference latency mean (ms)"),
                ("inference_latency_ms_p95", "Inference latency p95 (ms)"),
                ("throughput_records_per_sec", "Throughput (records/s)"),
                ("training_seconds", "Training time (s)"),
                ("model_size_mb", "Model size (MB)"),
                ("host_cpu_percent_during_training", "Host CPU during training (%)"),
                ("host_memory_rss_mb", "Host RSS after training (MB)"),
            ],
        )
    )

    if metrics.get("unknown_attack_recall") is not None:
        story.append(Paragraph("4. Unknown-attack experiment", styles["EdgeH2"]))
        story.append(
            Paragraph(
                f"Mode: {metrics.get('mode')} · withheld families: "
                f"{', '.join(metrics.get('heldout_families', [])) or 'n/a'}. "
                f"Known-family recall {metrics.get('known_attack_recall')} · withheld-family recall "
                f"{metrics.get('unknown_attack_recall')} · benign FPR "
                f"{metrics.get('benign_false_positive_rate')} · "
                f"LOFO mean unknown recall {metrics.get('lofo_mean_unknown_recall', 'n/a')}.",
                styles["EdgeBody"],
            )
        )
        family_rows = experiment.get("per_family") or []
        if family_rows:
            header = ["Family", "Support", "Withheld", "Supervised", "Anomaly", "Fused", "Mean score"]
            rows = []
            for item in family_rows[:14]:
                rows.append(
                    [
                        str(item.get("family", "")),
                        str(item.get("support", "")),
                        str(item.get("withheld", item.get("skipped", ""))),
                        str(item.get("supervised_recall", item.get("fused_recall", ""))),
                        str(item.get("anomaly_recall", "")),
                        str(item.get("fused_recall", "")),
                        str(item.get("mean_score", "")),
                    ]
                )
            story.append(_simple_table(header, rows))

    story.append(Paragraph("5. Per-class performance", styles["EdgeH2"]))
    if experiment["per_class"]:
        header = ["Class", "Support", "Detected", "Recall", "Mean score"]
        rows = [[str(item["class"]), str(item["support"]), str(item["predicted_positive"]),
                 str(item["recall"]), str(item["mean_score"])] for item in experiment["per_class"]]
        story.append(_simple_table(header, rows))

    story.append(Paragraph("6. Confusion matrix (test rows)", styles["EdgeH2"]))
    matrix = [
        ["", "Predicted benign", "Predicted malicious"],
        ["True benign", str(metrics.get("tn", "n/a")), str(metrics.get("fp", "n/a"))],
        ["True malicious", str(metrics.get("fn", "n/a")), str(metrics.get("tp", "n/a"))],
    ]
    story.append(_simple_table(matrix[0], matrix[1:], widths=[45 * mm, 50 * mm, 50 * mm]))

    story.append(Paragraph("7. Containment activity", styles["EdgeH2"]))
    events = db.query_all(
        "SELECT * FROM containment_events WHERE experiment_id = ? ORDER BY created_at DESC LIMIT 12",
        (experiment_id,),
    )
    if events:
        rows = [
            [event["device_name"] or event["device_id"], event["action"], f"{event['severity']:.1f}",
             event["status"], event.get("verification") or "—"]
            for event in events
        ]
        story.append(_simple_table(["Device", "Action", "Severity", "Status", "Verification"], rows))
    else:
        story.append(Paragraph("No containment events have been recorded for this experiment.", styles["EdgeBody"]))

    story.append(Paragraph("8. Resource observations", styles["EdgeH2"]))
    samples = db.query_all(
        "SELECT payload_json FROM resource_samples WHERE experiment_id = ? ORDER BY created_at DESC LIMIT 1",
        (experiment_id,),
    )
    if samples:
        payload = db.parse_json(samples[0]["payload_json"], {})
        measured = payload.get("measured", {})
        story.append(
            Paragraph(
                f"Measured on this backend host: latency mean {measured.get('latency_mean_ms')} ms, "
                f"p95 {measured.get('latency_p95_ms')} ms, throughput "
                f"{measured.get('throughput_records_per_sec')} records/s, model size "
                f"{measured.get('model_size_mb')} MB. Simulated edge latency budget: "
                f"{payload.get('simulated_edge', {}).get('latency_budget_ms')} ms.",
                styles["EdgeBody"],
            )
        )
    else:
        story.append(
            Paragraph(
                "No dedicated resource benchmark has been run. Training-time host measurements are "
                "reported in section 3; the edge budget is a simulation parameter.",
                styles["EdgeBody"],
            )
        )

    story.append(PageBreak())
    story.append(Paragraph("9. Limitations", styles["EdgeH2"]))
    for limitation in settings.SCOPE_NOTE.split(". "):
        if limitation.strip():
            story.append(Paragraph(f"• {limitation.strip().rstrip('.')}.", styles["EdgeBody"]))
    story.append(
        Paragraph(
            "• Held-out attack families are a proxy for unknown attacks, not proof of zero-day "
            "generalisation. They come from the same dataset and the same feature pipeline.",
            styles["EdgeBody"],
        )
    )
    story.append(
        Paragraph(
            "• Container actions modify simulated state only. No firewall, device or network flow "
            "on the host machine is touched.",
            styles["EdgeBody"],
        )
    )
    story.append(
        Paragraph(
            "• Synthetic or sampled evaluation data cannot establish real-world effectiveness. "
            "Report metrics alongside the dataset version and preprocessing configuration.",
            styles["EdgeBody"],
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "EDGEGUARD AI · generated from stored experiment artifacts · "
            "metrics in this document were not hand-written.",
            styles["EdgeSmall"],
        )
    )
    document.build(story)

    db.insert(
        "reports",
        {
            "id": report_id,
            "experiment_id": experiment_id,
            "title": f"{experiment['name']} — experimental report",
            "format": "pdf",
            "path": str(path),
            "created_at": db.utc_now(),
        },
    )
    return {
        "id": report_id,
        "experiment_id": experiment_id,
        "title": f"{experiment['name']} — experimental report",
        "format": "pdf",
        "created_at": db.utc_now(),
        "download_url": f"/api/reports/{report_id}/download",
    }


def list_reports() -> list[dict[str, Any]]:
    rows = db.query_all("SELECT * FROM reports ORDER BY created_at DESC")
    return [
        {
            **row,
            "download_url": f"/api/reports/{row['id']}/download",
            "exists": Path(row["path"]).exists(),
        }
        for row in rows
    ]


def report_path(report_id: str) -> tuple[Path, str]:
    row = db.query_one("SELECT * FROM reports WHERE id = ?", (report_id,))
    if not row or not Path(row["path"]).exists():
        raise ReportError("Report not found.")
    return Path(row["path"]), row["title"]


def export_csv(experiment_id: str) -> tuple[bytes, str]:
    experiment = modeling.get_experiment(experiment_id)
    metrics = experiment["metrics"]
    rows = [{"metric": key, "value": value} for key, value in metrics.items()
            if not isinstance(value, (list, dict))]
    frame = pd.DataFrame(rows)
    return frame.to_csv(index=False).encode("utf-8"), f"{experiment_id}_metrics.csv"


def export_json(experiment_id: str) -> tuple[bytes, str]:
    experiment = modeling.get_experiment(experiment_id)
    dataset = datasets.get_dataset(experiment["dataset_id"]) if experiment["dataset_id"] else None
    run = preprocessing.get_run(experiment["preprocess_id"]) if experiment["preprocess_id"] else None
    payload = {
        "experiment": experiment,
        "dataset": dataset,
        "preprocessing": run,
        "containment_events": [
            event for event in containment.list_events(200)
            if event.get("experiment_id") == experiment_id
        ],
        "resources": resources.latest_samples(10),
        "exported_at": db.utc_now(),
        "scope": settings.SCOPE_NOTE,
    }
    return json.dumps(payload, indent=2, default=str).encode("utf-8"), f"{experiment_id}_report.json"
