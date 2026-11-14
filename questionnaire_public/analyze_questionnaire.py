#!/usr/bin/env python3
"""Analyze two condition-specific questionnaire group contrasts.

Q13 defines groups for gravity-condition behavior only; Q14 separately
defines groups for zero-gravity-condition behavior only. Each comparison
includes all ten endpoints, including the four metacognitive measures.

Run from this directory with ``python analyze_questionnaire.py``.  The
behavioral files are read only from this folder's ``behavioral_data`` child.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = ROOT.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
import metacognition_analysis  # noqa: E402

DEFAULT_INPUT = ROOT / "questionnaire_data_public.csv"
DEFAULT_BEHAVIOR_DIR = ROOT / "behavioral_data"
DEFAULT_OUTPUT = ROOT / "questionnaire_outputs"

Q13_COLUMN = "q07_original_q13_gravity_understanding"
Q14_COLUMN = "q08_original_q14_zero_gravity_understanding"
Q13_GRAVITY = (
    "3D motion after collision with downward gravitational acceleration; "
    "downward gravity should be considered"
)
Q14_ZERO_GRAVITY = (
    "3D motion after collision under zero or microgravity; downward gravity "
    "need not be considered"
)
BILLIARDS = "2D plane motion after collision, like billiards"

METRICS = [
    "accuracy", "answer_rt_median", "answer_rt_mean", "confidence_mean",
    "confidence_rt_median", "auc", "meta_d", "m_ratio", "auc_ratio", "d_prime",
]
METACOGNITION_METRICS = ["auc", "meta_d", "m_ratio", "auc_ratio"]
METRIC_LABELS = {
    "accuracy": "Accuracy",
    "answer_rt_median": "Decision RT median (ms)",
    "answer_rt_mean": "Decision RT mean (ms)",
    "confidence_mean": "Mean confidence (1–7)",
    "confidence_rt_median": "Confidence RT median (ms)",
    "auc": "Type-2 ROC AUC",
    "meta_d": "meta-d′",
    "m_ratio": "M-ratio",
    "auc_ratio": "AUC-ratio",
    "d_prime": "d′ (reference)",
}
BASE_METRICS = {"accuracy", "answer_rt_median", "answer_rt_mean"}

COMPARISONS = [
    {
        "questionnaire_item": "Q13",
        "column": Q13_COLUMN,
        "condition": "gravity",
        "gravity_code": 1,
        "three_d_option": Q13_GRAVITY,
        "three_d_group": "3D gravity understanding",
    },
    {
        "questionnaire_item": "Q14",
        "column": Q14_COLUMN,
        "condition": "zero_gravity",
        "gravity_code": 0,
        "three_d_option": Q14_ZERO_GRAVITY,
        "three_d_group": "3D zero/microgravity understanding",
    },
]
REQUIRED_BEHAVIOR_COLUMNS = [
    "Gravity", "ExpectedAnswer", "UserAnswer", "ConfidenceRating",
    "AnswerTime", "ConfidenceTime",
]


def _as_finite(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return numeric if np.isfinite(numeric) else float("nan")


def load_questionnaire(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path, dtype={"participant_id": "string", "respondent_id": "string"})
    needed = ["participant_id", "respondent_id", Q13_COLUMN, Q14_COLUMN]
    missing = [column for column in needed if column not in data.columns]
    if missing:
        raise ValueError(f"Missing questionnaire columns: {missing}")
    for column in ["participant_id", "respondent_id", Q13_COLUMN, Q14_COLUMN]:
        data[column] = data[column].fillna("").astype(str).str.strip()
    if data["participant_id"].eq("").any():
        raise ValueError("Blank participant_id in questionnaire_data_public.csv")
    if not data["participant_id"].equals(data["respondent_id"]):
        raise ValueError("participant_id and respondent_id must match row by row after anonymization")
    return data


def build_and_validate_match(questionnaire: pd.DataFrame, behavior_dir: Path,
                             output_dir: Path) -> dict[str, int]:
    paths = sorted(p for p in behavior_dir.glob("*.csv") if p.is_file())
    file_ids = pd.DataFrame({"participant_id": [p.stem for p in paths]})
    q_ids = questionnaire[["participant_id"]].copy()
    duplicate_q_rows = int(q_ids["participant_id"].duplicated(keep=False).sum())
    duplicate_file_rows = int(file_ids["participant_id"].duplicated(keep=False).sum())
    q_unique = int(q_ids["participant_id"].nunique())
    file_unique = int(file_ids["participant_id"].nunique())
    if duplicate_q_rows or duplicate_file_rows:
        raise ValueError(
            "The participant-to-file join is not one-to-one: "
            f"questionnaire duplicate rows={duplicate_q_rows}; "
            f"behavior file duplicate stems={duplicate_file_rows}"
        )

    matched = q_ids.merge(file_ids, on="participant_id", how="left",
                          validate="one_to_one", indicator=True)
    n_unmatched = int(matched["_merge"].eq("left_only").sum())
    q_set = set(q_ids["participant_id"])
    n_behavior_without_q = int((~file_ids["participant_id"].isin(q_set)).sum())
    audit = {
        "questionnaire_rows": int(len(questionnaire)),
        "questionnaire_unique_participants": q_unique,
        "questionnaire_duplicate_id_rows": duplicate_q_rows,
        "behavior_csv_files_in_questionnaire_public": int(len(paths)),
        "behavior_unique_file_stems": file_unique,
        "behavior_duplicate_file_stems": duplicate_file_rows,
        "matched_questionnaire_participants": int(matched["_merge"].eq("both").sum()),
        "questionnaire_ids_without_behavior_file": n_unmatched,
        "behavior_files_without_questionnaire_record": n_behavior_without_q,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"category": key, "count": value} for key, value in audit.items()]).to_csv(
        output_dir / "questionnaire_match_audit_public.csv", index=False, encoding="utf-8-sig"
    )
    if n_unmatched:
        raise ValueError(
            f"{n_unmatched} questionnaire participant_id values have no exact-stem CSV "
            "in questionnaire_public/behavioral_data"
        )
    path_map = {p.stem: p for p in paths}
    if len(path_map) != len(paths):
        raise ValueError("Duplicate behavior CSV stems detected")
    return {"audit": audit, "path_map": path_map}


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def analyze_subject_condition(trial: pd.DataFrame, comparison: dict[str, object],
                              respondent_id: str) -> tuple[dict[str, object], dict[str, object]]:
    missing = [column for column in REQUIRED_BEHAVIOR_COLUMNS if column not in trial.columns]
    if missing:
        raise ValueError(f"Behavior file for {respondent_id} is missing columns: {missing}")
    gravity = _numeric(trial["Gravity"])
    data = trial.loc[gravity.eq(int(comparison["gravity_code"]))].copy()
    stimulus = _numeric(data["ExpectedAnswer"])
    response = _numeric(data["UserAnswer"])
    confidence = _numeric(data["ConfidenceRating"])
    answer_rt = _numeric(data["AnswerTime"])
    confidence_rt = _numeric(data["ConfidenceTime"])

    valid_choice = stimulus.isin([0, 1]) & response.isin([0, 1])
    correct = stimulus.eq(response)
    n_choice = int(valid_choice.sum())
    n_correct = int((valid_choice & correct).sum())
    n_error = int((valid_choice & ~correct).sum())
    choice_qc = n_choice >= 24 and n_correct >= 3 and n_error >= 3

    valid_confidence = valid_choice & confidence.isin(range(1, 8))
    n_confidence = int(valid_confidence.sum())
    n_conf_correct = int((valid_confidence & correct).sum())
    n_conf_error = int((valid_confidence & ~correct).sum())
    confidence_qc = (
        choice_qc and n_confidence >= 24 and n_conf_correct >= 3 and n_conf_error >= 3
    )

    record: dict[str, object] = {
        "respondent_id": respondent_id,
        "questionnaire_item": comparison["questionnaire_item"],
        "condition": comparison["condition"],
        "interpretation_group": None,
        "n_condition_trials": int(len(data)),
        "n_valid_choices": n_choice,
        "n_correct_choices": n_correct,
        "n_error_choices": n_error,
        "choice_qc_pass": bool(choice_qc),
        "n_valid_confidence_trials": n_confidence,
        "n_correct_confidence_trials": n_conf_correct,
        "n_error_confidence_trials": n_conf_error,
        "confidence_qc_pass": bool(confidence_qc),
    }

    # Choice and decision-time measures use all valid S/R trials. Confidence
    # missingness never removes a trial from these non-confidence measures.
    if choice_qc:
        record["accuracy"] = float(correct.loc[valid_choice].mean())
        valid_answer_rt = valid_choice & answer_rt.gt(0) & np.isfinite(answer_rt)
        vals = answer_rt.loc[valid_answer_rt].astype(float)
        record["answer_rt_median"] = float(vals.median()) if len(vals) else float("nan")
        record["answer_rt_mean"] = float(vals.mean()) if len(vals) else float("nan")
        record["n_positive_answer_rt"] = int(len(vals))
    else:
        record.update(accuracy=float("nan"), answer_rt_median=float("nan"),
                      answer_rt_mean=float("nan"), n_positive_answer_rt=0)

    model_record, _, _ = metacognition_analysis.metric_values(data, eligible=bool(confidence_qc))
    valid_conf_values = confidence.loc[valid_confidence].astype(float)
    positive_conf_rt = valid_confidence & confidence_rt.gt(0) & np.isfinite(confidence_rt)
    conf_rt_values = confidence_rt.loc[positive_conf_rt].astype(float)
    if confidence_qc:
        record["confidence_mean"] = (
            float(valid_conf_values.mean()) if len(valid_conf_values) else float("nan")
        )
        record["confidence_rt_median"] = (
            float(conf_rt_values.median()) if len(conf_rt_values) else float("nan")
        )
        record["n_positive_confidence_rt"] = int(len(conf_rt_values))
    else:
        record.update(confidence_mean=float("nan"), confidence_rt_median=float("nan"),
                      n_positive_confidence_rt=0)

    for metric in ["auc", "meta_d", "m_ratio", "auc_ratio", "d_prime"]:
        record[metric] = _as_finite(model_record.get(metric)) if confidence_qc else float("nan")
    diag = {
        "respondent_id": respondent_id,
        "questionnaire_item": comparison["questionnaire_item"],
        "condition": comparison["condition"],
        "n_sdt_trials": int(model_record.get("n_sdt_trials", 0)),
        "n_correct_sdt": int(model_record.get("n_correct_sdt", 0)),
        "n_error_sdt": int(model_record.get("n_error_sdt", 0)),
        "confidence_levels_used": int(model_record.get("confidence_levels_used", 0)),
        "empty_cells": int(model_record.get("empty_cells", 0)),
        "meta_fit_status": str(model_record.get("status", "unknown")),
        "optimizer_success": bool(model_record.get("optimizer_success", False)),
        "iterations": int(model_record.get("iterations", 0)),
        "message": str(model_record.get("message", "")),
        "fit_spec": str(model_record.get("fit_spec", "")),
        "confidence_qc_eligible": bool(confidence_qc),
    }
    return record, diag


def _welch_comparison(billiards: np.ndarray, three_d: np.ndarray) -> dict[str, float | int]:
    billiards = billiards[np.isfinite(billiards)]
    three_d = three_d[np.isfinite(three_d)]
    n_b, n_3d = len(billiards), len(three_d)
    result: dict[str, float | int] = {
        "n_billiards": n_b,
        "n_three_dimensional": n_3d,
        "billiards_mean": float(np.mean(billiards)) if n_b else float("nan"),
        "billiards_sd": float(np.std(billiards, ddof=1)) if n_b > 1 else float("nan"),
        "billiards_median": float(np.median(billiards)) if n_b else float("nan"),
        "three_dimensional_mean": float(np.mean(three_d)) if n_3d else float("nan"),
        "three_dimensional_sd": float(np.std(three_d, ddof=1)) if n_3d > 1 else float("nan"),
        "three_dimensional_median": float(np.median(three_d)) if n_3d else float("nan"),
        "mean_difference_billiards_minus_3d": float(np.mean(billiards) - np.mean(three_d))
        if n_b and n_3d else float("nan"),
        "welch_t": float("nan"), "welch_df": float("nan"),
        "welch_ci95_low": float("nan"), "welch_ci95_high": float("nan"),
        "p_value": float("nan"), "hedges_g": float("nan"),
    }
    if n_b < 2 or n_3d < 2:
        return result

    var_b = float(np.var(billiards, ddof=1))
    var_3d = float(np.var(three_d, ddof=1))
    difference = float(np.mean(billiards) - np.mean(three_d))
    term_b, term_3d = var_b / n_b, var_3d / n_3d
    se_sq = term_b + term_3d
    if se_sq > 0 and np.isfinite(se_sq):
        se = math.sqrt(se_sq)
        denominator = term_b**2 / (n_b - 1) + term_3d**2 / (n_3d - 1)
        df = se_sq**2 / denominator if denominator > 0 else float("nan")
        t_value = difference / se
        p_value = float(2 * stats.t.sf(abs(t_value), df)) if np.isfinite(df) else float("nan")
        critical = float(stats.t.ppf(0.975, df)) if np.isfinite(df) else float("nan")
        ci_low, ci_high = difference - critical * se, difference + critical * se
    else:
        df = float("nan")
        t_value = p_value = ci_low = ci_high = float("nan")

    pooled_df = n_b + n_3d - 2
    pooled_var = ((n_b - 1) * var_b + (n_3d - 1) * var_3d) / pooled_df
    pooled_sd = math.sqrt(pooled_var) if pooled_var > 0 else float("nan")
    hedges = float("nan")
    if np.isfinite(pooled_sd):
        correction = 1 - 3 / (4 * pooled_df - 1)
        hedges = correction * difference / pooled_sd
    result.update(welch_t=t_value, welch_df=df, welch_ci95_low=ci_low,
                  welch_ci95_high=ci_high, p_value=p_value, hedges_g=hedges)
    return result


def _bh(p_values: pd.Series) -> pd.Series:
    adjusted = pd.Series(np.nan, index=p_values.index, dtype=float)
    valid = p_values.notna() & np.isfinite(pd.to_numeric(p_values, errors="coerce"))
    if valid.any():
        adjusted.loc[valid] = multipletests(
            pd.to_numeric(p_values.loc[valid]), method="fdr_bh"
        )[1]
    return adjusted


def _make_trial_model_inputs(q14_focal: pd.DataFrame,
                             all_condition_metrics: pd.DataFrame,
                             behavior_cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Prepare Q14 focal-group trial rows for the primary agent's moderation model."""
    paired_flags = all_condition_metrics.groupby("subject", sort=False).agg(
        behavior_paired_included=("behavior_condition_pass", "all"),
        auc_paired_included=("confidence_condition_pass", "all"),
    )
    group_map: dict[str, str] = {}
    for _, row in q14_focal.iterrows():
        group_map[str(row["participant_id"])] = (
            "billiards" if row[Q14_COLUMN] == BILLIARDS else "three_d"
        )

    model_rows: list[dict[str, object]] = []
    for participant, interpretation in group_map.items():
        raw = behavior_cache[participant]
        gravity = _numeric(raw["Gravity"])
        stimulus = _numeric(raw["ExpectedAnswer"])
        response = _numeric(raw["UserAnswer"])
        confidence = _numeric(raw["ConfidenceRating"])
        answer_rt = _numeric(raw["AnswerTime"])
        confidence_rt = _numeric(raw["ConfidenceTime"])
        valid_choice = stimulus.isin([0, 1]) & response.isin([0, 1])
        correct = stimulus.eq(response)
        valid_confidence = valid_choice & confidence.isin(range(1, 8))
        confidence_values = confidence.loc[valid_confidence]
        confidence_between = float(confidence_values.mean()) if len(confidence_values) else float("nan")
        n_trials = len(raw)
        order = np.arange(1, n_trials + 1, dtype=float)
        trial_c = (order - order.mean()) / order.std(ddof=0) if n_trials > 1 else np.zeros(n_trials)
        flags = paired_flags.loc[participant]
        left_scale = _numeric(raw["LeftScale"])
        right_scale = _numeric(raw["RightScale"])
        target = _numeric(raw["Target"])
        velocity = _numeric(raw["LeftVelY"])

        for pos in range(n_trials):
            if not gravity.iloc[pos] in (0, 1):
                continue
            is_correct = float(correct.iloc[pos]) if bool(valid_choice.iloc[pos]) else np.nan
            conf_value = float(confidence.iloc[pos]) if bool(valid_confidence.iloc[pos]) else np.nan
            answer_value = float(answer_rt.iloc[pos]) if bool(valid_choice.iloc[pos] and answer_rt.iloc[pos] > 0) else np.nan
            confidence_value = float(confidence_rt.iloc[pos]) if bool(valid_confidence.iloc[pos] and confidence_rt.iloc[pos] > 0) else np.nan
            left_value, right_value = left_scale.iloc[pos], right_scale.iloc[pos]
            size_pair = (
                f"{left_value:g}_{right_value:g}"
                if np.isfinite(left_value) and np.isfinite(right_value) else ""
            )
            trial_number = raw.iloc[pos].get("TrialNumber", pos + 1)
            model_rows.append({
                "subject": participant,
                "condition": "gravity" if int(gravity.iloc[pos]) == 1 else "zero_gravity",
                "interpretation": interpretation,
                "trial_number": trial_number,
                "trial_order": pos + 1,
                "correct": is_correct,
                "confidence": conf_value,
                "velocity": velocity.iloc[pos],
                "size_pair": size_pair,
                "target": target.iloc[pos],
                "trial_c": float(trial_c[pos]),
                "trial_c2": float(trial_c[pos] ** 2),
                "answer_rt": answer_value,
                "confidence_rt": confidence_value,
                "confidence_between": confidence_between,
                "confidence_within": (
                    conf_value - confidence_between
                    if np.isfinite(conf_value) and np.isfinite(confidence_between) else np.nan
                ),
                "behavior_paired_included": bool(flags["behavior_paired_included"]),
                "auc_paired_included": bool(flags["auc_paired_included"]),
            })
    return pd.DataFrame(model_rows)


def analyze(questionnaire_path: Path = DEFAULT_INPUT,
            behavior_dir: Path = DEFAULT_BEHAVIOR_DIR,
            output_dir: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    questionnaire = load_questionnaire(questionnaire_path)
    match = build_and_validate_match(questionnaire, behavior_dir, output_dir)
    path_map: dict[str, Path] = match["path_map"]
    behavior_cache: dict[str, pd.DataFrame] = {}
    all_condition_rows: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []

    # Produce both conditions for all matched public respondents. These
    # condition-level metrics also supply the two condition-specific group contrasts.
    for participant in questionnaire["participant_id"].astype(str):
        behavior_cache[participant] = pd.read_csv(path_map[participant])
        for condition, gravity_code in [("gravity", 1), ("zero_gravity", 0)]:
            condition_spec = {
                "questionnaire_item": "all_participants",
                "condition": condition,
                "gravity_code": gravity_code,
            }
            row, diag = analyze_subject_condition(
                behavior_cache[participant], condition_spec, participant
            )
            row["subject"] = participant
            row["behavior_condition_pass"] = bool(row["choice_qc_pass"])
            row["confidence_condition_pass"] = bool(row["confidence_qc_pass"])
            diag["subject"] = participant
            all_condition_rows.append(row)
            diagnostics.append(diag)

    all_condition_metrics = pd.DataFrame(all_condition_rows)
    paired_flags = all_condition_metrics.groupby("subject", sort=False).agg(
        behavior_paired_included=("behavior_condition_pass", "all"),
        auc_paired_included=("confidence_condition_pass", "all"),
    )
    all_condition_metrics["behavior_paired_included"] = all_condition_metrics["subject"].map(
        paired_flags["behavior_paired_included"]
    ).astype(bool)
    all_condition_metrics["auc_paired_included"] = all_condition_metrics["subject"].map(
        paired_flags["auc_paired_included"]
    ).astype(bool)
    all_condition_metrics = all_condition_metrics.drop(
        columns=["respondent_id", "questionnaire_item", "interpretation_group"], errors="ignore"
    )
    diagnostic_df = pd.DataFrame(diagnostics).drop(columns=["respondent_id"], errors="ignore")

    # Assemble only the specified response options and corresponding condition.
    subject_rows: list[dict[str, object]] = []
    for comparison in COMPARISONS:
        qcol = str(comparison["column"])
        focal = questionnaire[qcol].isin([BILLIARDS, comparison["three_d_option"]])
        for _, qrow in questionnaire.loc[focal].iterrows():
            participant = str(qrow["participant_id"])
            metric_row = all_condition_metrics.loc[
                all_condition_metrics["subject"].eq(participant)
                & all_condition_metrics["condition"].eq(comparison["condition"])
            ].iloc[0].to_dict()
            metric_row["respondent_id"] = participant
            metric_row["questionnaire_item"] = comparison["questionnaire_item"]
            if qrow[qcol] == BILLIARDS:
                metric_row["interpretation_group"] = "billiards"
                metric_row["interpretation_label"] = BILLIARDS
                metric_row["group"] = "billiards"
            else:
                metric_row["interpretation_group"] = "three_dimensional"
                metric_row["interpretation_label"] = str(comparison["three_d_option"])
                metric_row["group"] = "three_d"
            subject_rows.append(metric_row)

    subject_df = pd.DataFrame(subject_rows)
    if subject_df.empty:
        raise ValueError("No questionnaire participants selected either focal response")

    comparison_rows: list[dict[str, object]] = []
    flow_rows: list[dict[str, object]] = []
    for comparison in COMPARISONS:
        item = str(comparison["questionnaire_item"])
        subset = subject_df.loc[subject_df["questionnaire_item"].eq(item)]
        qcol = str(comparison["column"])
        q_n = int(questionnaire[qcol].isin([BILLIARDS, comparison["three_d_option"]]).sum())
        nonfocal = int((~questionnaire[qcol].isin([BILLIARDS, comparison["three_d_option"]])).sum())
        for metric in METRICS:
            is_base = metric in BASE_METRICS
            qc_col = "choice_qc_pass" if is_base else "confidence_qc_pass"
            group_values: dict[str, np.ndarray] = {}
            for group in ["billiards", "three_dimensional"]:
                group_frame = subset.loc[subset["interpretation_group"].eq(group)]
                eligible_frame = group_frame.loc[group_frame[qc_col].astype(bool)]
                vals = pd.to_numeric(eligible_frame[metric], errors="coerce")
                finite = vals[np.isfinite(vals)]
                group_values[group] = finite.to_numpy(dtype=float)
                n_selected = int(len(group_frame))
                n_base_qc = int(group_frame["choice_qc_pass"].sum())
                n_conf_qc = int(group_frame["confidence_qc_pass"].sum())
                n_qc_eligible = int(len(eligible_frame))
                n_finite = int(len(finite))
                flow_rows.append({
                    "analysis_scope": "condition_specific_group_comparison",
                    "questionnaire_item": item,
                    "condition": comparison["condition"],
                    "interpretation_group": group,
                    "metric": metric,
                    "metric_label": METRIC_LABELS[metric],
                    "qc_required": "choice" if is_base else "confidence",
                    "n_questionnaire_selected": n_selected,
                    "n_behavior_matched": n_selected,
                    "n_choice_qc_pass": n_base_qc,
                    "n_confidence_qc_pass": n_conf_qc,
                    "n_qc_eligible": n_qc_eligible,
                    "n_analyzed": n_finite,
                    "n_excluded_qc": n_selected - n_qc_eligible,
                    "n_excluded_missing_endpoint": n_qc_eligible - n_finite,
                })
            stats_row = _welch_comparison(
                group_values["billiards"], group_values["three_dimensional"]
            )
            stats_row.update({
                "questionnaire_item": item,
                "condition": comparison["condition"],
                "comparison": (
                    f"{comparison['three_d_group']} vs two-dimensional billiards-like group in "
                    f"{comparison['condition']} condition"
                ),
                "metric": metric,
                "metric_label": METRIC_LABELS[metric],
                "unit": "proportion" if metric == "accuracy" else (
                    "rating points" if metric == "confidence_mean" else (
                        "dimensionless" if metric in {"auc", "meta_d", "m_ratio", "auc_ratio", "d_prime"}
                        else "ms"
                    )
                ),
                "n_questionnaire_focal": q_n,
                "mean_difference_direction": "two-dimensional billiards-like minus 3D",
                "hedges_g_method": "pooled SD with small-sample correction J=1-3/(4*df_pooled-1)",
            })
            comparison_rows.append(stats_row)

        flow_rows.append({
            "analysis_scope": "condition_specific_group_comparison",
            "questionnaire_item": item,
            "condition": comparison["condition"],
            "interpretation_group": "outside_focal_options",
            "metric": "all_endpoints",
            "metric_label": "Outside the two specified response options",
            "qc_required": "not_applicable",
            "n_questionnaire_selected": nonfocal,
            "n_behavior_matched": nonfocal,
            "n_choice_qc_pass": 0,
            "n_confidence_qc_pass": 0,
            "n_qc_eligible": 0,
            "n_analyzed": 0,
            "n_excluded_qc": 0,
            "n_excluded_missing_endpoint": 0,
        })

    comparisons = pd.DataFrame(comparison_rows)
    comparisons["q_bh_10_endpoints"] = np.nan
    comparisons["q_bh_4_metacognition"] = np.nan
    for item in ["Q13", "Q14"]:
        item_mask = comparisons["questionnaire_item"].eq(item)
        comparisons.loc[item_mask, "q_bh_10_endpoints"] = _bh(
            comparisons.loc[item_mask, "p_value"]
        ).to_numpy()
        meta_mask = item_mask & comparisons["metric"].isin(METACOGNITION_METRICS)
        comparisons.loc[meta_mask, "q_bh_4_metacognition"] = _bh(
            comparisons.loc[meta_mask, "p_value"]
        ).to_numpy()

    # Q14 two-condition rows support the condition-by-interpretation models. They
    # are sample accounting, not additional inferential group comparisons.
    q14_focal = questionnaire.loc[
        questionnaire[Q14_COLUMN].isin([BILLIARDS, Q14_ZERO_GRAVITY])
    ].copy()
    for group, response_value in [("billiards", BILLIARDS), ("three_d", Q14_ZERO_GRAVITY)]:
        people = q14_focal.loc[q14_focal[Q14_COLUMN].eq(response_value), "participant_id"].astype(str)
        for condition in ["gravity", "zero_gravity"]:
            group_rows = all_condition_metrics.loc[
                all_condition_metrics["subject"].isin(people)
                & all_condition_metrics["condition"].eq(condition)
            ]
            for metric in METRICS:
                is_base = metric in BASE_METRICS
                qc_col = "behavior_condition_pass" if is_base else "confidence_condition_pass"
                eligible = group_rows.loc[group_rows[qc_col].astype(bool)]
                finite = pd.to_numeric(eligible[metric], errors="coerce")
                n_selected = int(len(group_rows))
                n_endpoint = int(np.isfinite(finite).sum())
                flow_rows.append({
                    "analysis_scope": "q14_all_conditions_metrics",
                    "questionnaire_item": "Q14",
                    "condition": condition,
                    "interpretation_group": group,
                    "metric": metric,
                    "metric_label": METRIC_LABELS[metric],
                    "qc_required": "choice" if is_base else "confidence",
                    "n_questionnaire_selected": n_selected,
                    "n_behavior_matched": n_selected,
                    "n_choice_qc_pass": int(group_rows["behavior_condition_pass"].sum()),
                    "n_confidence_qc_pass": int(group_rows["confidence_condition_pass"].sum()),
                    "n_qc_eligible": int(len(eligible)),
                    "n_analyzed": n_endpoint,
                    "n_excluded_qc": n_selected - int(len(eligible)),
                    "n_excluded_missing_endpoint": int(len(eligible)) - n_endpoint,
                    "n_behavior_paired_included": int(group_rows["behavior_paired_included"].sum()),
                    "n_auc_paired_included": int(group_rows["auc_paired_included"].sum()),
                })

    comparisons["n_three_d"] = comparisons["n_three_dimensional"]
    comparisons["mean_billiards"] = comparisons["billiards_mean"]
    comparisons["sd_billiards"] = comparisons["billiards_sd"]
    comparisons["median_billiards"] = comparisons["billiards_median"]
    comparisons["mean_three_d"] = comparisons["three_dimensional_mean"]
    comparisons["sd_three_d"] = comparisons["three_dimensional_sd"]
    comparisons["median_three_d"] = comparisons["three_dimensional_median"]
    comparisons["difference_billiards_minus_three_d"] = comparisons["mean_difference_billiards_minus_3d"]
    comparisons["ci95_low"] = comparisons["welch_ci95_low"]
    comparisons["ci95_high"] = comparisons["welch_ci95_high"]
    comparisons["p_bh"] = comparisons["q_bh_10_endpoints"]

    subject_df = subject_df.sort_values(
        ["questionnaire_item", "interpretation_group", "respondent_id"]
    ).reset_index(drop=True)
    diagnostic_df = diagnostic_df.sort_values(["condition", "subject"]).reset_index(drop=True)
    comparisons = comparisons[[
        "questionnaire_item", "condition", "comparison", "metric", "metric_label", "unit",
        "n_questionnaire_focal", "n_billiards", "n_three_d", "billiards_mean", "billiards_sd",
        "billiards_median", "mean_billiards", "sd_billiards", "median_billiards",
        "mean_three_d", "sd_three_d", "median_three_d",
        "three_dimensional_mean", "three_dimensional_sd", "three_dimensional_median",
        "mean_difference_billiards_minus_3d", "difference_billiards_minus_three_d",
        "welch_t", "welch_df", "welch_ci95_low", "welch_ci95_high", "ci95_low", "ci95_high",
        "p_value", "hedges_g", "q_bh_10_endpoints", "q_bh_4_metacognition", "p_bh",
        "mean_difference_direction", "hedges_g_method",
    ]]
    output_dir.mkdir(parents=True, exist_ok=True)
    subject_df.to_csv(output_dir / "questionnaire_subject_metrics.csv", index=False, encoding="utf-8-sig")
    comparisons.to_csv(output_dir / "questionnaire_group_comparisons.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(flow_rows).to_csv(output_dir / "questionnaire_sample_flow.csv", index=False, encoding="utf-8-sig")
    diagnostic_df.to_csv(output_dir / "questionnaire_model_diagnostics.csv", index=False, encoding="utf-8-sig")
    all_condition_metrics.to_csv(
        output_dir / "questionnaire_all_conditions_metrics.csv", index=False, encoding="utf-8-sig"
    )
    trial_model_input = _make_trial_model_inputs(q14_focal, all_condition_metrics, behavior_cache)
    trial_model_input.to_csv(
        output_dir / "questionnaire_trial_model_input.csv", index=False, encoding="utf-8-sig"
    )

    q14_interpretation = {
        str(row["participant_id"]): ("billiards" if row[Q14_COLUMN] == BILLIARDS else "three_d")
        for _, row in q14_focal.iterrows()
    }
    q14_paired_summary = {}
    for group in ["billiards", "three_d"]:
        people = [person for person, label in q14_interpretation.items() if label == group]
        q14_paired_summary[group] = {
            "questionnaire_focal_n": len(people),
            "behavior_paired_included": int(paired_flags.loc[people, "behavior_paired_included"].sum()),
            "auc_paired_included": int(paired_flags.loc[people, "auc_paired_included"].sum()),
        }

    summary = {
        "analysis": "Two exploratory condition-specific questionnaire group comparisons",
        "primary_group_comparisons": [
            {
                "questionnaire_item": spec["questionnaire_item"],
                "grouping_variable": spec["column"],
                "behavioral_condition": spec["condition"],
                "three_dimensional_response": spec["three_d_option"],
                "billiards_response": BILLIARDS,
                "endpoints": METRICS,
            }
            for spec in COMPARISONS
        ],
        "source_questionnaire": "questionnaire_public/questionnaire_data_public.csv",
        "source_behavior": "questionnaire_public/behavioral_data/*.csv",
        "join": match["audit"],
        "join_rule": "Exact participant_id to behavior CSV stem; one-to-one validation; no order-based matching",
        "direction": "two-dimensional billiards-like minus 3D",
        "qc": {
            "choice": "valid ExpectedAnswer/UserAnswer in {0,1}; >=24 trials and >=3 correct and >=3 errors",
            "confidence": "choice QC plus >=24 integer confidence trials in {1,...,7} and >=3 correct and >=3 errors among them",
            "condition_specific": True,
            "other_condition_qc_required": False,
        },
        "inference": {
            "test": "two-sided Welch independent-samples t test",
            "confidence_interval": "95% Welch interval for the two-dimensional billiards-like-minus-3D mean difference",
            "effect_size": "Hedges g using pooled SD and J=1-3/(4*pooled_df-1)",
            "p_adjustment": "BH across 10 endpoints separately within each questionnaire item; separate BH across the four metacognition endpoints",
            "reported_correction": "BH across all 10 endpoints within each question is the main reporting family; the four-metacognition family is supplementary",
            "exploratory_association": "Questionnaire was completed after the task",
        },
        "selected_group_counts": {
            item: {
                group: int(((subject_df["questionnaire_item"] == item) &
                            (subject_df["interpretation_group"] == group)).sum())
                for group in ["billiards", "three_dimensional"]
            }
            for item in ["Q13", "Q14"]
        },
        "all_condition_metrics": {
            "participants": int(all_condition_metrics["subject"].nunique()),
            "participant_condition_rows": int(len(all_condition_metrics)),
            "behavior_paired_included": int(paired_flags["behavior_paired_included"].sum()),
            "auc_paired_included": int(paired_flags["auc_paired_included"].sum()),
            "q14_focal_trial_rows": int(len(trial_model_input)),
            "q14_focal_participants": int(trial_model_input["subject"].nunique()),
            "q14_focal_paired_qc": q14_paired_summary,
        },
        "model_status_counts": {
            str(k): int(v) for k, v in diagnostic_df["meta_fit_status"].value_counts(dropna=False).items()
        },
        "comparison_results": json.loads(comparisons.to_json(orient="records")),
    }
    summary_path = output_dir / "questionnaire_analysis_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    write_report(comparisons, flow_rows, summary, output_dir)
    return summary


def _fmt(value: object, digits: int = 3) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "NA"
    return f"{number:.{digits}f}" if np.isfinite(number) else "NA"


def write_report(comparisons: pd.DataFrame, flow_rows: list[dict[str, object]],
                 summary: dict[str, object], output_dir: Path) -> None:
    lines = [
        "# 问卷任务理解分组比较",
        "",
        "本报告的主要比较为：按第13题分组，比较三维组与二维台球式组在重力条件下的表现；按第14题重新分组，比较两组在无重力条件下的表现。每项比较包含全部10项指标，包括 AUC、meta-d′、有符号 M-ratio 和 AUC-ratio。行为数据仅来自本目录 `behavioral_data/`，并按公开匿名 `participant_id` 与行为 CSV 文件名一一连接。问卷在任务后完成，因此分组差异作为探索性关联解释。",
        "",
        "检验均为被试水平的双尾 Welch 独立样本 t 检验。差值方向固定为二维台球式理解减三维理解；95% CI 对应该均值差。Hedges g 使用两组 pooled SD，并作小样本修正 J=1−3/(4×pooled df−1)。主要结论采用 `q_bh_10_endpoints`，在每道题内对10项终点作 BH 校正；`q_bh_4_metacognition` 在每道题内对 AUC、meta-d′、M-ratio、AUC-ratio 四项另作补充校正。",
        "",
        "每一问只分析指定的两个选项，其他回答不纳入组间检验。组间比较的有效人数按各终点分别计算。基础选择终点要求有效 ExpectedAnswer/UserAnswer 编码为0/1，至少24个试次且至少3个正确和3个错误；信心终点另外要求至少24个1–7级整数信心试次，并在这些试次中至少3个正确和3个错误。两道题分别按其对应条件筛选，不要求另一条件通过QC。反应时只使用大于0毫秒的值；信心缺失不影响准确率和决策时分析。",
        "",
    ]
    section_specs = [
        ("Q13：gravity 条件下的三维重力理解组与二维台球式组", "Q13"),
        ("Q14：zero-gravity 条件下的三维无／微重力理解组与二维台球式组", "Q14"),
    ]
    for title, item in section_specs:
        lines.extend([f"## {title}", ""])
        rows = comparisons.loc[comparisons["questionnaire_item"].eq(item)]
        lines.extend([
            "| 指标 | 二维台球式 n；M (SD)；中位数 | 三维组 n；M (SD)；中位数 | 差值（台球−三维） | Welch t(df) | 95% CI | p | q：10项 | q：元认知4项 | Hedges g |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for _, row in rows.iterrows():
            b = f"{int(row['n_billiards'])}; {_fmt(row['mean_billiards'])} ({_fmt(row['sd_billiards'])}); {_fmt(row['median_billiards'])}"
            d = f"{int(row['n_three_d'])}; {_fmt(row['mean_three_d'])} ({_fmt(row['sd_three_d'])}); {_fmt(row['median_three_d'])}"
            t_df = f"{_fmt(row['welch_t'], 2)} ({_fmt(row['welch_df'], 1)})"
            ci = f"[{_fmt(row['welch_ci95_low'])}, {_fmt(row['welch_ci95_high'])}]"
            lines.append(
                f"| {row['metric_label']} | {b} | {d} | {_fmt(row['mean_difference_billiards_minus_3d'])} | {t_df} | {ci} | {_fmt(row['p_value'], 4)} | {_fmt(row['q_bh_10_endpoints'], 4)} | {_fmt(row['q_bh_4_metacognition'], 4)} | {_fmt(row['hedges_g'])} |"
            )
        lines.append("")
        selected = summary["selected_group_counts"][item]
        lines.append(
            f"问卷焦点选项人数：二维台球式理解 {selected['billiards']} 人，三维理解 {selected['three_dimensional']} 人。每个终点的纳入与排除人数见 `questionnaire_sample_flow.csv`。"
        )
        lines.append("")
    lines.extend([
        "## 复现",
        "",
        "在本目录运行 `python analyze_questionnaire.py`。指标表、组间比较、样本流、模型诊断、汇总 JSON 与本报告写入 `questionnaire_outputs/`。",
        "",
    ])
    (output_dir / "questionnaire_analysis_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> dict[str, object]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--behavior-dir", type=Path, default=DEFAULT_BEHAVIOR_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = analyze(args.input, args.behavior_dir, args.output_dir)
    counts = summary["selected_group_counts"]
    print("Questionnaire group comparisons completed")
    print(f"Exact one-to-one joins: {summary['join']['matched_questionnaire_participants']}")
    for item in ["Q13", "Q14"]:
        print(f"{item}: billiards={counts[item]['billiards']}, three_dimensional={counts[item]['three_dimensional']}")
    print(f"Outputs: {args.output_dir.resolve()}")
    return summary


if __name__ == "__main__":
    main()
