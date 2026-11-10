"""Research documentation content served by the API."""

from __future__ import annotations

from ..settings import RESEARCH_TITLE

SECTIONS = [
    {
        "id": "abstract",
        "title": "Abstract",
        "paragraphs": [
            "Internet of Things (IoT) networks operate under a difficult combination of constraints: "
            "heterogeneous devices, limited compute and memory at the edge, and attacks whose families "
            "change faster than labelled datasets can be updated. This work designs and develops an "
            "adaptive edge cyber-resilience mechanism that learns per-device normal behaviour, detects "
            "deviations with a fused statistical and isolation-based detector, assesses severity from "
            "context rather than a single threshold, and autonomously selects a containment response "
            "inside a safe simulated environment.",
            "The platform separates detection from response evaluation. Known attacks are measured with "
            "normal binary classification metrics on a held-out test split. Unknown-attack sensitivity "
            "is measured by withholding entire attack families from training and evaluation using "
            "leave-one-attack-family-out (LOFO) protocols. A closed loop of MONITOR, DETECT, ASSESS, "
            "CONTAIN, VERIFY and LEARN records every decision and verifies the simulated effect of each "
            "action on real held-out records.",
            "EDGEGUARD AI is the research prototype built for this study. It accepts public IoT datasets, "
            "performs leakage-safe preprocessing, trains supervised and anomaly detectors, runs "
            "unknown-attack experiments and containment replays, and reports measured host resource "
            "costs alongside clearly labelled simulated edge budgets. The contribution is an auditable "
            "end-to-end methodology; it is not a claim of production security effectiveness.",
        ],
    },
    {
        "id": "problem",
        "title": "Problem Statement",
        "paragraphs": [
            "Edge gateways in IoT deployments must decide, with limited CPU and memory and without "
            "cloud connectivity, whether observed traffic is benign, a known attack, or something the "
            "model has never been trained to recognise. Static thresholds either flag legitimate "
            "behaviour changes (high false-positive rate) or are raised until slow attacks pass "
            "unnoticed. Supervised classifiers trained on known attack families cannot by construction "
            "recognise a family absent from their labels, yet dashboards often present their accuracy "
            "as if it demonstrated zero-day detection.",
            "Response introduces a second problem. Isolation and rate limiting consume edge resources, "
            "can disrupt critical devices, and are difficult to evaluate because an attack that has "
            "already succeeded may look 'contained'. A credible mechanism must therefore state which "
            "records were unseen during training, distinguish known from suspected-unknown detections, "
            "verify that a response changed the observed behaviour, and report failure modes honestly.",
            "A third problem is reproducibility. Dataset version, target-column choice, preprocessing "
            "fits, split boundaries, model hyperparameters, thresholds and resource conditions all "
            "affect reported metrics. The platform must persist each of these and compute every "
            "reported number from the stored experiment, never from a template.",
        ],
    },
    {
        "id": "objectives",
        "title": "Research Objectives",
        "bullets": [
            "Design a per-device, adaptive anomaly-detection method that tolerates legitimate behaviour drift while protecting its baseline from poisoning.",
            "Implement a transparent severity assessment that combines anomaly magnitude, detector confidence, asset criticality and network context.",
            "Evaluate unknown-attack sensitivity with withheld families and leave-one-attack-family-out training, rather than claiming zero-day detection from known-class accuracy.",
            "Implement a closed-loop containment controller with graduated responses, criticality guards, resource guards, verification and recovery.",
            "Quantify detection and response cost on a resource-constrained edge envelope, separating real host measurements from simulated device budgets.",
            "Deliver a reproducible research platform in which every dataset, preprocessing fit, model, metric and report is traceable to stored artifacts.",
        ],
    },
    {
        "id": "literature",
        "title": "Literature Review",
        "paragraphs": [
            "IoT intrusion-detection research has produced strong public benchmarks — Edge-IIoTset, "
            "CICIoT2023 and ToN-IoT among them — and a wide family of supervised classifiers. Random "
            "Forests and gradient-boosted trees remain effective tabular baselines; recent benchmark "
            "studies repeatedly show near-ceiling scores on random splits. Those numbers are optimistic "
            "when records from the same capture appear in both train and test, and they do not measure "
            "generalisation to unseen attack families.",
            "Unsupervised and one-class methods (Isolation Forest, One-Class SVM, autoencoders) are "
            "frequently proposed for novelty detection because they can be fitted on benign data only. "
            "Their weakness is the false-positive rate under legitimate distribution shift: firmware "
            "updates, new schedules and seasonal load all move benign telemetry. Adaptive thresholds "
            "and online baselines address drift but create a poisoning surface, because an attacker "
            "that is learned as 'normal' disappears from the detector's view.",
            "Autonomous response work spans SDN-based blocking, quarantine VLANs and moving-target "
            "defence. Much of it is evaluated on whether an action was emitted, not whether it worked. "
            "Verification is the gap: a response should be judged by a measured reduction in the "
            "offending behaviour, with inconclusive cases reported rather than counted as successes. "
            "Resource-aware response is also under-studied; containment itself consumes the constrained "
            "resource the mechanism was meant to protect.",
        ],
    },
    {
        "id": "gap",
        "title": "Research Gap",
        "bullets": [
            "Known-attack classification accuracy is routinely presented as evidence of unknown-attack capability.",
            "Adaptive baselines are proposed for drift but are rarely evaluated against an explicit poisoning adversary or an audit trail of refused updates.",
            "Containment is evaluated by action emission rather than by a post-action behavioural measurement, and inconclusive outcomes are often hidden.",
            "Edge resource claims are frequently estimated analytically without separating host measurements from device simulations.",
            "End-to-end reproducibility — dataset version, target selection, split-first preprocessing, threshold calibration and report generation — is rarely packaged with the research artifact.",
        ],
    },
    {
        "id": "methodology",
        "title": "Proposed Methodology",
        "paragraphs": [
            "The pipeline begins with dataset ingestion and profiling: row and column counts, dtypes, "
            "missing values, duplicate records, candidate target columns and class distributions. The "
            "researcher explicitly selects the label column; the platform never assumes a universal "
            "column name. Benign labels are resolved from the selected target, and every other label is "
            "an attack family used for evaluation grouping.",
            "Preprocessing is leakage-safe by construction. Rows without labels are dropped, exact "
            "duplicates are removed before splitting, and the data is split into train, validation and "
            "test partitions with stratification. Imputers, one-hot encoders, scaling and optional "
            "univariate feature selection are fitted on the training partition only and then applied "
            "to validation and test. Oversampling, when selected, is applied to the training partition "
            "after the split. Identifier-like and leakage-prone columns are excluded by name and can be "
            "removed explicitly.",
            "Detection supports two families. Supervised models (Random Forest, XGBoost when installed, "
            "Decision Tree, Logistic Regression) learn from labelled train rows. Anomaly models "
            "(Isolation Forest, One-Class SVM, reconstruction autoencoder) are fitted on benign training "
            "rows only; their raw scores are normalised against benign validation scores and a "
            "configurable quantile sets the threshold. Reported metrics are computed once on the "
            "untouched test partition.",
            "Unknown-attack evaluation withholds selected families from train and validation, trains a "
            "supervised detector on the remaining families and an anomaly detector on benign rows, and "
            "reports known-family recall, withheld-family recall, benign false-positive rate and the "
            "score distribution separately. In LOFO mode this is repeated for each family, producing a "
            "per-family generalisation table. No row from a withheld family contributes to fitting or "
            "threshold calibration.",
            "Severity combines anomaly magnitude above threshold, detector confidence, asset criticality "
            "and network context (the share of fleet currently anomalous). The containment policy maps "
            "severity to OBSERVE, RATE_LIMIT, REAUTHENTICATE or QUARANTINE, with a critical-asset guard, "
            "a graduated-response guard, cooldown and simulated CPU-headroom downgrade. Verification "
            "re-scores subsequent held-out records through the same model after applying the action's "
            "traffic allowance to volume features; it reports SUCCESS, FAILURE or INCONCLUSIVE. Recovery "
            "releases the device and restores its active state.",
            "All run parameters, artifacts and metrics are persisted. Reports are generated from those "
            "stored values, and measured host latency, CPU and memory are labelled separately from the "
            "configured edge budget.",
        ],
    },
    {
        "id": "architecture",
        "title": "System Architecture",
        "paragraphs": [
            "The frontend is a React single-page application built with Vite and Tailwind CSS, using "
            "Recharts for metric and score visualisations. It talks to a FastAPI backend over REST and "
            "a WebSocket channel used for live job progress.",
            "The backend persists application state in SQLite (datasets, preprocessing runs, experiments, "
            "models, containment events, reports and resource samples) and stores large artifacts on "
            "disk: uploaded datasets, fitted preprocessing pipelines, trained model bundles, test "
            "predictions, benchmark samples and PDF reports. Background work runs in a bounded thread "
            "pool and reports progress through the job registry.",
            "The ML layer uses scikit-learn for supervised models and anomaly detectors, pandas and "
            "NumPy for data handling, and joblib for artifact persistence. XGBoost is optional. The "
            "Kaggle importer uses the Kaggle API with credentials supplied only through backend "
            "environment variables or the standard Kaggle configuration file.",
        ],
        "diagram": [
            "Dataset upload / Kaggle API",
            "→ profiler (targets, dtypes, missing, duplicates)",
            "→ leakage-safe preprocessing (split first, fit on train)",
            "→ supervised model OR benign-only anomaly detector",
            "→ held-out test metrics + unknown-family experiments",
            "→ threat composition (benign / known / suspected unknown)",
            "→ simulated containment (MONITOR → DETECT → ASSESS → CONTAIN → VERIFY → LEARN)",
            "→ report (PDF / CSV / JSON) + measured resource profile",
        ],
    },
    {
        "id": "implementation",
        "title": "Implementation Details",
        "bullets": [
            "Datasets are versioned by name: uploading a second file with the same name creates version 2 and links it to its parent.",
            "CSV profiling is streamed in chunks; duplicate counting is exact up to one million rows and explicitly marked as sampled above that.",
            "The preprocessing pipeline persists imputers, encoders, scaler and feature-selection mask, so prediction and containment verification use the exact training-time transformation.",
            "Training runs as a background job with staged progress: loading, fitting, validation scoring, test evaluation, latency measurement and artifact persistence.",
            "Test predictions are saved to Parquet and reused by threat intelligence, containment replay and reporting instead of recomputing or inventing events.",
            "Containment verification applies the action's allowance to recognised volume/count columns of real held-out rows, re-scores them, and compares the before/after mean anomaly score.",
            "The resource benchmark measures end-to-end transformation and scoring latency on real test rows with psutil; the edge budget remains a separate simulation parameter.",
            "Every API error is surfaced to the UI with a message; there are no alert-only buttons.",
        ],
    },
    {
        "id": "experimental",
        "title": "Experimental Methodology",
        "bullets": [
            "Unit of evaluation: one row of the held-out test split, with its dataset-provided family label retained for grouping.",
            "Known-attack metrics: accuracy, precision, recall, F1, false-positive rate, ROC AUC, PR AUC and a confusion matrix; per-family recall is reported for every present family.",
            "Unknown-attack protocol: holdout mode withholds one or more families from train/validation; LOFO mode retrains once per family and reports each withheld result.",
            "Thresholds for anomaly detectors are calibrated on benign validation scores only, at a documented quantile; supervised decision thresholds are reported explicitly.",
            "Latency and throughput are measured on the backend host with wall-clock timing over real test rows. Edge CPU/RAM budgets are simulated and labelled as such.",
            "Containment outcomes are verified by re-scoring future held-out records under the simulated action; INCONCLUSIVE outcomes are retained in the record.",
            "Random seeds, split sizes, preprocessing configuration and model hyperparameters are persisted with every experiment for reproducibility.",
        ],
    },
    {
        "id": "results",
        "title": "Results and Discussion",
        "paragraphs": [
            "This platform does not embed results. The Research Analytics and Experimental Reports modules "
            "display only metrics computed from experiments run in this installation. That is deliberate: "
            "static screenshots of favourable numbers are not evidence, and copying numbers between "
            "datasets or runs would break the audit trail.",
            "Interpret results along three axes. First, known-attack performance on the held-out split "
            "after leakage-safe preprocessing. Second, withheld-family recall and the benign false-positive "
            "rate; a detector that flags everything can achieve high unknown recall, so the two must be "
            "read together. Third, response and resource behaviour: how many actions were verified as "
            "effective, how many were inconclusive, and whether the simulated edge budget permitted the "
            "selected response.",
            "The legacy simulation bundled with this repository provides a complementary controlled study "
            "with three systems (static threshold, adaptive detection, adaptive closed loop) on identical "
            "synthetic traffic. Its documented trade-offs — unnecessary quarantines under harder benign "
            "drift, and containment capability disappearing before detection capability on a starved "
            "gateway — illustrate the failure modes this platform is designed to expose rather than hide.",
        ],
    },
    {
        "id": "conclusion",
        "title": "Conclusion",
        "paragraphs": [
            "EDGEGUARD AI turns the research question into an executable, auditable workflow. It makes the "
            "distinction between known and withheld attack families explicit, fits every transformation on "
            "training data only, measures every reported metric from stored test predictions, and verifies "
            "simulated containment against subsequent held-out traffic instead of assuming success.",
            "The mechanism is adaptive in detection, graduated and resource-aware in response, and honest "
            "about its limits. Its value for an academic evaluation is not a single headline accuracy but "
            "the traceable chain from dataset version to preprocessing fit, model artifact, test split, "
            "unknown-family experiment, containment event and generated report.",
        ],
    },
    {
        "id": "future",
        "title": "Future Scope",
        "bullets": [
            "Integrate an SDN or virtual-firewall testbed so containment can act on isolated real traffic rather than simulated state.",
            "Evaluate on independently collected attack corpora and adversarial refits of attack parameters to test unknown-family generalisation more strictly.",
            "Add sequential change detection and explicit attacker modelling for baseline adaptation instead of fixed drift gates.",
            "Support multi-gateway coordination and federated benign-only calibration without sharing raw telemetry.",
            "Add encrypted-traffic feature extraction and protocol-aware flow features.",
            "Add concept-drift annotations and time-aware splits to measure performance decay across capture periods.",
            "Package the stack as a reproducible container with pinned dataset checksums for publication artifacts.",
        ],
    },
]

REFERENCES = [
    "Ferrag, M. A., Friha, O., Hamouda, D., Maglaras, L., Janicke, H. (2022). Edge-IIoTset: A New Comprehensive Realistic Cyber Security Dataset of IoT and IIoT Applications for Centralized and Federated Learning. IEEE Access.",
    "Neto, E. C. P., Dadkhah, S., Ferreira, R., Zohourian, A., Lu, R., Ghorbani, A. A. (2023). CICIoT2023: A Real-Time Dataset and Benchmark for Large-Scale Attacks in IoT Environment. Sensors.",
    "Alsaedi, A., Moustafa, N., Tari, Z., Mahmood, A., Anwar, A. (2020). TON_IoT Telemetry Dataset: A New Generation Dataset of IoT and IIoT for Data-Driven Intrusion Detection Systems. IEEE Access.",
    "Liu, F. T., Ting, K. M., Zhou, Z.-H. (2008). Isolation Forest. IEEE ICDM.",
    "Breiman, L. (2001). Random Forests. Machine Learning.",
    "Chen, T., Guestrin, C. (2016). XGBoost: A Scalable Tree Boosting System. ACM SIGKDD.",
    "Chandola, V., Banerjee, A., Kumar, V. (2009). Anomaly Detection: A Survey. ACM Computing Surveys.",
    "Sommer, R., Paxson, V. (2010). Outside the Closed World: On Using Machine Learning for Network Intrusion Detection. IEEE Symposium on Security and Privacy.",
    "Pendlebury, F., Pierazzi, F., Jordaney, R., Kinder, J., Cavallaro, L. (2019). TESSERACT: Eliminating Experimental Bias in Malware Classification across Space and Time. USENIX Security.",
]


def documentation() -> dict:
    return {
        "title": "EDGEGUARD AI — Research Documentation",
        "research_title": RESEARCH_TITLE,
        "sections": SECTIONS,
        "references": REFERENCES,
        "scope_note": (
            "Documentation describes the implemented methodology. Quantitative results are produced "
            "by the experiments in this installation and are not embedded here."
        ),
    }
