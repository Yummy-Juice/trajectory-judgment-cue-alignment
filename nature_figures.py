#!/usr/bin/env python3
"""Generate the final serif-font publication figure set.

The drawing layer is deliberately self-contained matplotlib code.  All figure
labels are English and use a serif family; every numerical panel writes a CSV
source beside the other analysis tables.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Rectangle
import numpy as np
import pandas as pd
from scipy import stats


ROOT = Path(__file__).resolve().parent
TABLE = ROOT / "outputs" / "tables"
FIG = ROOT / "outputs" / "figures"
SEED = 20260713

COL = {
    "gravity": "#355C7D",
    "zero": "#B86449",
    "gravity_soft": "#C5D2DD",
    "zero_soft": "#E6C3B5",
    "teal": "#2F7A74",
    "teal_soft": "#BFD8D3",
    "violet": "#746581",
    "gold": "#B89555",
    "ink": "#24323D",
    "mid": "#68737B",
    "light": "#D7DADD",
    "pale": "#F5F3EF",
    "white": "#FFFFFF",
}


def setup_style() -> None:
    mpl.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "STIX Two Text", "STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": 7.4,
        "axes.labelsize": 7.8,
        "axes.titlesize": 8.8,
        "axes.titleweight": "semibold",
        "axes.edgecolor": COL["ink"],
        "axes.linewidth": .72,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "xtick.labelsize": 6.9,
        "ytick.labelsize": 6.9,
        "xtick.major.width": .65,
        "ytick.major.width": .65,
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "legend.frameon": False,
        "legend.fontsize": 6.7,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
    })


def export(fig: plt.Figure, stem: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    base = FIG / stem
    common = {"facecolor": "white"}
    fig.savefig(base.with_suffix(".svg"), **common)
    fig.savefig(base.with_suffix(".pdf"), **common)
    # The PNG is embedded in the Word report, where 300 dpi is already
    # publication-clear and keeps Office rendering responsive. Vector PDF/SVG
    # and the 600 dpi TIFF remain the submission-grade masters.
    fig.savefig(base.with_suffix(".png"), dpi=300, **common)
    fig.savefig(base.with_suffix(".tiff"), dpi=600,
                pil_kwargs={"compression": "tiff_lzw"}, **common)
    plt.close(fig)


def panel(ax: plt.Axes, label: str, x: float = -.12, y: float = 1.04) -> None:
    ax.text(x, y, label, transform=ax.transAxes, fontsize=9.2,
            fontweight="bold", ha="left", va="bottom", color=COL["ink"])


def p_text(p: float) -> str:
    if not np.isfinite(p):
        return "p = NA"
    if p < .001:
        return "p < .001"
    return f"p = {p:.3f}".replace("0.", ".")


def mean_ci(values: np.ndarray) -> tuple[float, float, float]:
    x = np.asarray(values, float)
    x = x[np.isfinite(x)]
    mean = float(x.mean())
    if len(x) < 2:
        return mean, np.nan, np.nan
    lo, hi = stats.t.interval(.95, len(x)-1, loc=mean, scale=stats.sem(x))
    return mean, float(lo), float(hi)


def bootstrap_mean_ci(values: np.ndarray, rng: np.random.Generator,
                      n_boot: int = 2500) -> tuple[float, float, float]:
    x = np.asarray(values, float)
    x = x[np.isfinite(x)]
    draws = rng.choice(x, (n_boot, len(x)), replace=True).mean(axis=1)
    return float(x.mean()), *np.quantile(draws, [.025, .975]).tolist()


def paired_distribution(ax: plt.Axes, summary: pd.DataFrame, metric: str,
                        ylabel: str, rng: np.random.Generator,
                        ylim: tuple[float, float] | None = None) -> None:
    wide = summary.pivot(index="subject", columns="condition", values=metric).dropna()
    values = [wide.gravity.to_numpy(), wide.zero_gravity.to_numpy()]
    vp = ax.violinplot(values, positions=[0, 1], widths=.78, showextrema=False)
    for body, fill in zip(vp["bodies"], [COL["gravity_soft"], COL["zero_soft"]]):
        body.set_facecolor(fill)
        body.set_edgecolor("none")
        body.set_alpha(.78)
    sample = rng.choice(len(wide), min(90, len(wide)), replace=False)
    for idx in sample:
        ax.plot([0, 1], [values[0][idx], values[1][idx]], color=COL["light"],
                lw=.34, alpha=.46, zorder=1)
    for xpos, vals, color in [(0, values[0], COL["gravity"]),
                              (1, values[1], COL["zero"])]:
        ax.scatter(np.full(len(vals), xpos)+rng.normal(0, .035, len(vals)), vals,
                   s=3.2, color=color, alpha=.22, edgecolors="none",
                   rasterized=True, zorder=2)
        mean, lo, hi = mean_ci(vals)
        ax.errorbar(xpos, mean, yerr=[[mean-lo], [hi-mean]], fmt="o", ms=4,
                    color=COL["ink"], mfc="white", mew=.85, capsize=2.3,
                    lw=.85, zorder=5)
    ax.set_xticks([0, 1], ["Gravity", "Zero gravity"])
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", length=0)
    if ylim:
        ax.set_ylim(*ylim)


def figure1_behavior() -> None:
    rng = np.random.default_rng(SEED)
    effects = pd.read_csv(TABLE / "paired_condition_effects.csv")
    summary = pd.read_csv(TABLE / "participant_condition_summary.csv")
    order = ["accuracy", "answer_rt_median", "answer_rt_mean",
             "confidence_mean", "confidence_rt_median", "auc"]
    labels = {
        "accuracy": "Accuracy",
        "answer_rt_median": "Decision RT (median)",
        "answer_rt_mean": "Decision RT (mean)",
        "confidence_mean": "Confidence",
        "confidence_rt_median": "Confidence RT",
        "auc": "Type-2 ROC AUC",
    }
    rows = []
    for metric in order:
        r = effects.loc[effects.metric.eq(metric)].iloc[0]
        sd_diff = abs(r.difference_zero_minus_gravity/r.cohens_dz) if abs(r.cohens_dz) > 1e-8 else np.nan
        rows.append({
            "metric": metric, "label": labels[metric], "dz": r.cohens_dz,
            "ci_low": r.ci95_low/sd_diff, "ci_high": r.ci95_high/sd_diff,
            "raw_difference": r.difference_zero_minus_gravity,
            "p": r.paired_t_p, "n": int(r.n),
        })
    forest = pd.DataFrame(rows)
    forest.to_csv(TABLE/"figure1_standardized_effects.csv", index=False,
                  encoding="utf-8-sig")

    fig = plt.figure(figsize=(7.2, 4.85))
    gs = fig.add_gridspec(2, 3, width_ratios=[1.48, 1, 1], hspace=.52,
                          wspace=.58, left=.165, right=.985, top=.94, bottom=.12)
    ax = fig.add_subplot(gs[:, 0])
    y = np.arange(len(forest))[::-1]
    ax.axvspan(-.5, 0, color=COL["pale"], zorder=-3)
    ax.axvline(0, color=COL["mid"], lw=.75, ls=(0, (3, 2)), zorder=0)
    for yi, r in zip(y, forest.itertuples()):
        color = COL["zero"] if r.p < .05 else COL["mid"]
        ax.plot([r.ci_low, r.ci_high], [yi, yi], color=color, lw=1.45,
                solid_capstyle="round")
        ax.scatter(r.dz, yi, s=28, color=color, edgecolor="white",
                   linewidth=.6, zorder=3)
    ax.set_yticks(y, forest.label)
    ax.set_xlim(-.46, .18)
    ax.set_xlabel("Paired standardized effect, $d_z$\n(zero gravity − gravity)")
    ax.set_title("Paired condition effects", loc="left", pad=7)
    ax.text(.02, .985, "lower in zero gravity", transform=ax.transAxes,
            va="top", color=COL["zero"], fontsize=6.3)
    ax.text(.98, .985, "higher", transform=ax.transAxes, ha="right",
            va="top", color=COL["mid"], fontsize=6.3)
    panel(ax, "a", -.22)

    ax_b = fig.add_subplot(gs[0, 1])
    paired_distribution(ax_b, summary, "accuracy", "Accuracy", rng, (.22, .96))
    ax_b.set_title("Accuracy", loc="left"); panel(ax_b, "b")
    ax_c = fig.add_subplot(gs[0, 2])
    paired_distribution(ax_c, summary, "confidence_mean", "Mean confidence (1–7)", rng, (.9, 7.1))
    ax_c.set_title("Confidence", loc="left"); panel(ax_c, "c")
    ax_d = fig.add_subplot(gs[1, 1:])
    paired_distribution(ax_d, summary, "auc", "Type-2 ROC AUC", rng, (.22, 1.01))
    ax_d.axhline(.5, color=COL["mid"], lw=.65, ls=(0, (3, 2)), alpha=.75)
    ax_d.set_title("Metacognitive sensitivity", loc="left"); panel(ax_d, "d", -.10)
    export(fig, "Figure_1_behavioral_signature")


def calibration_source(d: pd.DataFrame, rng: np.random.Generator,
                       n_boot: int = 1500) -> pd.DataFrame:
    rows = []
    ratings = np.arange(1, 8)
    for condition in ["gravity", "zero_gravity"]:
        z = d[d.condition.eq(condition)]
        matrix = z.groupby(["subject", "confidence"]).correct.mean().unstack().reindex(columns=ratings)
        values = matrix.to_numpy(float)
        for idx, rating in enumerate(ratings):
            col = values[:, idx]
            col = col[np.isfinite(col)]
            draws = rng.choice(col, (n_boot, len(col)), replace=True).mean(axis=1)
            rows.append({
                "condition": condition, "confidence": rating,
                "accuracy": col.mean(), "ci_low": np.quantile(draws, .025),
                "ci_high": np.quantile(draws, .975), "n_subjects": len(col),
                "n_trials": int((z.confidence == rating).sum()),
            })
    return pd.DataFrame(rows)


def figure2_monitoring() -> None:
    rng = np.random.default_rng(SEED+1)
    trial = pd.read_csv(ROOT/"cache"/"behavior_model_input.csv")
    trial = trial[trial.behavior_included.eq(1) & trial.confidence.notna()].copy()
    coef = pd.read_csv(TABLE/"behavior_mixed_model_coefficients.csv")
    cal = calibration_source(trial, rng)
    cal.to_csv(TABLE/"figure2_confidence_calibration.csv", index=False,
               encoding="utf-8-sig")

    # Put the six prespecified primary models on one common ratio scale.  The
    # GLMM/CLMM rows are odds ratios already; exponentiating the two log-RT LMM
    # coefficients gives directly comparable zero-gravity/gravity time ratios.
    specs = [
        ("accuracy_glmm", "conditionzero_gravity", "Accuracy", "odds ratio"),
        ("answer_rt_lmm", "conditionzero_gravity", "Decision RT", "time ratio"),
        ("confidence_rt_lmm", "conditionzero_gravity", "Confidence RT", "time ratio"),
        ("confidence_clmm", "conditionzero_gravity", "Confidence level", "odds ratio"),
        ("confidence_accuracy_coupling_glmm",
         "conditionzero_gravity:confidence_within",
         "Confidence and accuracy\ncoupling", "odds ratio"),
        ("confidence_bias_clmm", "conditionzero_gravity:correct_f1",
         "Correct/error confidence\nseparation", "odds ratio"),
    ]
    coef_rows = []
    for model, term, label, effect_type in specs:
        r = coef[(coef.model.eq(model)) & (coef.term.eq(term))].iloc[0]
        if effect_type == "time ratio":
            ratio, ci_low, ci_high = np.exp([r.estimate, r.ci_low, r.ci_high])
        else:
            ratio, ci_low, ci_high = r.odds_ratio, r.ci_low, r.ci_high
        coef_rows.append({"model": model, "term": term, "label": label,
                          "effect_type": effect_type, "ratio": ratio,
                          "ci_low": ci_low, "ci_high": ci_high,
                          "p": r.p_value,
                          "contrast": "Zero gravity / gravity"})
    key = pd.DataFrame(coef_rows)
    key.to_csv(TABLE/"figure2_key_model_coefficients.csv", index=False,
               encoding="utf-8-sig")

    fig = plt.figure(figsize=(7.2, 4.35))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.60, .70], wspace=.38,
                          left=.095, right=.985, top=.91, bottom=.18)
    ax_a = fig.add_subplot(gs[0, 0])
    for cond, color, label in [("gravity", COL["gravity"], "Gravity"),
                               ("zero_gravity", COL["zero"], "Zero gravity")]:
        z = cal[cal.condition.eq(cond)]
        ax_a.fill_between(z.confidence, z.ci_low, z.ci_high, color=color,
                          alpha=.12, linewidth=0)
        ax_a.plot(z.confidence, z.accuracy, color=color, lw=1.7,
                  marker="o", ms=3.5, label=label)
    ax_a.set(xlabel="Confidence rating", ylabel="Observed accuracy",
             xticks=np.arange(1, 8), ylim=(.25, .93))
    ax_a.legend(ncol=1, loc="upper left")
    ax_a.set_title("Empirical confidence-accuracy relation", loc="left", pad=7)
    panel(ax_a, "a", -.18)

    ax_b = fig.add_subplot(gs[0, 1])
    yy = np.arange(len(key))[::-1]
    ratio_xlim = (.38, 1.16)
    ax_b.axvspan(ratio_xlim[0], 1, color=COL["pale"], zorder=-3)
    ax_b.axvline(1, color=COL["mid"], ls=(0, (3, 2)), lw=.75)
    for yi, r in zip(yy, key.itertuples()):
        color = COL["zero"] if r.p < .05 else COL["mid"]
        ax_b.plot([r.ci_low, r.ci_high], [yi, yi], color=color, lw=1.45,
                  solid_capstyle="round")
        ax_b.scatter(r.ratio, yi, s=28, color=color, edgecolor="white",
                     linewidth=.6, zorder=3)
    ax_b.set_yticks(yy, key.label)
    ax_b.set_ylim(-.65, len(key)-.35)
    ax_b.set_xlim(*ratio_xlim)
    ax_b.set_xticks([.4, .6, .8, 1.0])
    ax_b.set_xlabel("Adjusted ratio\n(zero gravity / gravity; OR or time ratio)")
    ax_b.set_title("Six primary trial-level models", loc="left", pad=7)
    ax_b.text(.02, .985, "lower in zero gravity", transform=ax_b.transAxes,
              va="top", color=COL["zero"], fontsize=6.3)
    ax_b.text(.98, .985, "higher", transform=ax_b.transAxes, ha="right",
              va="top", color=COL["mid"], fontsize=6.3)
    panel(ax_b, "b", -.19)
    export(fig, "Figure_2_metacognitive_monitoring")


def figure3_gaze() -> None:
    rng = np.random.default_rng(SEED+2)
    eye = pd.read_csv(TABLE/"eye_metrics_subject_condition_region.csv")
    wide = eye.pivot(index="subject", columns=["condition", "region"],
                     values="fixation_time_ratio").dropna()
    position_change = (wide[("zero_gravity", "position")]
                       -wide[("gravity", "position")]) * 100
    pd.DataFrame({"subject": position_change.index,
                  "position_share_change_pp": position_change.values}).to_csv(
        TABLE/"figure3_position_share_change_subject.csv", index=False,
        encoding="utf-8-sig")

    ratio_means = eye.groupby(["condition", "region"]).fixation_time_ratio.mean().unstack()
    fold_rows = []
    for metric, label in [("total_fixation_time", "Total time"),
                          ("fixation_count", "Fixation count"),
                          ("mean_fixation_time", "Mean duration")]:
        for region in ["ball", "position"]:
            z = eye[eye.region.eq(region)].pivot(index="subject", columns="condition",
                                                 values=metric).dropna()
            log_ratio = np.log(z.zero_gravity/z.gravity)
            mean, lo, hi = bootstrap_mean_ci(log_ratio.to_numpy(), rng)
            fold_rows.append({"metric": label, "region": region,
                              "fold": np.exp(mean), "ci_low": np.exp(lo),
                              "ci_high": np.exp(hi), "n": len(log_ratio)})
    fold = pd.DataFrame(fold_rows)
    fold.to_csv(TABLE/"figure3_eye_condition_ratios.csv", index=False,
                encoding="utf-8-sig")

    direct_rows = []
    metric_specs = [
        ("total_fixation_time", "Total fixation time", "Seconds", 1),
        ("fixation_count", "Fixation count", "Fixations", 0),
        ("mean_fixation_time", "Mean fixation duration", "Seconds per fixation", 2),
    ]
    for metric, title, ylabel, digits in metric_specs:
        for region in ["ball", "position"]:
            for condition in ["gravity", "zero_gravity"]:
                values = eye.loc[(eye.region.eq(region)) &
                                 (eye.condition.eq(condition)), metric].dropna().to_numpy()
                mean, lo, hi = mean_ci(values)
                direct_rows.append({
                    "metric": metric, "metric_label": title,
                    "region": region, "condition": condition,
                    "n": len(values), "mean": mean, "sd": values.std(ddof=1),
                    "ci95_low": lo, "ci95_high": hi,
                })
    direct = pd.DataFrame(direct_rows)
    direct.to_csv(TABLE/"figure3_direct_eye_metric_summary.csv", index=False,
                  encoding="utf-8-sig")

    fig = plt.figure(figsize=(7.2, 5.35))
    gs = fig.add_gridspec(2, 3, height_ratios=[.92, 1.12], hspace=.64,
                          wspace=.43, left=.11, right=.985,
                          top=.93, bottom=.12)
    ax_a = fig.add_subplot(gs[0, :])
    for y, cond, label in [(1, "gravity", "Gravity"),
                           (0, "zero_gravity", "Zero gravity")]:
        ball = ratio_means.loc[cond, "ball"]
        position = ratio_means.loc[cond, "position"]
        ax_a.barh(y, ball, height=.36, color="#CFD7DB",
                  edgecolor="white", lw=.8)
        ax_a.barh(y, position, left=ball, height=.36, color=COL["teal_soft"],
                  edgecolor="white", lw=.8)
        ax_a.text(ball/2, y, f"Ball\n{ball*100:.1f}%", ha="center", va="center")
        ax_a.text(ball+position/2, y, f"Position\n{position*100:.1f}%",
                  ha="center", va="center")
        ax_a.text(-.025, y, label, ha="right", va="center", fontsize=7.2)
    shift = ratio_means.loc["zero_gravity", "position"]-ratio_means.loc["gravity", "position"]
    start = ratio_means.loc["gravity", "ball"]
    end = ratio_means.loc["zero_gravity", "ball"]
    band_y = .48
    ax_a.plot([end, end, start, start], [band_y-.07, band_y, band_y, band_y+.07],
              color=COL["mid"], lw=1.0, solid_capstyle="round")
    ax_a.text((start+end)/2, band_y+.055, f"Position +{shift*100:.1f} pp",
              color=COL["zero"], fontsize=7.2, fontweight="bold",
              ha="center", va="bottom",
              bbox=dict(facecolor="white", edgecolor="none", pad=.7))
    ax_a.set_xlim(-.20, 1.02); ax_a.set_ylim(-.55, 1.55)
    ax_a.set_yticks([]); ax_a.set_xticks([0, .25, .5, .75, 1], ["0", "25", "50", "75", "100"])
    ax_a.set_xlabel("Share of fixation time (%)")
    ax_a.set_title("Fixation time is reallocated from ball to position", loc="left")
    ax_a.spines["left"].set_visible(False)
    panel(ax_a, "a", -.09)

    positions = {("ball", "gravity"): -.18,
                 ("ball", "zero_gravity"): .18,
                 ("position", "gravity"): .82,
                 ("position", "zero_gravity"): 1.18}
    cond_style = {
        "gravity": (COL["gravity"], COL["gravity_soft"], "Gravity"),
        "zero_gravity": (COL["zero"], COL["zero_soft"], "Zero gravity"),
    }

    def direct_metric_panel(ax, metric, title, ylabel, digits):
        means = {}
        for region in ["ball", "position"]:
            for condition in ["gravity", "zero_gravity"]:
                vals = eye.loc[(eye.region.eq(region)) &
                               (eye.condition.eq(condition)), metric].dropna().to_numpy()
                xpos = positions[(region, condition)]
                dark, soft, _ = cond_style[condition]
                vp = ax.violinplot(vals, positions=[xpos], widths=.29,
                                   showextrema=False)
                body = vp["bodies"][0]
                body.set_facecolor(soft); body.set_edgecolor(dark)
                body.set_linewidth(.65); body.set_alpha(.68)
                q1, med, q3 = np.quantile(vals, [.25, .5, .75])
                mean, lo, hi = mean_ci(vals)
                means[(region, condition)] = mean
                ax.plot([xpos, xpos], [q1, q3], color=COL["ink"], lw=1.05,
                        solid_capstyle="round", zorder=3)
                ax.scatter(xpos, med, s=10, color="white", edgecolor=COL["ink"],
                           linewidth=.55, zorder=4)
                ax.errorbar(xpos, mean, yerr=[[mean-lo], [hi-mean]], fmt="o",
                            ms=3.7, color=dark, mfc=dark, mec="white", mew=.55,
                            capsize=1.8, lw=.85, zorder=5)
                label = f"{mean:.{digits}f}"
                offset = (-4, 6) if condition == "gravity" else (4, 6)
                align = "right" if condition == "gravity" else "left"
                # Keep the leftmost value label inside panel b rather than
                # letting it intrude into the y-axis label/margin.
                if (metric == "total_fixation_time" and region == "ball"
                        and condition == "gravity"):
                    offset = (4, 6)
                    align = "left"
                ax.annotate(label, (xpos, mean), xytext=offset,
                            textcoords="offset points",
                            ha=align,
                            va="bottom", fontsize=5.7, color=dark,
                            fontweight="semibold")
            ax.plot([positions[(region, "gravity")], positions[(region, "zero_gravity")]],
                    [means[(region, "gravity")], means[(region, "zero_gravity")]],
                    color=COL["mid"], lw=.75, alpha=.75, zorder=2)
        ax.set_xticks([0, 1], ["Ball", "Position"])
        ax.set_ylabel(ylabel)
        ax.set_title(title, loc="left")
        ax.tick_params(axis="x", length=0)

    ax_b = fig.add_subplot(gs[1, 0])
    direct_metric_panel(ax_b, *metric_specs[0]); panel(ax_b, "b", -.24)
    ax_c = fig.add_subplot(gs[1, 1])
    direct_metric_panel(ax_c, *metric_specs[1]); panel(ax_c, "c", -.24)
    ax_d = fig.add_subplot(gs[1, 2])
    direct_metric_panel(ax_d, *metric_specs[2]); panel(ax_d, "d", -.24)
    handles = [
        Line2D([0], [0], marker="o", color="none", mfc=COL["gravity"],
               label="Gravity", markersize=5),
        Line2D([0], [0], marker="o", color="none", mfc=COL["zero"],
               label="Zero gravity", markersize=5),
    ]
    fig.legend(handles=handles, ncol=2, loc="upper center",
               bbox_to_anchor=(.5, .535), columnspacing=1.4)
    export(fig, "Figure_3_gaze_reallocation")


def independent_boot_delta(low: np.ndarray, high: np.ndarray,
                           rng: np.random.Generator,
                           n_boot: int = 3500) -> tuple[float, float, float]:
    """Return low-AUC minus high-AUC mean rate and its bootstrap interval."""
    low = np.asarray(low, float); high = np.asarray(high, float)
    draws = (rng.choice(low, (n_boot, len(low)), replace=True).mean(1)
             -rng.choice(high, (n_boot, len(high)), replace=True).mean(1))
    return float(low.mean()-high.mean()), *np.quantile(draws, [.025, .975]).tolist()


def figure4_scanpaths() -> None:
    rng = np.random.default_rng(SEED+3)
    dsm = pd.read_csv(TABLE/"dsm_results_all.csv")
    duration = pd.read_csv(TABLE/"duration_dyad_subject_rates.csv")
    sig = dsm[dsm.permutation_p_fdr < .05].sort_values(["permutation_p_fdr", "dyad"]).copy()
    boot_rows = []
    for r in sig.itertuples():
        z = duration[(duration.condition.eq(r.condition)) &
                     (duration.dyad.eq(r.dyad)) & duration.spam_included]
        high = z.loc[z.auc > r.q3, "rate"].to_numpy()
        low = z.loc[z.auc < r.q1, "rate"].to_numpy()
        estimate, lo, hi = independent_boot_delta(low, high, rng)
        boot_rows.append({"condition": r.condition, "dyad": r.dyad,
                          "estimate": estimate, "ci_low": lo, "ci_high": hi,
                          "n_high": len(high), "n_low": len(low),
                          "fdr_p": r.permutation_p_fdr,
                          "delta_definition": "low_AUC_rate_minus_high_AUC_rate"})
    boot = pd.DataFrame(boot_rows)
    boot.to_csv(TABLE/"figure4_significant_dyad_bootstrap.csv", index=False,
                encoding="utf-8-sig")

    signature_dyads = sig.dyad.tolist()
    signature = (duration[(duration.condition.eq("zero_gravity"))
                          & duration.spam_included
                          & duration.dyad.isin(signature_dyads)]
                 .groupby(["subject", "auc"], as_index=False).rate.sum()
                 .rename(columns={"rate": "signature_rate"})
                 .dropna(subset=["auc", "signature_rate"]))
    signature["signature_rate_percent"] = signature.signature_rate*100
    signature.to_csv(TABLE/"figure4_transition_signature_subject.csv", index=False,
                     encoding="utf-8-sig")
    fit = stats.linregress(signature.auc, signature.signature_rate_percent)
    pd.DataFrame([{
        "n": len(signature), "slope_pp_per_auc_unit": fit.slope,
        "intercept": fit.intercept, "pearson_r": fit.rvalue,
        "r_squared": fit.rvalue**2, "p": fit.pvalue,
        "signature_definition": "sum_of_three_FDR_significant_zero_gravity_duration_dyad_rates",
    }]).to_csv(TABLE/"figure4_transition_signature_model.csv", index=False,
               encoding="utf-8-sig")

    matrix_rows = dsm[(dsm.representation.eq("duration"))
                      & dsm.condition.eq("zero_gravity")].copy()
    matrix_rows["delta_pp"] = -matrix_rows.high_minus_low*100
    matrix_rows[["source", "destination"]] = matrix_rows.dyad.str.split("->", expand=True)
    state_order = ["ball_MED", "ball_LONG", "position_MED", "position_LONG"]
    delta_matrix = (matrix_rows.pivot(index="source", columns="destination",
                                      values="delta_pp")
                    .reindex(index=state_order, columns=state_order))
    fdr_matrix = (matrix_rows.pivot(index="source", columns="destination",
                                    values="permutation_p_fdr")
                  .reindex(index=state_order, columns=state_order))
    matrix_rows.to_csv(TABLE/"figure4_zero_gravity_transition_matrix.csv", index=False,
                       encoding="utf-8-sig")

    fig = plt.figure(figsize=(7.2, 5.25))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.03, 1.15], height_ratios=[1, 1.05],
                          hspace=.54, wspace=.48, left=.11, right=.985,
                          top=.92, bottom=.11)
    ax_a = fig.add_subplot(gs[:, 0])
    limit = float(np.nanmax(np.abs(delta_matrix.values)))
    cmap = LinearSegmentedColormap.from_list(
        "scanpath_delta", [COL["gravity"], "#F7F4EE", COL["zero"]])
    im = ax_a.imshow(delta_matrix.values, cmap=cmap, vmin=-limit, vmax=limit,
                     aspect="equal")
    state_labels = ["Ball\nMedium", "Ball\nLong", "Position\nMedium", "Position\nLong"]
    ax_a.set_xticks(range(4), state_labels, rotation=0, ha="center")
    ax_a.set_yticks(range(4), state_labels)
    ax_a.set_xlabel("Destination state")
    ax_a.set_ylabel("Source state")
    for i in range(4):
        for j in range(4):
            value = delta_matrix.iloc[i, j]
            significant = fdr_matrix.iloc[i, j] < .05
            ax_a.text(j, i, f"{value:+.2f}" + ("*" if significant else ""),
                      ha="center", va="center", fontsize=6.5,
                      fontweight="bold" if significant else "normal",
                      color="white" if abs(value) > limit*.60 else COL["ink"])
            if significant:
                ax_a.add_patch(Rectangle((j-.48, i-.48), .96, .96,
                                         fill=False, edgecolor=COL["ink"],
                                         linewidth=1.25))
    cb = fig.colorbar(im, ax=ax_a, orientation="horizontal", fraction=.065,
                      pad=.18, aspect=24)
    cb.set_label("Δ = low-AUC rate − high-AUC rate (percentage points)")
    cb.ax.tick_params(labelsize=6.1)
    ax_a.text(1.02, 1.00, "* FDR < .05", transform=ax_a.transAxes,
              ha="left", va="top", fontsize=6.3,
              color=COL["ink"], fontweight="bold",
              bbox=dict(facecolor="white", edgecolor="none", pad=.5))
    ax_a.set_title("Zero-gravity duration-transition matrix", loc="left")
    panel(ax_a, "a", -.16)

    ax_b = fig.add_subplot(gs[0, 1])
    x = signature.auc.to_numpy(float)
    y = signature.signature_rate_percent.to_numpy(float)
    ax_b.scatter(x, y, s=8, color=COL["violet"], alpha=.30,
                 edgecolors="none", rasterized=True)
    xx = np.linspace(x.min(), x.max(), 160)
    yy = fit.intercept + fit.slope*xx
    residual = y-(fit.intercept+fit.slope*x)
    s_err = np.sqrt(np.sum(residual**2)/(len(x)-2))
    sxx = np.sum((x-x.mean())**2)
    ci = stats.t.ppf(.975, len(x)-2)*s_err*np.sqrt(1/len(x)+(xx-x.mean())**2/sxx)
    ax_b.fill_between(xx, yy-ci, yy+ci, color=COL["violet"], alpha=.14, lw=0)
    ax_b.plot(xx, yy, color=COL["violet"], lw=1.55)
    ax_b.text(.03, .96, f"r = {fit.rvalue:.2f}, {p_text(fit.pvalue)}, n = {len(x)}",
              transform=ax_b.transAxes, ha="left", va="top",
              fontsize=6.5, color=COL["violet"], fontweight="semibold")
    ax_b.set_xlabel("Type-2 ROC AUC")
    ax_b.set_ylabel("Transition-signature rate (%)")
    ax_b.set_title("Continuous AUC–signature association", loc="left")
    panel(ax_b, "b", -.23)

    ax_c = fig.add_subplot(gs[1, 1])
    ax_c.set_xlim(0, 1); ax_c.set_ylim(0, 1); ax_c.axis("off")
    nodes = {"Ball\n(Med)": (.18, .50), "Position\n(Med)": (.81, .72),
             "Position\n(Long)": (.81, .26)}
    for name, (x, y) in nodes.items():
        fill = COL["gravity_soft"] if name.startswith("Ball") else COL["zero_soft"]
        ax_c.scatter(x, y, s=1500, color=fill, edgecolor="white", linewidth=1.2, zorder=3)
        ax_c.text(x, y, name, ha="center", va="center", fontsize=7.0,
                  color=COL["ink"], zorder=4)

    def arrow(start, end, rad, width):
        x1, y1 = nodes[start]; x2, y2 = nodes[end]
        patch = FancyArrowPatch((x1, y1), (x2, y2),
                                connectionstyle=f"arc3,rad={rad}",
                                arrowstyle="-|>", mutation_scale=11,
                                color=COL["ink"], lw=width, alpha=.82,
                                shrinkA=17, shrinkB=17, zorder=2)
        ax_c.add_patch(patch)

    arrow("Ball\n(Med)", "Position\n(Med)", .20, 1.55)
    arrow("Position\n(Med)", "Ball\n(Med)", .20, 1.62)
    arrow("Ball\n(Med)", "Position\n(Long)", -.08, 1.48)
    label_box = dict(facecolor="white", edgecolor=COL["light"],
                     linewidth=.45, boxstyle="round,pad=.18")
    delta = dict(zip(boot.dyad, boot.estimate*100))
    ax_c.text(.49, .82, f"Ball → Position (Med)\nΔ = {delta['ball_MED->position_MED']:+.2f} pp",
              ha="center", va="center", fontsize=5.8, color=COL["ink"], bbox=label_box)
    ax_c.text(.48, .61, f"Position (Med) → Ball\nΔ = {delta['position_MED->ball_MED']:+.2f} pp",
              ha="center", va="center", fontsize=5.8, color=COL["ink"], bbox=label_box)
    ax_c.text(.50, .27, f"Ball → Position (Long)\nΔ = {delta['ball_MED->position_LONG']:+.2f} pp",
              ha="center", va="center", fontsize=5.8, color=COL["ink"], bbox=label_box)
    ax_c.text(.5, .02, "Δ = low-AUC rate − high-AUC rate; positive values indicate\nmore frequent transitions in the low-AUC group.",
              ha="center", va="bottom", fontsize=5.5, color=COL["zero"],
              fontweight="bold")
    ax_c.set_title("Directed transition signature", loc="left", pad=2)
    panel(ax_c, "c", -.12, 1.00)
    export(fig, "Figure_4_scanpath_organization")


def figure_s1_task_structure() -> None:
    d = pd.read_csv(ROOT/"cache"/"behavior_model_input.csv")
    d = d[d.behavior_included.eq(1)].copy()
    d["within_condition_trial"] = d.groupby(["subject", "condition"])["trial_c"].rank(method="first")
    d["trial_bin"] = pd.cut(d.within_condition_trial, bins=np.arange(0, 37, 6),
                            include_lowest=True, labels=np.arange(1, 7))

    velocity_subject = d.groupby(["subject", "condition", "velocity"], observed=True).correct.mean().reset_index()
    velocity_rows = []
    for (cond, velocity), z in velocity_subject.groupby(["condition", "velocity"], observed=True):
        mean, lo, hi = mean_ci(z.correct.to_numpy())
        velocity_rows.append({"condition": cond, "velocity": velocity,
                              "accuracy": mean, "ci_low": lo, "ci_high": hi,
                              "n": z.subject.nunique()})
    velocity = pd.DataFrame(velocity_rows)

    size_subject = d.groupby(["subject", "condition", "size_pair"], observed=True).correct.mean().reset_index()
    wide = size_subject.pivot(index=["subject", "size_pair"], columns="condition", values="correct").dropna()
    wide["difference"] = wide.zero_gravity-wide.gravity
    size_diff = wide.groupby("size_pair").difference.mean().reset_index()
    size_diff[["left_size", "right_size"]] = size_diff.size_pair.str.split("_", expand=True).astype(float)
    matrix = size_diff.pivot(index="left_size", columns="right_size", values="difference").sort_index(ascending=False)

    progress_subject = d.groupby(["subject", "condition", "trial_bin"], observed=True).correct.mean().reset_index()
    progress_rows = []
    for (cond, trial_bin), z in progress_subject.groupby(["condition", "trial_bin"], observed=True):
        mean, lo, hi = mean_ci(z.correct.to_numpy())
        progress_rows.append({"condition": cond, "trial_bin": int(trial_bin),
                              "accuracy": mean, "ci_low": lo, "ci_high": hi,
                              "n": z.subject.nunique()})
    progress = pd.DataFrame(progress_rows)

    fig = plt.figure(figsize=(7.2, 5.05))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.02], width_ratios=[1.05, 1],
                          hspace=.54, wspace=.38, left=.10, right=.985,
                          top=.92, bottom=.11)
    ax_a = fig.add_subplot(gs[0, 0])
    for cond, color, label in [("gravity", COL["gravity"], "Gravity"),
                               ("zero_gravity", COL["zero"], "Zero gravity")]:
        z = velocity[velocity.condition.eq(cond)]
        ax_a.fill_between(z.velocity, z.ci_low, z.ci_high, color=color, alpha=.12, lw=0)
        ax_a.plot(z.velocity, z.accuracy, marker="o", ms=3.3, lw=1.55,
                  color=color, label=label)
    ax_a.set(xlabel="Vertical speed level", ylabel="Accuracy", ylim=(.55, .83))
    ax_a.legend(ncol=2, loc="lower left")
    ax_a.set_title("Condition pattern across speed levels", loc="left")
    panel(ax_a, "a")

    ax_b = fig.add_subplot(gs[0, 1])
    limit = max(abs(np.nanmin(matrix.values)), abs(np.nanmax(matrix.values)))
    cmap = LinearSegmentedColormap.from_list("context_diverging",
                                             [COL["zero"], "#F2EFE8", COL["gravity"]])
    ax_b.imshow(matrix.values, cmap=cmap, vmin=-limit, vmax=limit, aspect="auto")
    ax_b.set_xticks(range(len(matrix.columns)), [f"{x:.1f}" for x in matrix.columns])
    ax_b.set_yticks(range(len(matrix.index)), [f"{x:.1f}" for x in matrix.index])
    ax_b.set(xlabel="Right-ball size", ylabel="Left-ball size")
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix.iloc[i, j]
            ax_b.text(j, i, f"{value:+.02f}", ha="center", va="center",
                      fontsize=6.6, color="white" if abs(value) > limit*.58 else COL["ink"])
    ax_b.set_title("Accuracy difference by size pairing", loc="left", pad=14)
    ax_b.text(.98, 1.01, "zero gravity − gravity", transform=ax_b.transAxes,
              ha="right", va="bottom", fontsize=6.2, color=COL["ink"],
              fontweight="bold",
              bbox=dict(facecolor="white", edgecolor="none", pad=.4))
    panel(ax_b, "b")

    ax_c = fig.add_subplot(gs[1, :])
    for cond, color, label in [("gravity", COL["gravity"], "Gravity"),
                               ("zero_gravity", COL["zero"], "Zero gravity")]:
        z = progress[progress.condition.eq(cond)]
        ax_c.fill_between(z.trial_bin, z.ci_low, z.ci_high, color=color, alpha=.12, lw=0)
        ax_c.plot(z.trial_bin, z.accuracy, marker="o", ms=3.5, lw=1.6,
                  color=color, label=label)
    ax_c.set(xlabel="Six-trial bin within condition", ylabel="Accuracy",
             xticks=np.arange(1, 7), ylim=(.58, .75))
    ax_c.set_title("Within-condition accuracy over trials", loc="left")
    ax_c.legend(ncol=2, loc="upper right")
    panel(ax_c, "c", -.075)

    velocity.to_csv(TABLE/"figureS1_velocity_accuracy.csv", index=False, encoding="utf-8-sig")
    size_diff.to_csv(TABLE/"figureS1_size_pair_accuracy_difference.csv", index=False, encoding="utf-8-sig")
    progress.to_csv(TABLE/"figureS1_trial_progress_accuracy.csv", index=False, encoding="utf-8-sig")
    export(fig, "Figure_S1_task_structure_and_time_course")


def draw_flow(ax: plt.Axes, flow: pd.DataFrame, paired_auc_n: int,
              behavior_eye_overlap: int) -> None:
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    values = dict(zip(flow.stage, flow.n))
    boxes = [
        (.18, .83, .64, .12, "Matched files", values["Matched behavior-eye files"], COL["ink"]),
        (.02, .56, .29, .14, "Behavior", values["Behavior QC included"], COL["gravity"]),
        (.355, .56, .29, .14, "Eye (50%)", values["Eye QC included (50%)"], COL["teal"]),
        (.69, .56, .29, .14, "Sequence", values["SPAM/DSM M-2SD included"], COL["gold"]),
        (.02, .30, .29, .14, "AUC eligible", values["AUC QC included"], COL["violet"]),
        (.02, .06, .29, .14, "Paired finite AUC", paired_auc_n, COL["violet"]),
    ]
    for x, y, width, height, label, count, color in boxes:
        ax.add_patch(Rectangle((x, y), width, height, facecolor="white",
                               edgecolor=color, lw=1.15))
        ax.text(x+.016, y+height*.58, label, ha="left", va="center",
                fontsize=5.1, color=COL["ink"])
        ax.text(x+width-.016, y+height*.58, str(int(count)), ha="right",
                va="center", fontsize=6.7, fontweight="bold", color=color)
    for start, end in [((.38, .83), (.165, .70)), ((.50, .83), (.50, .70)),
                       ((.62, .83), (.835, .70)), ((.165, .56), (.165, .44)),
                       ((.165, .30), (.165, .20))]:
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=8,
                                     lw=.75, color=COL["mid"]))
    ax.plot([.31, .355], [.625, .625], color=COL["mid"], lw=.65,
            ls=(0, (1.5, 1.3)))
    ax.text(.3325, .515, f"overlap\n{behavior_eye_overlap}", ha="center",
            va="center", fontsize=4.6, color=COL["mid"], linespacing=.95)
    ax.text(.65, .17, "Parallel, endpoint-specific\nquality gates",
            ha="center", va="center", fontsize=5.4, color=COL["mid"],
            linespacing=1.15)


def figure_s2_qc() -> None:
    flow = pd.read_csv(TABLE/"sample_flow.csv")
    eye = pd.read_csv(TABLE/"eye_qc_by_condition.csv").drop_duplicates("subject")
    behavior = pd.read_csv(TABLE/"behavior_qc_by_condition.csv").drop_duplicates("subject")
    summary = pd.read_csv(TABLE/"participant_condition_summary.csv")
    dyad = pd.read_csv(TABLE/"spam_dsm_dyad_qc.csv")
    loo = pd.read_csv(TABLE/"leave_one_subject_out_stability.csv")
    paired_auc_n = int(summary.pivot(index="subject", columns="condition",
                                     values="auc").notna().all(axis=1).sum())
    behavior_subjects = set(behavior.loc[behavior.behavior_included, "subject"])
    eye_subjects = set(eye.loc[eye.eye_included, "subject"])
    behavior_eye_overlap = len(behavior_subjects & eye_subjects)

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.1))
    fig.subplots_adjust(left=.10, right=.985, top=.92, bottom=.11,
                        hspace=.56, wspace=.42)
    ax_a, ax_b, ax_c, ax_d = axes.ravel()
    draw_flow(ax_a, flow, paired_auc_n, behavior_eye_overlap)
    ax_a.set_title("Analysis-specific sample flow", loc="left")
    panel(ax_a, "a", -.10)

    ax_b.hist(eye.min_coverage, bins=np.linspace(0, 1, 31),
              color=COL["teal_soft"], edgecolor="white", linewidth=.35)
    ax_b.axvline(.5, color=COL["zero"], ls=(0, (3, 2)), lw=1,
                 label="Primary threshold")
    ax_b.set(xlabel="Minimum condition non-gap coverage", ylabel="Participants")
    ax_b.legend(loc="upper left")
    ax_b.set_title("Eye-data coverage", loc="left")
    panel(ax_b, "b")

    ax_c.hist(dyad.dyad_total, bins=32, color="#D9C18A", edgecolor="white",
              linewidth=.35)
    threshold = dyad.m_minus_2sd_threshold.iloc[0]
    ax_c.axvline(threshold, color=COL["zero"], ls=(0, (3, 2)), lw=1,
                 label=f"M − 2SD = {threshold:.1f}")
    ax_c.set(xlabel="Total usable dyads", ylabel="Participants")
    ax_c.legend(loc="upper right")
    ax_c.set_title("Sequence-data threshold", loc="left")
    panel(ax_c, "c")

    labels = {"accuracy": "Accuracy", "answer_rt_median": "Decision RT",
              "confidence_mean": "Confidence", "auc": "AUC"}
    z = loo[loo.metric.isin(labels)].copy()
    z["ratio_a"] = z.loo_min/z.full_difference
    z["ratio_b"] = z.loo_max/z.full_difference
    z["ratio_low"] = z[["ratio_a", "ratio_b"]].min(axis=1)
    z["ratio_high"] = z[["ratio_a", "ratio_b"]].max(axis=1)
    yy = np.arange(len(z))[::-1]
    ax_d.axvline(1, color=COL["mid"], ls=(0, (3, 2)), lw=.75)
    for yi, r in zip(yy, z.itertuples()):
        ax_d.plot([r.ratio_low, r.ratio_high], [yi, yi], color=COL["violet"], lw=2)
        ax_d.scatter(1, yi, s=27, color=COL["violet"], edgecolor="white",
                     linewidth=.55, zorder=3)
    ax_d.set_yticks(yy, [labels[x] for x in z.metric])
    ax_d.set_xlabel("Leave-one-out estimate / full estimate")
    ax_d.set_title("Leave-one-participant-out stability", loc="left")
    panel(ax_d, "d", -.18)
    z.to_csv(TABLE/"figureS2_leave_one_out_stability.csv", index=False,
             encoding="utf-8-sig")
    export(fig, "Figure_S2_quality_control_and_robustness")


def generate_all() -> None:
    setup_style()
    figure1_behavior()
    figure2_monitoring()
    figure3_gaze()
    figure4_scanpaths()
    figure_s1_task_structure()
    figure_s2_qc()


if __name__ == "__main__":
    generate_all()
