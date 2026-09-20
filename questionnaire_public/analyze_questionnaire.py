#!/usr/bin/env python3
"""Analyze the de-identified English questionnaire dataset.

The primary analyses are deliberately limited to the comparisons requested for
the PB&R revision:

1. Original Q14: the two focal interpretations are compared with a paired
   samples t-test on respondent-level binary indicators, conditional on
   selecting one of those two options.
2. Original Q13 versus original Q14: the gravity-consistent and zero-gravity-
   consistent choices are compared with a paired-samples t-test because the
   same respondents answered both questions.

Run from this directory with:
    python analyze_questionnaire.py
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "questionnaire_data_public.csv"
DEFAULT_OUTPUT = ROOT / "questionnaire_outputs"

Q07_GRAVITY = (
    "3D motion after collision with downward gravitational acceleration; "
    "downward gravity should be considered"
)
Q08_ZERO_GRAVITY = (
    "3D motion after collision under zero or microgravity; downward gravity "
    "need not be considered"
)
Q08_BILLIARDS = "2D plane motion after collision, like billiards"


def wilson_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    if total <= 0:
        return float("nan"), float("nan")
    z = float(stats.norm.ppf(1 - (1 - confidence) / 2))
    p = successes / total
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    half_width = (
        z
        * math.sqrt((p * (1 - p) / total) + (z**2 / (4 * total**2)))
        / denominator
    )
    return center - half_width, center + half_width


def format_p(value: float) -> str:
    if not np.isfinite(value):
        return "NA"
    if value < 0.001:
        return "< .001"
    return f"= {value:.3f}"


def paired_mean_ci(values: pd.Series, confidence: float = 0.95) -> tuple[float, float]:
    values = pd.Series(values, dtype=float).dropna()
    if len(values) <= 1:
        return float("nan"), float("nan")
    mean = float(values.mean())
    standard_error = float(stats.sem(values))
    critical_value = float(stats.t.ppf(1 - (1 - confidence) / 2, df=len(values) - 1))
    half_width = critical_value * standard_error
    return mean - half_width, mean + half_width


def load_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = [
        "respondent_id",
        "completion_time_seconds",
        "q07_original_q13_gravity_understanding",
        "q08_original_q14_zero_gravity_understanding",
    ]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    for column in df.columns:
        if df[column].dtype == object:
            df[column] = df[column].fillna("").astype(str).str.strip()
    return df


def save_response_counts(df: pd.DataFrame, output_dir: Path) -> None:
    rows: list[dict[str, object]] = []
    question_columns = [column for column in df.columns if column.startswith("q")]
    for column in question_columns:
        counts = df[column].value_counts(dropna=False)
        for response, count in counts.items():
            rows.append(
                {
                    "variable": column,
                    "response": response,
                    "count": int(count),
                    "proportion": float(count / len(df)),
                }
            )
    pd.DataFrame(rows).to_csv(
        output_dir / "questionnaire_response_counts.csv",
        index=False,
        encoding="utf-8-sig",
    )


def save_q13_q14_crosstab(df: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    categories = [
        Q07_GRAVITY,
        Q08_BILLIARDS,
        Q08_ZERO_GRAVITY,
        "Abstract motion unrelated to a physical scene",
    ]
    table = pd.crosstab(
        df["q07_original_q13_gravity_understanding"],
        df["q08_original_q14_zero_gravity_understanding"],
        dropna=False,
    ).reindex(index=categories, columns=categories, fill_value=0)
    table.index.name = "original_q13_response"
    table.columns.name = "original_q14_response"
    table.to_csv(
        output_dir / "questionnaire_q13_q14_transition_table.csv",
        encoding="utf-8-sig",
    )
    return table


def run_core_analyses(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    q14 = df["q08_original_q14_zero_gravity_understanding"]
    q14_focal = q14.isin([Q08_BILLIARDS, Q08_ZERO_GRAVITY])
    q14_focal_n = int(q14_focal.sum())
    q14_focal_df = df.loc[q14_focal]
    q14_billiards_indicator = q14_focal_df["q08_original_q14_zero_gravity_understanding"].eq(Q08_BILLIARDS).astype(float)
    q14_zero_indicator = q14_focal_df["q08_original_q14_zero_gravity_understanding"].eq(Q08_ZERO_GRAVITY).astype(float)
    q14_billiards_n = int(q14_billiards_indicator.sum())
    q14_zero_n = int(q14_zero_indicator.sum())
    q14_difference = q14_zero_indicator - q14_billiards_indicator
    q14_test = stats.ttest_rel(q14_zero_indicator, q14_billiards_indicator)
    q14_difference_ci = paired_mean_ci(q14_difference)
    q14_billiards_ci = wilson_interval(q14_billiards_n, q14_focal_n)
    q14_zero_ci = wilson_interval(q14_zero_n, q14_focal_n)

    q13_gravity_flag = df["q07_original_q13_gravity_understanding"].eq(Q07_GRAVITY)
    q14_zero_flag = q14.eq(Q08_ZERO_GRAVITY)
    q13_only = int((q13_gravity_flag & ~q14_zero_flag).sum())
    q14_only = int((~q13_gravity_flag & q14_zero_flag).sum())
    both = int((q13_gravity_flag & q14_zero_flag).sum())
    neither = int((~q13_gravity_flag & ~q14_zero_flag).sum())
    q13_indicator = q13_gravity_flag.astype(float)
    q14_zero_indicator = q14_zero_flag.astype(float)
    q13_q14_difference = q14_zero_indicator - q13_indicator
    q13_q14_test = stats.ttest_rel(q14_zero_indicator, q13_indicator)
    q13_q14_difference_ci = paired_mean_ci(q13_q14_difference)

    q13_n = int(q13_gravity_flag.sum())
    q14_n = int(q14_zero_flag.sum())
    q13_prop = q13_n / len(df)
    q14_prop = q14_n / len(df)

    results = pd.DataFrame(
        [
            {
                "comparison_id": "q14_focal_interpretations",
                "comparison": "Original Q14: 2D plane motion versus 3D zero/microgravity motion",
                "test": "Paired-samples t-test on binary indicators, conditional on the two focal responses",
                "total_n": len(df),
                "analyzed_n": q14_focal_n,
                "category_1": Q08_BILLIARDS,
                "category_1_n": q14_billiards_n,
                "category_1_proportion": q14_billiards_n / q14_focal_n,
                "category_2": Q08_ZERO_GRAVITY,
                "category_2_n": q14_zero_n,
                "category_2_proportion": q14_zero_n / q14_focal_n,
                "proportion_difference_category_2_minus_category_1": (q14_zero_n - q14_billiards_n) / q14_focal_n,
                "statistic": q14_test.statistic,
                "degrees_of_freedom": q14_focal_n - 1,
                "statistic_label": "paired t statistic (category 2 - category 1)",
                "p_value": q14_test.pvalue,
                "effect_metric": "paired mean difference in binary indicators (category 2 - category 1)",
                "effect_value": q14_difference.mean(),
                "effect_ci95_low": q14_difference_ci[0],
                "effect_ci95_high": q14_difference_ci[1],
                "notes": "The 24 other Q14 responses are excluded from this conditional two-option comparison.",
            },
            {
                "comparison_id": "q13_vs_q14_consistent_choices",
                "comparison": "Original Q13 gravity-consistent choice versus original Q14 zero-gravity-consistent choice",
                "test": "Paired-samples t-test on paired binary indicators",
                "total_n": len(df),
                "analyzed_n": len(df),
                "category_1": "Original Q13: 3D falling motion with downward gravity",
                "category_1_n": q13_n,
                "category_1_proportion": q13_prop,
                "category_2": "Original Q14: 3D zero/microgravity motion",
                "category_2_n": q14_n,
                "category_2_proportion": q14_prop,
                "proportion_difference_category_2_minus_category_1": q14_prop - q13_prop,
                "statistic": q13_q14_test.statistic,
                "degrees_of_freedom": len(df) - 1,
                "statistic_label": "paired t statistic (category 2 - category 1)",
                "p_value": q13_q14_test.pvalue,
                "effect_metric": "paired mean difference in binary indicators (category 2 - category 1)",
                "effect_value": q13_q14_difference.mean(),
                "effect_ci95_low": q13_q14_difference_ci[0],
                "effect_ci95_high": q13_q14_difference_ci[1],
                "notes": f"Paired cells: Q13-only={q13_only}, Q14-only={q14_only}, both={both}, neither={neither}.",
            },
        ]
    )

    summary = {
        "n_respondents": int(len(df)),
        "q14_focal_n": q14_focal_n,
        "q14_billiards_n": q14_billiards_n,
        "q14_zero_gravity_n": q14_zero_n,
        "q14_paired_t": float(q14_test.statistic),
        "q14_paired_t_df": int(q14_focal_n - 1),
        "q14_paired_t_p": float(q14_test.pvalue),
        "q14_mean_difference_zero_gravity_minus_billiards": float(q14_difference.mean()),
        "q14_mean_difference_zero_gravity_minus_billiards_ci95": list(q14_difference_ci),
        "q14_billiards_wilson_ci95": list(q14_billiards_ci),
        "q14_zero_gravity_wilson_ci95": list(q14_zero_ci),
        "q13_gravity_consistent_n": q13_n,
        "q14_zero_gravity_consistent_n": q14_n,
        "q13_vs_q14_q13_only": q13_only,
        "q13_vs_q14_q14_only": q14_only,
        "q13_vs_q14_both": both,
        "q13_vs_q14_neither": neither,
        "q13_vs_q14_paired_t": float(q13_q14_test.statistic),
        "q13_vs_q14_paired_t_df": int(len(df) - 1),
        "q13_vs_q14_paired_t_p": float(q13_q14_test.pvalue),
        "q13_vs_q14_mean_difference_q14_minus_q13": float(q13_q14_difference.mean()),
        "q13_vs_q14_mean_difference_q14_minus_q13_ci95": list(q13_q14_difference_ci),
        "q13_proportion": q13_prop,
        "q14_proportion": q14_prop,
    }
    return results, summary


def make_figure(df: pd.DataFrame, summary: dict[str, object], output_dir: Path) -> None:
    q14_billiards_n = int(summary["q14_billiards_n"])
    q14_zero_n = int(summary["q14_zero_gravity_n"])
    q13_n = int(summary["q13_gravity_consistent_n"])
    q14_n = int(summary["q14_zero_gravity_consistent_n"])
    n = int(summary["n_respondents"])

    colors = ["#4C78A8", "#F58518"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), constrained_layout=True)

    axes[0].bar(
        ["2D plane motion\n(like billiards)", "3D zero/microgravity\n(no downward gravity)"],
        [q14_billiards_n, q14_zero_n],
        color=colors,
        width=0.65,
    )
    axes[0].set_title("Original Q14: focal responses")
    axes[0].set_ylabel("Number of respondents")
    axes[0].set_ylim(0, max(q14_zero_n, q14_billiards_n) * 1.18)
    for idx, value in enumerate([q14_billiards_n, q14_zero_n]):
        axes[0].text(idx, value + 3, f"{value}\n({value / (q14_billiards_n + q14_zero_n):.1%} of focal)", ha="center")

    axes[1].bar(
        ["Original Q13:\n3D gravity-consistent", "Original Q14:\n3D zero-gravity-consistent"],
        [q13_n, q14_n],
        color=colors,
        width=0.65,
    )
    axes[1].set_title("Paired marginal proportions")
    axes[1].set_ylabel("Number of respondents")
    axes[1].set_ylim(0, n * 1.12)
    for idx, value in enumerate([q13_n, q14_n]):
        axes[1].text(idx, value + 4, f"{value}\n({value / n:.1%})", ha="center")

    for axis in axes:
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.tick_params(axis="x", labelsize=9)
    fig.suptitle("Physics-comprehension questionnaire: requested comparisons", fontsize=13)
    fig.savefig(output_dir / "questionnaire_core_comparisons.png", dpi=300)
    plt.close(fig)


def write_report(summary: dict[str, object], output_dir: Path) -> None:
    q14_t = float(summary["q14_paired_t"])
    q14_t_df = int(summary["q14_paired_t_df"])
    q14_p = float(summary["q14_paired_t_p"])
    q13_q14_t = float(summary["q13_vs_q14_paired_t"])
    q13_q14_t_df = int(summary["q13_vs_q14_paired_t_df"])
    q13_q14_p = float(summary["q13_vs_q14_paired_t_p"])
    q14_focal_n = int(summary["q14_focal_n"])
    q14_billiards_n = int(summary["q14_billiards_n"])
    q14_zero_n = int(summary["q14_zero_gravity_n"])
    q13_n = int(summary["q13_gravity_consistent_n"])
    q14_n = int(summary["q14_zero_gravity_consistent_n"])
    q13_only = int(summary["q13_vs_q14_q13_only"])
    q14_only = int(summary["q13_vs_q14_q14_only"])
    both = int(summary["q13_vs_q14_both"])
    neither = int(summary["q13_vs_q14_neither"])
    q14_ci = summary["q14_zero_gravity_wilson_ci95"]
    q14_difference_ci = summary["q14_mean_difference_zero_gravity_minus_billiards_ci95"]
    q13_q14_difference_ci = summary["q13_vs_q14_mean_difference_q14_minus_q13_ci95"]

    text = f"""# Questionnaire analysis report

## Dataset

- Respondents: **{int(summary['n_respondents'])}**
- Original submission timestamps were removed from the public dataset.
- Public respondent IDs were newly assigned and do not encode the source identifier.

## Requested comparison 1: original Q14

Among the **{q14_focal_n}** respondents who selected one of the two focal Q14 interpretations:

- **{q14_billiards_n} ({q14_billiards_n / q14_focal_n:.1%})** selected 2D plane motion after collision, like billiards.
- **{q14_zero_n} ({q14_zero_n / q14_focal_n:.1%})** selected 3D zero/microgravity motion without considering downward gravity.
- A paired-samples t-test was conducted on two binary indicators for the same respondents (category 2 minus category 1): **t({q14_t_df}) = {q14_t:.2f}, p {format_p(q14_p)}**.
- Mean difference in the binary indicators (3D zero/microgravity minus 2D billiards): **{float(summary['q14_mean_difference_zero_gravity_minus_billiards']):.3f}**, 95% CI **[{q14_difference_ci[0]:.3f}, {q14_difference_ci[1]:.3f}]**.
- Wilson 95% CI for the zero/microgravity proportion among focal responses: **[{q14_ci[0]:.1%}, {q14_ci[1]:.1%}]**.

The t-test is conditional on the two focal options; the **24** other Q14 responses are not treated as support for either focal interpretation.

## Requested comparison 2: original Q13 versus original Q14

Binary indicators were defined within each respondent:

- Original Q13 indicator = selected the 3D falling-motion interpretation with downward gravity.
- Original Q14 indicator = selected the 3D zero/microgravity interpretation without downward gravity.

Marginally, **{q13_n}/{int(summary['n_respondents'])} ({q13_n / int(summary['n_respondents']):.1%})** endorsed the Q13 gravity-consistent interpretation, compared with **{q14_n}/{int(summary['n_respondents'])} ({q14_n / int(summary['n_respondents']):.1%})** for the Q14 zero-gravity-consistent interpretation.

Because both indicators came from the same respondents, a paired-samples t-test was conducted on the two binary indicators:

- Q13-only: **{q13_only}**
- Q14-only: **{q14_only}**
- Both: **{both}**
- Neither: **{neither}**
- Paired t-test for Q14 zero/microgravity minus Q13 gravity-consistent: **t({q13_q14_t_df}) = {q13_q14_t:.2f}, p {format_p(q13_q14_p)}**.
- Mean difference in the binary indicators (Q14 minus Q13): **{float(summary['q13_vs_q14_mean_difference_q14_minus_q13']):.3f}**, 95% CI **[{q13_q14_difference_ci[0]:.3f}, {q13_q14_difference_ci[1]:.3f}]**.

Thus, the gravity-consistent interpretation was endorsed more often in original Q13 than the zero-gravity-consistent interpretation was endorsed in original Q14, with a statistically significant paired marginal difference.

## Interpretation boundary

These results show how respondents described the task and how their interpretations differed across the two questionnaire prompts. They support a condition-associated difference in reported task understanding. They do not, by themselves, establish that an internal gravity prior was causally violated or updated, because the two task contexts may also differ in motion profile, cue alignment, and perceived task demands.

## Reproduction

Run:

```text
python analyze_questionnaire.py
```

The script writes the CSV tables, JSON summary, and PNG figure to `questionnaire_outputs/`.
"""
    (output_dir / "questionnaire_analysis_report.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    df = load_data(args.input)
    results, summary = run_core_analyses(df)
    results.to_csv(args.output_dir / "questionnaire_results.csv", index=False, encoding="utf-8-sig")
    save_response_counts(df, args.output_dir)
    save_q13_q14_crosstab(df, args.output_dir)
    make_figure(df, summary, args.output_dir)
    (args.output_dir / "questionnaire_analysis_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    write_report(summary, args.output_dir)

    print(f"Respondents: {summary['n_respondents']}")
    print(
        "Original Q14 focal comparison: "
        f"2D={summary['q14_billiards_n']}, "
        f"3D zero/microgravity={summary['q14_zero_gravity_n']}, "
        f"paired t({summary['q14_paired_t_df']})={summary['q14_paired_t']:.6g}, "
        f"p={summary['q14_paired_t_p']:.6g}"
    )
    print(
        "Original Q13 vs Q14 paired comparison: "
        f"Q13-only={summary['q13_vs_q14_q13_only']}, "
        f"Q14-only={summary['q13_vs_q14_q14_only']}, "
        f"paired t({summary['q13_vs_q14_paired_t_df']})={summary['q13_vs_q14_paired_t']:.6g}, "
        f"p={summary['q13_vs_q14_paired_t_p']:.6g}"
    )


if __name__ == "__main__":
    main()
