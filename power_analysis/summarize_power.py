"""Create machine-readable tables from the actual G*Power records.

Reads aggregate analysis outputs only. Does not refit study models or alter
behavior, eye-tracking, figures, or the main results report.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)


def number(mapping, key, default=""):
    return float(mapping[key]) if key in mapping else default


def summarize(output):
    jobs = json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    records = [json.loads(line) for line in
               (output / "gpower_results.jsonl").read_text(encoding="utf-8").splitlines()]
    indexed = {r["scenario"]["id"]: r for r in records}
    if len(indexed) != len(records) or set(indexed) != {j["id"] for j in jobs}:
        raise ValueError("Completed records must match all scenario identifiers exactly")
    required, sensitivity = [], []
    for job in jobs:
        record = indexed[job["id"]]
        if record["scenario"] != job:
            raise ValueError(f"Scenario changed: {job['id']}")
        for label, value in job["inputs"].items():
            entered = record["entered_inputs"][label]
            if isinstance(value, (float, int)):
                if not math.isclose(float(entered), value, rel_tol=1e-12, abs_tol=1e-12):
                    raise ValueError(f"Input field mismatch: {job['id']} / {label}")
            elif str(value) != entered:
                raise ValueError(f"Selection mismatch: {job['id']} / {label}")
        expected = {"signed-rank": "A.R.E. method", "correlation": "exact distribution",
                    "correlation-sensitivity": "exact distribution",
                    "logistic-reference": "Demidenko (2007) with var corr"}.get(job["group"])
        if expected and expected not in record["native_protocol"]:
            raise ValueError(f"Unexpected G*Power option: {job['id']}")
        i, o = job["inputs"], record["outputs"]
        effect_keys = [k for k in i if k.startswith("Effect size") or k in
                       ("Correlation ρ H1", "Odds ratio")]
        option = re.search(r"Options:\s*([^\n]+)", record["native_protocol"])
        common = dict(scenario_id=job["id"], analysis=job["group"],
                      family=job["family"], statistical_test=job["test"],
                      alpha=i["α err prob"], target_power=i["Power (1-β err prob)"],
                      tails=i.get("Tail(s)", "F test upper tail"), unit=job["unit"],
                      tested_predictors=i.get("Number of tested predictors", ""),
                      total_predictors=i.get("Total number of predictors", ""),
                      other_predictor_r_squared=i.get("R² other X", ""),
                      parent_distribution=i.get("Parent distribution", ""),
                      gpower_option=option.group(1).strip() if option else "default distribution test",
                      interpretation=job["role"])
        if job["mode"] == "A priori":
            key = effect_keys[0]
            required.append(dict(**common, effect_definition=key, assumed_effect=i[key],
                                 required_n=int(float(o["Total sample size"])),
                                 group_1_n=number(o, "Sample size group 1"),
                                 group_2_n=number(o, "Sample size group 2"),
                                 actual_power=float(o["Actual power"])))
        else:
            key = next(k for k in o if k.startswith("Effect size") or k == "Correlation ρ H1")
            n1, n2 = i.get("Sample size group 1", ""), i.get("Sample size group 2", "")
            sensitivity.append(dict(**common, effect_definition=key,
                                    eligible_n=i.get("Total sample size", n1+n2 if n1 != "" else ""),
                                    group_1_n=n1, group_2_n=n2,
                                    detectable_effect=float(o[key])))
    write_csv(output / "gpower_sample_sizes.csv", required)
    write_csv(output / "gpower_sensitivity.csv", sensitivity)

    tables = ROOT / "outputs" / "tables"
    effects = read_csv(tables / "paired_condition_effects.csv")
    main_summary = json.loads((ROOT / "outputs" / "analysis_summary.json").read_text(encoding="utf-8"))
    base_n = int(main_summary["matched"])
    counts = {row["metric"]: int(float(row["n"])) for row in effects}
    snapshot = [dict(endpoint=k, matched_records=base_n, eligible_n=v,
                     retained_fraction=v/base_n, source="outputs/tables/paired_condition_effects.csv")
                for k, v in counts.items()]
    eye_n = int(main_summary["eye_included"])
    snapshot.append(dict(endpoint="primary_eye_sample", matched_records=base_n,
                         eligible_n=eye_n, retained_fraction=eye_n/base_n,
                         source="outputs/analysis_summary.json"))
    write_csv(output / "endpoint_sample_sizes.csv", snapshot)
    retention = []
    for row in required:
        if row["analysis"] != "paired" or row["assumed_effect"] not in (.15, .2, .25, .3):
            continue
        if row["target_power"] not in (.8, .9) or row["alpha"] not in (.05, .005):
            continue
        for endpoint in ("accuracy", "auc", "meta_d", "m_ratio", "auc_ratio", "primary_eye_sample"):
            observed_n = eye_n if endpoint == "primary_eye_sample" else counts[endpoint]
            fraction = observed_n/base_n
            retention.append(dict(scenario_id=row["scenario_id"], endpoint=endpoint,
                                  assumed_dz=row["assumed_effect"], alpha=row["alpha"],
                                  target_power=row["target_power"], required_eligible_n=row["required_n"],
                                  observed_eligible_n=observed_n, matched_records=base_n,
                                  observed_retention=fraction,
                                  expected_matched_records_before_endpoint_qc=math.ceil(row["required_n"]/fraction),
                                  attained_eligible_requirement=observed_n >= row["required_n"],
                                  interpretation="Future planning extrapolation using observed endpoint retention; expected count, not a prospective recruitment justification or assurance"))
    write_csv(output / "retention_planning.csv", retention)

    dsm = read_csv(tables / "dsm_results_by_metric.csv")
    grouped = {}
    for row in dsm:
        key = row["metric"], row["condition"], row["representation"]
        grouped.setdefault(key, []).append(row)
    dsm_rows = []
    for (metric, condition, representation), group in grouped.items():
        pairs = {(int(float(r["n_high"])), int(float(r["n_low"]))) for r in group}
        if len(pairs) != 1:
            raise ValueError("DSM group counts vary within one comparison family")
        high, low = pairs.pop()
        dsm_rows.append(dict(metric=metric, condition=condition, representation=representation,
                             n_high=high, n_low=low, comparison_count=len(group),
                             single_metric_bonferroni_alpha=.05/len(group),
                             four_metric_bonferroni_alpha=.05/(4*len(group)),
                             interpretation="Benchmark alpha values; actual analyses use permutation tests and BH-FDR"))
    write_csv(output / "dsm_design_summary.csv", dsm_rows)
    correlations = read_csv(tables / "accuracy_metacognition_correlations.csv")
    write_csv(output / "correlation_sample_sizes.csv",
              [dict(metric=r["metric"], condition=r["condition"], eligible_n=r["n"],
                    source="outputs/tables/accuracy_metacognition_correlations.csv") for r in correlations])
    mixed = read_csv(tables / "mixed_model_power_summary.csv")
    keep = ["model", "target", "true_or", "replicates", "usable", "failed", "n_participants",
            "n_trials", "detection_all_replicates", "monte_carlo_se",
            "monte_carlo_ci95_low", "monte_carlo_ci95_high", "coverage_95_successful", "role"]
    write_csv(output / "existing_mixed_model_simulation.csv",
              [{k: r[k] for k in keep} for r in mixed])
    print(f"Summarized {len(required)} required-N and {len(sensitivity)} sensitivity scenarios.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "power_analysis")
    args = parser.parse_args()
    summarize(args.output)
