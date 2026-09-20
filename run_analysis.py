#!/usr/bin/env python3
"""End-to-end, OSF-ready analysis pipeline for the PB&R revision dataset.

Run from this folder with ``python run_analysis.py``. The script discovers
participants from matched CSV/XLSX stems, applies the prespecified filters,
caches the expensive eye-event extraction, fits mixed models through the
bundled R script, creates publication figures, and writes a concise DOCX report.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
import warnings
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm
from scipy import stats
from sklearn.metrics import roc_auc_score
from statsmodels.formula.api import ols
from statsmodels.stats.multitest import multipletests

warnings.filterwarnings("ignore", category=RuntimeWarning)

ROOT = Path(__file__).resolve().parent
BEHAVIOR_DIR = ROOT / "behavioral_data"
EYE_DIR = ROOT / "eye_tracking_data"
CACHE_DIR = ROOT / "cache"
OUT_DIR = ROOT / "outputs"
TABLE_DIR = OUT_DIR / "tables"
FIG_DIR = OUT_DIR / "figures"
LOG_DIR = OUT_DIR / "logs"
REPORT_DIR = OUT_DIR / "report"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
SEED = int(CONFIG["random_seed"])
RNG = np.random.default_rng(SEED)
CONDITIONS = CONFIG["conditions"]
OKABE_ITO = {"gravity": "#0072B2", "zero_gravity": "#D55E00", "ball": "#009E73", "position": "#CC79A7"}


def ensure_dirs() -> None:
    for p in (CACHE_DIR, TABLE_DIR, FIG_DIR, LOG_DIR, REPORT_DIR):
        p.mkdir(parents=True, exist_ok=True)


def write_log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    with (LOG_DIR / "pipeline.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def save_csv(df: pd.DataFrame, name: str) -> Path:
    path = TABLE_DIR / name
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def paired_ci(x: np.ndarray, y: np.ndarray, confidence: float = 0.95) -> tuple[float, float, float]:
    d = np.asarray(y, float) - np.asarray(x, float)
    d = d[np.isfinite(d)]
    mean = float(np.mean(d))
    if len(d) < 2:
        return mean, np.nan, np.nan
    se = stats.sem(d)
    q = stats.t.ppf((1 + confidence) / 2, len(d) - 1)
    return mean, mean - q * se, mean + q * se


def paired_effects(wide: pd.DataFrame, variable: str) -> dict:
    x = wide[f"{variable}_gravity"].to_numpy(float)
    y = wide[f"{variable}_zero_gravity"].to_numpy(float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    d = y - x
    t = stats.ttest_rel(y, x)
    try:
        w = stats.wilcoxon(y, x, zero_method="wilcox", alternative="two-sided")
        w_stat, w_p = float(w.statistic), float(w.pvalue)
    except ValueError:
        w_stat, w_p = np.nan, np.nan
    mean_diff, lo, hi = paired_ci(x, y)
    dz = float(np.mean(d) / np.std(d, ddof=1)) if np.std(d, ddof=1) > 0 else np.nan
    positive = np.sum(d > 0); negative = np.sum(d < 0)
    rank_biserial = (positive - negative) / max(1, positive + negative)
    return {
        "metric": variable, "n": len(d),
        "gravity_mean": np.mean(x), "gravity_sd": np.std(x, ddof=1),
        "zero_gravity_mean": np.mean(y), "zero_gravity_sd": np.std(y, ddof=1),
        "difference_zero_minus_gravity": mean_diff, "ci95_low": lo, "ci95_high": hi,
        "paired_t": t.statistic, "paired_t_p": t.pvalue, "cohens_dz": dz,
        "wilcoxon_w": w_stat, "wilcoxon_p": w_p, "rank_biserial_sign": rank_biserial,
    }


def type2_auc(g: pd.DataFrame) -> float:
    if g["correct"].nunique() < 2 or g["confidence"].nunique() < 2:
        return np.nan
    return float(roc_auc_score(g["correct"], g["confidence"]))


def discover_participants() -> tuple[list[str], pd.DataFrame]:
    b = {p.stem for p in BEHAVIOR_DIR.glob("*.csv")}
    e = {p.stem for p in EYE_DIR.glob("*.xlsx")}
    matched = sorted(b & e)
    audit = pd.DataFrame({
        "category": ["behavior_files", "eye_files", "matched_participants", "behavior_without_eye", "eye_without_behavior"],
        "count": [len(b), len(e), len(matched), len(b-e), len(e-b)],
        "identifiers": ["", "", "", ";".join(sorted(b-e)), ";".join(sorted(e-b))]
    })
    return matched, audit


def load_behavior(participants: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = []
    file_audit = []
    for subject in participants:
        path = BEHAVIOR_DIR / f"{subject}.csv"
        try:
            d = pd.read_csv(path)
        except Exception as exc:
            file_audit.append({"subject": subject, "status": "read_error", "detail": str(exc)})
            continue
        missing = sorted(set(["TrialNumber","Gravity","Target","ExpectedAnswer","LeftVelY","LeftScale","RightScale","UserAnswer","AnswerTime","ConfidenceRating","ConfidenceTime"]) - set(d.columns))
        if missing:
            file_audit.append({"subject": subject, "status": "missing_columns", "detail": ";".join(missing)})
            continue
        d = d.copy()
        d["subject"] = subject
        d["row_order"] = np.arange(1, len(d) + 1)
        d["condition"] = np.where(pd.to_numeric(d["Gravity"], errors="coerce").eq(1), "gravity", "zero_gravity")
        d["valid_response"] = pd.to_numeric(d["UserAnswer"], errors="coerce").isin([0, 1])
        d["correct"] = np.where(d["valid_response"], (d["UserAnswer"] == d["ExpectedAnswer"]).astype(int), np.nan)
        d["confidence_valid"] = pd.to_numeric(d["ConfidenceRating"], errors="coerce").between(1, 7) & d["valid_response"]
        d["answer_rt_valid"] = pd.to_numeric(d["AnswerTime"], errors="coerce").gt(0) & d["valid_response"]
        d["confidence_rt_valid"] = pd.to_numeric(d["ConfidenceTime"], errors="coerce").gt(0) & d["confidence_valid"]
        d["confidence"] = pd.to_numeric(d["ConfidenceRating"], errors="coerce").where(d["confidence_valid"])
        d["answer_rt"] = pd.to_numeric(d["AnswerTime"], errors="coerce").where(d["answer_rt_valid"])
        d["confidence_rt"] = pd.to_numeric(d["ConfidenceTime"], errors="coerce").where(d["confidence_rt_valid"])
        d["expected_answer"] = pd.to_numeric(d["ExpectedAnswer"], errors="coerce")
        d["velocity"] = pd.to_numeric(d["LeftVelY"], errors="coerce")
        d["left_scale"] = pd.to_numeric(d["LeftScale"], errors="coerce")
        d["right_scale"] = pd.to_numeric(d["RightScale"], errors="coerce")
        d["size_pair"] = d["left_scale"].map(lambda v:f"{v:.1f}") + "_" + d["right_scale"].map(lambda v:f"{v:.1f}")
        d["target"] = pd.to_numeric(d["Target"], errors="coerce")
        d["trial_c"] = (d["row_order"] - d["row_order"].mean()) / d["row_order"].std(ddof=0)
        d["trial_c2"] = d["trial_c"] ** 2
        d["log_answer_rt"] = np.log(d["answer_rt"])
        d["log_confidence_rt"] = np.log(d["confidence_rt"])
        d["occlusion_hidden"] = pd.to_numeric(d.get("OcclusionHiddenDurationMs"), errors="coerce")
        d["occlusion_start"] = pd.to_numeric(d.get("OcclusionStartTimeMs"), errors="coerce")
        d["option_distance"] = np.sqrt((pd.to_numeric(d.get("TrueLandingX"),errors="coerce")-pd.to_numeric(d.get("FalseLandingX"),errors="coerce"))**2 +
                                       (pd.to_numeric(d.get("TrueLandingY"),errors="coerce")-pd.to_numeric(d.get("FalseLandingY"),errors="coerce"))**2)
        rows.append(d)
        file_audit.append({"subject":subject,"status":"ok","detail":f"rows={len(d)}"})
    trial = pd.concat(rows, ignore_index=True)

    qc_rows = []
    for (subject, cond), g in trial.groupby(["subject","condition"], observed=True):
        valid = g[g["valid_response"]]
        conf = g[g["confidence_valid"]]
        qc_rows.append({"subject":subject,"condition":cond,"n_rows":len(g),"n_valid":len(valid),
                        "n_correct":int(valid["correct"].sum()),"n_error":int((1-valid["correct"]).sum()),
                        "n_confidence":len(conf),"n_conf_correct":int(conf["correct"].sum()),"n_conf_error":int((1-conf["correct"]).sum())})
    qc = pd.DataFrame(qc_rows)
    bq = CONFIG["behavior_qc"]; aq = CONFIG["auc_qc"]
    qc["condition_behavior_pass"] = (qc.n_valid >= bq["minimum_valid_trials_per_condition"]) & (qc.n_correct >= bq["minimum_correct_trials_per_condition"]) & (qc.n_error >= bq["minimum_error_trials_per_condition"])
    qc["condition_auc_pass"] = (qc.n_confidence >= aq["minimum_confidence_trials_per_condition"]) & (qc.n_conf_correct >= aq["minimum_correct_trials_per_condition"]) & (qc.n_conf_error >= aq["minimum_error_trials_per_condition"])
    subj_qc = qc.groupby("subject").agg(behavior_included=("condition_behavior_pass","all"), auc_included=("condition_auc_pass","all"), conditions=("condition","nunique")).reset_index()
    subj_qc["behavior_included"] &= subj_qc["conditions"].eq(2)
    subj_qc["auc_included"] &= subj_qc["conditions"].eq(2) & subj_qc["behavior_included"]
    trial = trial.merge(subj_qc[["subject","behavior_included","auc_included"]], on="subject", how="left")
    trial["behavior_included"] = trial["behavior_included"].astype(int)
    trial["auc_included"] = trial["auc_included"].astype(int)
    trial["confidence_between"] = trial.groupby("subject")["confidence"].transform("mean")
    trial["confidence_within"] = trial["confidence"] - trial["confidence_between"]
    trial["occlusion_hidden_c"] = (trial["occlusion_hidden"] - trial["occlusion_hidden"].mean()) / trial["occlusion_hidden"].std(ddof=0)
    return trial, qc.merge(subj_qc,on="subject",how="left"), pd.DataFrame(file_audit)


def summarize_behavior(trial: pd.DataFrame, qc: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    core = trial[trial.behavior_included.eq(1)].copy()
    summaries=[]
    for (subject,condition),g in core.groupby(["subject","condition"],observed=True):
        v=g[g.valid_response]; c=g[g.confidence_valid]
        summaries.append({"subject":subject,"condition":condition,"accuracy":v.correct.mean(),
                          "answer_rt_median":v.answer_rt.median(),"answer_rt_mean":v.answer_rt.mean(),
                          "confidence_mean":c.confidence.mean(),"confidence_rt_median":c.confidence_rt.median(),
                          "auc":type2_auc(c) if bool(g.auc_included.iloc[0]) else np.nan,
                          "n_valid":len(v),"n_confidence":len(c)})
    summary=pd.DataFrame(summaries)
    wide=summary.pivot(index="subject",columns="condition",values=["accuracy","answer_rt_median","answer_rt_mean","confidence_mean","confidence_rt_median","auc"]) 
    wide.columns=[f"{a}_{b}" for a,b in wide.columns]
    wide=wide.reset_index()
    effects=pd.DataFrame([paired_effects(wide,m) for m in ["accuracy","answer_rt_median","answer_rt_mean","confidence_mean","confidence_rt_median","auc"]])
    effects["p_bh"] = multipletests(effects["paired_t_p"].fillna(1),method="fdr_bh")[1]
    return summary, effects


AOI_ALIAS = {"lift_ball":"left_ball","left_ball":"left_ball","right_ball":"right_ball","up_point":"up_point","down_point":"down_point"}
AOI_REGION = {"left_ball":"ball","right_ball":"ball","up_point":"position","down_point":"position"}


def extract_eye_file(subject: str, path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    usecols=["Time(s)","Eye State","AOI","in_trial","TOI"]
    d=pd.read_excel(path,sheet_name="MainData",usecols=usecols,engine="calamine")
    d.columns=[str(c).strip() for c in d.columns]
    d["time"]=pd.to_numeric(d["Time(s)"],errors="coerce")
    d["condition"]=d["TOI"].astype("string").str.strip()
    d=d[d.condition.isin(CONDITIONS) & d.time.notna()].copy()
    if d.empty:
        return pd.DataFrame(),pd.DataFrame([{"subject":subject,"condition":"missing","n_samples":0}])
    d=d.sort_values("time",kind="stable").reset_index(drop=True)
    dt=np.diff(d.time.to_numpy(float)); dt=dt[(dt>0)&(dt<0.2)]
    sample_dt=float(np.median(dt)) if len(dt) else 1/60
    max_gap=sample_dt*float(CONFIG["eye_qc"]["maximum_gap_multiplier"])
    state=d["Eye State"].astype("string").str.strip()
    d["non_gap"]=state.ne("Gap") & state.notna()
    d["fixation"]=state.isin(["注视","Fixation","fixation"])
    d["aoi_clean"]=d["AOI"].astype("string").str.strip().map(AOI_ALIAS)
    d["region"]=d["aoi_clean"].map(AOI_REGION)
    qc=[]
    for cond,g in d.groupby("condition",observed=True):
        qc.append({"subject":subject,"condition":cond,"n_samples":len(g),"non_gap_samples":int(g.non_gap.sum()),
                   "non_gap_coverage":float(g.non_gap.mean()),"recognized_aoi_samples":int(g.aoi_clean.notna().sum()),"sample_interval_s":sample_dt})

    events=[]; current=None
    for row in d[["time","condition","fixation","aoi_clean","region"]].itertuples(index=False):
        valid=bool(row.fixation) and pd.notna(row.aoi_clean)
        if not valid:
            if current is not None: events.append(current); current=None
            continue
        if current is None or row.condition!=current["condition"] or row.aoi_clean!=current["aoi"] or row.time-current["end_time"]>max_gap:
            if current is not None: events.append(current)
            current={"subject":subject,"condition":row.condition,"aoi":row.aoi_clean,"region":row.region,
                     "start_time":float(row.time),"end_time":float(row.time),"n_samples":1,"sample_dt":sample_dt}
        else:
            current["end_time"]=float(row.time); current["n_samples"]+=1
    if current is not None: events.append(current)
    ev=pd.DataFrame(events)
    if not ev.empty:
        ev["duration_s"]=(ev.end_time-ev.start_time+ev.sample_dt).clip(lower=ev.sample_dt)
        ev["event_order"]=np.arange(len(ev))
    q=pd.DataFrame(qc)
    if not ev.empty:
        counts=ev.groupby("condition").size().rename("fixation_events").reset_index()
        q=q.merge(counts,on="condition",how="left")
    if "fixation_events" not in q.columns:
        q["fixation_events"] = 0
    else:
        q["fixation_events"] = q["fixation_events"].fillna(0)
    q["fixation_events"] = q["fixation_events"].astype(int)
    return ev,q


def process_eye(participants: list[str], rebuild: bool=False) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    event_cache=CACHE_DIR/"eye_events.csv.gz"; qc_cache=CACHE_DIR/"eye_qc.csv"
    if event_cache.exists() and qc_cache.exists() and not rebuild:
        write_log("Loading cached eye events")
        ev=pd.read_csv(event_cache,compression="gzip",dtype={"subject":str})
        qc=pd.read_csv(qc_cache,dtype={"subject":str})
    else:
        all_ev=[]; all_qc=[]; errors=[]
        for i,subject in enumerate(participants,1):
            try:
                ev,q=extract_eye_file(subject,EYE_DIR/f"{subject}.xlsx")
                all_ev.append(ev); all_qc.append(q)
            except Exception as exc:
                errors.append({"subject":subject,"error":f"{type(exc).__name__}: {exc}"})
            if i==1 or i%25==0 or i==len(participants): write_log(f"Eye extraction {i}/{len(participants)}")
        ev=pd.concat(all_ev,ignore_index=True) if all_ev else pd.DataFrame()
        qc=pd.concat(all_qc,ignore_index=True) if all_qc else pd.DataFrame()
        ev.to_csv(event_cache,index=False,compression="gzip")
        qc.to_csv(qc_cache,index=False,encoding="utf-8-sig")
        save_csv(pd.DataFrame(errors),"eye_file_errors.csv")
    eq=CONFIG["eye_qc"]
    qc["condition_primary_pass"]=(qc.non_gap_coverage>=eq["primary_non_gap_coverage"])&(qc.fixation_events>=eq["minimum_fixation_events_per_condition"])
    for threshold in eq["sensitivity_non_gap_coverage"]:
        qc[f"condition_pass_{int(threshold*100)}"]=(qc.non_gap_coverage>=threshold)&(qc.fixation_events>=eq["minimum_fixation_events_per_condition"])
    sq=qc.groupby("subject").agg(eye_included=("condition_primary_pass","all"),conditions=("condition","nunique"),
                                  min_coverage=("non_gap_coverage","min"),total_events=("fixation_events","sum")).reset_index()
    sq["eye_included"] &= sq.conditions.eq(2)
    for threshold in eq["sensitivity_non_gap_coverage"]:
        col=f"condition_pass_{int(threshold*100)}"
        flag=f"eye_included_{int(threshold*100)}"
        z=qc.groupby("subject")[col].all().rename(flag).reset_index()
        sq=sq.merge(z,on="subject",how="left")
        sq[flag]=sq[flag].fillna(False)&sq["conditions"].eq(2)
    ev=ev.merge(sq[["subject","eye_included"]],on="subject",how="left")
    metrics=[]
    inc=ev[ev.eye_included.fillna(False)].copy()
    for (subject,condition,region),g in inc.groupby(["subject","condition","region"],observed=True):
        total=g.duration_s.sum(); denom=inc[(inc.subject==subject)&(inc.condition==condition)].duration_s.sum()
        metrics.append({"subject":subject,"condition":condition,"region":region,"total_fixation_time":total,
                        "fixation_count":len(g),"mean_fixation_time":g.duration_s.mean(),"fixation_time_ratio":total/denom if denom>0 else np.nan})
    met=pd.DataFrame(metrics)
    eps=1e-5
    if not met.empty:
        met["fixation_time_ratio_logit"]=np.log(np.clip(met.fixation_time_ratio,eps,1-eps)/(1-np.clip(met.fixation_time_ratio,eps,1-eps)))
        for c in ["total_fixation_time","fixation_count","mean_fixation_time"]: met[f"{c}_log1p"]=np.log1p(met[c])
    return ev,qc.merge(sq,on="subject",how="left"),met


def build_dyads(events: pd.DataFrame, behavior_summary: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    auc=behavior_summary[["subject","condition","auc"]].dropna()
    eligible=set(auc.subject)&set(events.loc[events.eye_included.fillna(False),"subject"])
    e=events[events.subject.isin(eligible)&events.eye_included.fillna(False)].sort_values(["subject","event_order"]).copy()
    e["log_duration"]=np.log(e.duration_s.clip(lower=1e-6))
    e["duration_class"]=e.groupby("subject")["log_duration"].transform(lambda x:np.where(x>x.median(),"LONG","MED"))
    event_rows=[]; duration_rows=[]; subject_totals=[]
    for subject,g0 in e.groupby("subject",sort=False):
        total=0
        g0=g0.sort_values("event_order").copy()
        g0["condition_block"] = g0.condition.ne(g0.condition.shift()).cumsum()
        for cond in CONDITIONS:
            ed_total=Counter(); dd_total=Counter(); ntrans=0
            for _,g in g0[g0.condition.eq(cond)].groupby("condition_block",sort=False):
                nxt=g.shift(-1); valid=nxt.condition.eq(g.condition)
                eg=g[valid]; ng=nxt[valid]
                ed_total.update((eg.region+"->"+ng.region).tolist())
                dd_total.update((eg.region+"_"+eg.duration_class+"->"+ng.region+"_"+ng.duration_class).tolist())
                ntrans += int(valid.sum())
            total+=ntrans
            for dyad in ["ball->ball","ball->position","position->ball","position->position"]:
                count=int(ed_total.get(dyad,0)); event_rows.append({"subject":subject,"condition":cond,"dyad":dyad,"count":count,"total_transitions":ntrans,"rate":count/ntrans if ntrans else np.nan})
            labels=[f"{a}_{u}->{b}_{v}" for a in ["ball","position"] for u in ["MED","LONG"] for b in ["ball","position"] for v in ["MED","LONG"]]
            for dyad in labels:
                count=int(dd_total.get(dyad,0)); duration_rows.append({"subject":subject,"condition":cond,"dyad":dyad,"count":count,"total_transitions":ntrans,"rate":count/ntrans if ntrans else np.nan})
        subject_totals.append({"subject":subject,"dyad_total":total})
    totals=pd.DataFrame(subject_totals)
    threshold=float(totals.dyad_total.mean()-CONFIG["spam_dsm_qc"]["dyad_total_sd_cutoff"]*totals.dyad_total.std(ddof=1))
    totals["spam_included"]=totals.dyad_total>=threshold
    totals["m_minus_2sd_threshold"]=threshold
    er=pd.DataFrame(event_rows).merge(totals,on="subject").query("spam_included")
    dr=pd.DataFrame(duration_rows).merge(totals,on="subject").query("spam_included")
    er=er.merge(auc,on=["subject","condition"],how="left"); dr=dr.merge(auc,on=["subject","condition"],how="left")
    return er,dr,totals,auc


def permutation_difference(x: np.ndarray,y: np.ndarray,n_perm:int) -> tuple[float,float]:
    x=np.asarray(x,float);y=np.asarray(y,float);x=x[np.isfinite(x)];y=y[np.isfinite(y)]
    obs=float(np.mean(x)-np.mean(y)); pooled=np.r_[x,y]; nx=len(x)
    if nx<2 or len(y)<2:return obs,np.nan
    exceed=0
    for _ in range(n_perm):
        p=RNG.permutation(pooled); diff=np.mean(p[:nx])-np.mean(p[nx:])
        exceed+=abs(diff)>=abs(obs)
    return obs,(exceed+1)/(n_perm+1)


def analyze_dsm(df: pd.DataFrame, representation: str) -> tuple[pd.DataFrame,pd.DataFrame]:
    rows=[]; continuous=[]; n_perm=int(CONFIG["spam_dsm_qc"]["permutations"])
    for cond,gc in df.groupby("condition"):
        q1,q3=gc[["subject","auc"]].drop_duplicates().auc.quantile([.25,.75])
        group_auc=gc[["subject","auc"]].drop_duplicates()
        group_auc["group"]=np.where(group_auc.auc<q1,"Low",np.where(group_auc.auc>q3,"High","Middle/tie"))
        z=gc.merge(group_auc,on=["subject","auc"],how="left")
        for dyad,g in z.groupby("dyad"):
            hi=g.loc[g.group.eq("High"),"rate"].to_numpy();lo=g.loc[g.group.eq("Low"),"rate"].to_numpy()
            diff,p=permutation_difference(hi,lo,n_perm)
            wt=stats.ttest_ind(hi,lo,equal_var=False,nan_policy="omit")
            rows.append({"representation":representation,"condition":cond,"dyad":dyad,"q1":q1,"q3":q3,
                         "n_high":np.isfinite(hi).sum(),"n_low":np.isfinite(lo).sum(),"high_mean_rate":np.nanmean(hi),"low_mean_rate":np.nanmean(lo),
                         "high_minus_low":diff,"permutation_p":p,"welch_t":wt.statistic,"welch_p":wt.pvalue})
            gg=g[["rate","auc"]].dropna()
            if len(gg)>=20 and gg.auc.nunique()>2:
                m=ols("rate ~ auc",data=gg).fit(cov_type="HC3")
                continuous.append({"representation":representation,"condition":cond,"dyad":dyad,"n":len(gg),"auc_slope":m.params.get("auc",np.nan),"robust_se":m.bse.get("auc",np.nan),"p_value":m.pvalues.get("auc",np.nan),"r_squared":m.rsquared})
    res=pd.DataFrame(rows); cont=pd.DataFrame(continuous)
    if not res.empty:
        res["permutation_p_fdr"]=res.groupby(["representation","condition"])["permutation_p"].transform(lambda p:multipletests(p.fillna(1),method="fdr_bh")[1])
    if not cont.empty:
        cont["p_fdr"]=cont.groupby(["representation","condition"])["p_value"].transform(lambda p:multipletests(p.fillna(1),method="fdr_bh")[1])
    return res,cont


def prepare_r_input(trial: pd.DataFrame, eye_metrics: pd.DataFrame) -> Path:
    cols=["subject","condition","correct","confidence","confidence_within","confidence_between","velocity","size_pair","target","trial_c","trial_c2",
          "log_answer_rt","log_confidence_rt","occlusion_hidden_c","behavior_included"]
    d=trial[cols].copy()
    path=CACHE_DIR/"behavior_model_input.csv"; d.to_csv(path,index=False)
    eye_metrics.to_csv(CACHE_DIR/"eye_metrics_model_input.csv",index=False)
    return path


def run_r_models(input_path: Path) -> None:
    rscript=shutil.which("Rscript")
    if not rscript:
        save_csv(pd.DataFrame([{"status":"not_run","reason":"Rscript not found; install R, lme4, and ordinal"}]),"r_model_status.csv")
        write_log("Rscript not found; mixed models skipped")
        return
    probe=subprocess.run([rscript,"-e","quit(status=ifelse(requireNamespace('lme4',quietly=TRUE)&&requireNamespace('ordinal',quietly=TRUE),0,2))"])
    if probe.returncode!=0:
        save_csv(pd.DataFrame([{"status":"not_run","reason":"Required R packages lme4/ordinal unavailable"}]),"r_model_status.csv")
        return
    cmd=[rscript,str(ROOT/"r_models.R"),str(input_path),str(TABLE_DIR)]
    write_log("Fitting R mixed models")
    proc=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,encoding="utf-8",errors="replace")
    (LOG_DIR/"r_models_stdout.log").write_text(proc.stdout,encoding="utf-8")
    (LOG_DIR/"r_models_stderr.log").write_text(proc.stderr,encoding="utf-8")
    save_csv(pd.DataFrame([{"status":"success" if proc.returncode==0 else "failed","return_code":proc.returncode,"command":" ".join(cmd)}]),"r_model_status.csv")
    if proc.returncode!=0: raise RuntimeError(f"R models failed; see {LOG_DIR/'r_models_stderr.log'}")


def normalize_model_diagnostics() -> None:
    for name in ["behavior_model_diagnostics.csv","eye_model_diagnostics.csv"]:
        path=TABLE_DIR/name
        if not path.exists(): continue
        d=pd.read_csv(path)
        if d.empty or "model" not in d: continue
        rows=[]
        for model,g in d.groupby("model",sort=False):
            row=g.iloc[0].to_dict()
            row["formula"]=" ".join(dict.fromkeys(g["formula"].dropna().astype(str)))
            if ("fallback_reason" not in row or pd.isna(row.get("fallback_reason"))) and float(row.get("formula_index",1))>1:
                row["fallback_reason"]="Full/uncorrelated random structure was singular or non-convergent; retained the first acceptable fallback."
            rows.append(row)
        pd.DataFrame(rows).to_csv(path,index=False,encoding="utf-8-sig")


def setup_plot_style() -> None:
    mpl.rcParams.update({
        "font.family":"sans-serif","font.sans-serif":["Arial","Microsoft YaHei","DejaVu Sans"],
        "font.size":8,"axes.labelsize":8.5,"axes.titlesize":9,"xtick.labelsize":7.5,"ytick.labelsize":7.5,
        "legend.fontsize":7.5,"axes.spines.top":False,"axes.spines.right":False,"axes.linewidth":0.7,
        "xtick.major.width":0.6,"ytick.major.width":0.6,"savefig.facecolor":"white","pdf.fonttype":42,"ps.fonttype":42,
    })


def export_figure(fig: plt.Figure,name: str) -> None:
    dpi=int(CONFIG["figure_dpi"])
    fig.savefig(FIG_DIR/f"{name}.png",dpi=dpi,bbox_inches="tight",facecolor="white")
    fig.savefig(FIG_DIR/f"{name}.pdf",bbox_inches="tight",facecolor="white")
    fig.savefig(FIG_DIR/f"{name}.svg",bbox_inches="tight",facecolor="white")
    plt.close(fig)


def add_panel_label(ax: plt.Axes,label: str) -> None:
    ax.text(-.15,1.07,label,transform=ax.transAxes,fontweight="bold",fontsize=10,va="top")


def paired_panel(ax:plt.Axes,summary:pd.DataFrame,metric:str,ylabel:str) -> None:
    w=summary.pivot(index="subject",columns="condition",values=metric).dropna()
    x=np.array([0,1]);
    for _,r in w.iterrows(): ax.plot(x,[r.gravity,r.zero_gravity],color="#9E9E9E",alpha=.18,lw=.45,zorder=1)
    jitter=RNG.normal(0,.035,(len(w),2))
    ax.scatter(np.zeros(len(w))+jitter[:,0],w.gravity,s=8,color=OKABE_ITO["gravity"],alpha=.42,edgecolors="none",zorder=2)
    ax.scatter(np.ones(len(w))+jitter[:,1],w.zero_gravity,s=8,color=OKABE_ITO["zero_gravity"],alpha=.42,edgecolors="none",zorder=2)
    for i,c in enumerate(CONDITIONS):
        v=w[c].to_numpy(); mean=np.mean(v);ci=stats.t.interval(.95,len(v)-1,loc=mean,scale=stats.sem(v))
        ax.errorbar(i,mean,yerr=[[mean-ci[0]],[ci[1]-mean]],fmt="o",ms=5,color="black",mfc="white",mew=1,capsize=3,zorder=4)
    ax.set_xticks(x,["Gravity","Zero gravity"]);ax.set_ylabel(ylabel);ax.set_title(f"n = {len(w)}")


def make_behavior_figure(summary:pd.DataFrame) -> None:
    fig,axes=plt.subplots(2,2,figsize=(7.1,5.4),constrained_layout=True)
    specs=[("accuracy","Accuracy"),("answer_rt_median","Median decision RT (ms)"),("confidence_mean","Mean confidence (1-7)"),("auc","Type-2 ROC AUC")]
    for label,ax,(metric,ylabel) in zip("ABCD",axes.ravel(),specs):
        paired_panel(ax,summary,metric,ylabel);add_panel_label(ax,label)
        if metric in ["accuracy","auc"]: ax.axhline(.5,color="#777777",ls="--",lw=.6,zorder=0)
    export_figure(fig,"Figure_1_behavior_and_metacognition")


def make_eye_figure(eye_metrics:pd.DataFrame) -> None:
    fig,axes=plt.subplots(2,2,figsize=(7.1,5.5),constrained_layout=True)
    specs=[("fixation_time_ratio","Fixation-time proportion"),("total_fixation_time","Total fixation time (s)"),
           ("fixation_count","Fixation-event count"),("mean_fixation_time","Mean fixation duration (s)")]
    for label,ax,(metric,ylabel) in zip("ABCD",axes.ravel(),specs):
        z=eye_metrics.groupby(["subject","condition","region"],observed=True)[metric].mean().reset_index()
        s=z.groupby(["condition","region"])[metric].agg(["mean","sem"]).reset_index()
        for j,cond in enumerate(CONDITIONS):
            q=s[s.condition.eq(cond)]
            xpos=np.array([0,1])+(j-.5)*.16
            ax.errorbar(xpos,q["mean"],yerr=1.96*q["sem"],fmt="o-",capsize=3,color=OKABE_ITO[cond],label=cond.replace("_"," "))
        ax.set_xticks([0,1],["Ball region","Position region"]);ax.set_ylabel(ylabel);add_panel_label(ax,label)
        if label=="A":ax.legend(frameon=False)
    export_figure(fig,"Figure_4_gaze_allocation")


def make_spam_figure(event_res:pd.DataFrame,duration_res:pd.DataFrame,continuous:pd.DataFrame) -> None:
    # Extra vertical space keeps long duration-dyad labels and panel letters
    # separated in both the raster and vector publication exports.
    fig=plt.figure(figsize=(7.1,7.2),constrained_layout=False)
    gs=fig.add_gridspec(2,2,height_ratios=[1,1.25],left=.20,right=.98,
                        bottom=.08,top=.94,wspace=.48,hspace=.58)
    for idx,cond in enumerate(CONDITIONS):
        ax=fig.add_subplot(gs[0,idx]);z=event_res[event_res.condition.eq(cond)].set_index("dyad").reindex(["ball->ball","ball->position","position->ball","position->position"])
        vals=z.high_minus_low.to_numpy().reshape(2,2);norm=TwoSlopeNorm(vcenter=0,vmin=min(-1e-5,np.nanmin(vals)),vmax=max(1e-5,np.nanmax(vals)))
        im=ax.imshow(vals,cmap="PuOr",norm=norm)
        ax.set_xticks([0,1],["Ball","Position"]);ax.set_yticks([0,1],["Ball","Position"]);ax.set_xlabel("To");ax.set_ylabel("From");ax.set_title(cond.replace("_"," ").title()+" event dyads")
        for i in range(2):
            for j in range(2): ax.text(j,i,f"{vals[i,j]:.3f}",ha="center",va="center",fontsize=7)
        fig.colorbar(im,ax=ax,shrink=.68,label="High - low AUC rate");add_panel_label(ax,"AB"[idx])
    ax=fig.add_subplot(gs[1,0]);z=duration_res.sort_values("permutation_p_fdr").head(12).sort_values("high_minus_low")
    colors=[OKABE_ITO[c] for c in z.condition]
    ax.barh(np.arange(len(z)),z.high_minus_low,color=colors,alpha=.8)
    ax.axvline(0,color="black",lw=.7);ax.set_yticks(np.arange(len(z)),[f"{r.condition[:1].upper()} | {r.dyad}" for r in z.itertuples()],fontsize=5.8);ax.set_xlabel("High - low AUC normalized dyad rate");ax.set_title("Duration-dyad group contrasts",pad=10);ax.text(-.28,1.10,"C",transform=ax.transAxes,fontsize=10,fontweight="bold",va="top")
    ax=fig.add_subplot(gs[1,1]);z=continuous.sort_values("p_fdr").head(12).sort_values("auc_slope")
    colors=[OKABE_ITO[c] for c in z.condition]
    ax.barh(np.arange(len(z)),z.auc_slope,color=colors,alpha=.8);ax.axvline(0,color="black",lw=.7)
    ax.set_yticks(np.arange(len(z)),[f"{r.condition[:1].upper()} | {r.dyad}" for r in z.itertuples()],fontsize=5.8);ax.set_xlabel("Continuous AUC slope");ax.set_title("Continuous-AUC associations",pad=10);ax.text(-.28,1.10,"D",transform=ax.transAxes,fontsize=10,fontweight="bold",va="top")
    export_figure(fig,"Figure_5_SPAM_DSM_exploratory")


def make_diagnostic_figure(trial:pd.DataFrame,eye_qc:pd.DataFrame,dyad_totals:pd.DataFrame) -> None:
    fig,axes=plt.subplots(2,2,figsize=(7.1,5.4),constrained_layout=True)
    ax=axes[0,0];d=trial[trial.behavior_included.eq(1)&trial.answer_rt.notna()]
    for cond in CONDITIONS: ax.hist(np.log(d.loc[d.condition.eq(cond),"answer_rt"]),bins=45,density=True,histtype="step",lw=1.2,color=OKABE_ITO[cond],label=cond.replace("_"," "))
    ax.set_xlabel("Log decision RT (ms)");ax.set_ylabel("Density");ax.legend(frameon=False);add_panel_label(ax,"A")
    ax=axes[0,1];q=eye_qc.drop_duplicates("subject")
    ax.hist(q.min_coverage,bins=np.linspace(0,1,31),color="#56B4E9",edgecolor="white");ax.axvline(.5,color="#D55E00",ls="--",label="Primary threshold");ax.set_xlabel("Minimum condition non-gap coverage");ax.set_ylabel("Participants");ax.legend(frameon=False);add_panel_label(ax,"B")
    ax=axes[1,0];ax.hist(dyad_totals.dyad_total,bins=35,color="#009E73",edgecolor="white");thr=dyad_totals.m_minus_2sd_threshold.iloc[0];ax.axvline(thr,color="#D55E00",ls="--",label=f"M - 2SD = {thr:.1f}");ax.set_xlabel("Total usable dyads");ax.set_ylabel("Participants");ax.legend(frameon=False);add_panel_label(ax,"C")
    ax=axes[1,1];counts=pd.Series({"Behavior included":trial.drop_duplicates("subject").behavior_included.sum(),"Eye included":q.eye_included.sum(),"SPAM/DSM included":dyad_totals.spam_included.sum()})
    ax.barh(counts.index,counts.values,color=["#0072B2","#CC79A7","#E69F00"]);ax.set_xlabel("Participants");
    for i,v in enumerate(counts):ax.text(v+2,i,str(int(v)),va="center");add_panel_label(ax,"D")
    export_figure(fig,"Figure_S1_quality_control_and_diagnostics")


def sample_flow(trial:pd.DataFrame,eye_qc:pd.DataFrame,dyad_totals:pd.DataFrame) -> pd.DataFrame:
    s=trial.drop_duplicates("subject")[["subject","behavior_included","auc_included"]]
    e=eye_qc.drop_duplicates("subject")[["subject","eye_included","eye_included_40","eye_included_60"]]
    x=s.merge(e,on="subject",how="outer").merge(dyad_totals[["subject","spam_included"]],on="subject",how="left")
    rows=[
        ("Matched behavior-eye files",len(x)),
        ("Behavior QC included",int(x.behavior_included.fillna(False).sum())),
        ("AUC QC included",int(x.auc_included.fillna(False).sum())),
        ("Eye QC included (50%)",int(x.eye_included.fillna(False).sum())),
        ("Eye QC included (40% sensitivity)",int(x.eye_included_40.fillna(False).sum())),
        ("Eye QC included (60% sensitivity)",int(x.eye_included_60.fillna(False).sum())),
        ("SPAM/DSM M-2SD included",int(x.spam_included.fillna(False).sum())),
    ]
    return pd.DataFrame(rows,columns=["stage","n"])


def write_runtime_manifest(participants:list[str]) -> None:
    info={"timestamp":time.strftime("%Y-%m-%dT%H:%M:%S%z"),"python":sys.version,"platform":platform.platform(),
          "participants":len(participants),"random_seed":SEED,"command":" ".join(sys.argv)}
    try:
        info["r_version"]=subprocess.run([shutil.which("Rscript") or "Rscript","--version"],capture_output=True,text=True).stderr.strip()
    except Exception: info["r_version"]="not available"
    (OUT_DIR/"runtime_manifest.json").write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding="utf-8")


def robustness_tables(trial:pd.DataFrame,summary:pd.DataFrame,eye_events:pd.DataFrame,eye_qc:pd.DataFrame) -> None:
    d=trial[trial.behavior_included.eq(1)].copy();lo,hi=CONFIG["rt_sensitivity_ms"]
    rt=d[d.valid_response & d.answer_rt.between(lo,hi)].groupby(["subject","condition"]).answer_rt.median().unstack().dropna()
    rt_eff=paired_ci(rt.gravity,rt.zero_gravity)
    save_csv(pd.DataFrame([{"analysis":"decision_rt_restricted","lower_ms":lo,"upper_ms":hi,"n":len(rt),"zero_minus_gravity":rt_eff[0],"ci95_low":rt_eff[1],"ci95_high":rt_eff[2],"paired_p":stats.ttest_rel(rt.zero_gravity,rt.gravity).pvalue}]),"rt_sensitivity.csv")
    corr=[]
    for cond,g in summary.groupby("condition"):
        z=g[["accuracy","auc"]].dropna();r,p=stats.pearsonr(z.accuracy,z.auc);rs,ps=stats.spearmanr(z.accuracy,z.auc)
        corr.append({"condition":cond,"n":len(z),"pearson_r":r,"pearson_p":p,"spearman_rho":rs,"spearman_p":ps})
    save_csv(pd.DataFrame(corr),"accuracy_auc_correlations.csv")
    option=trial.groupby(["condition","velocity"]).agg(n=("option_distance","size"),distance_mean=("option_distance","mean"),distance_sd=("option_distance","std"),
        hidden_duration_mean=("occlusion_hidden","mean"),hidden_duration_sd=("occlusion_hidden","std"),occlusion_start_mean=("occlusion_start","mean"),first_boundary_levels=("FirstBoundaryType",lambda x:';'.join(sorted(set(x.dropna().astype(str)))))).reset_index()
    save_csv(option,"stimulus_generation_checks.csv")
    # Leave-one-participant-out stability of paired condition effects.
    loo=[]
    for metric in ["accuracy","answer_rt_median","confidence_mean","auc"]:
        w=summary.pivot(index="subject",columns="condition",values=metric).dropna();diff=w.zero_gravity-w.gravity
        estimates=[diff.drop(i).mean() for i in diff.index]
        loo.append({"metric":metric,"full_difference":diff.mean(),"loo_min":np.min(estimates),"loo_max":np.max(estimates),"sign_stable":bool(np.all(np.sign(estimates)==np.sign(diff.mean())))})
    save_csv(pd.DataFrame(loo),"leave_one_subject_out_stability.csv")
    # Eye threshold sensitivity: direct within-participant change in the share
    # of fixation time allocated to the position AOI.  Because the ball and
    # position shares sum to one, this is the clearest single-scale expression
    # of the same reallocation pattern on an interpretable percentage-point scale.
    sens=[];eq=eye_qc.drop_duplicates("subject")
    for pct,col in [(40,"eye_included_40"),(50,"eye_included"),(60,"eye_included_60")]:
        ids=set(eq.loc[eq[col].fillna(False),"subject"]);ev=eye_events[eye_events.subject.isin(ids)].copy()
        m=ev.groupby(["subject","condition","region"]).duration_s.sum().rename("dur").reset_index()
        m["ratio"]=m.dur/m.groupby(["subject","condition"]).dur.transform("sum")
        w=m.pivot(index="subject",columns=["condition","region"],values="ratio").dropna()
        if len(w):
            change=(w[("zero_gravity","position")]-w[("gravity","position")])*100
            ci=stats.t.interval(.95,len(change)-1,loc=change.mean(),scale=stats.sem(change))
            t=stats.ttest_1samp(change,0)
            sens.append({"coverage_threshold":pct/100,"n":len(change),
                         "position_share_change_pp":change.mean(),
                         "ci95_low_pp":ci[0],"ci95_high_pp":ci[1],
                         "t":t.statistic,"p":t.pvalue})
    save_csv(pd.DataFrame(sens),"eye_coverage_threshold_sensitivity.csv")


def update_readme(participants:int) -> None:
    text=f"""# OSF-ready PB&R revision analysis package

This folder contains **{participants} matched participants** with a behavioral CSV and an eye-tracking XLSX. It is a self-contained, reproducible analysis package for the manuscript revision. The participant count is discovered from the current matched filenames rather than hard-coded.

## One-command reproduction

1. Install Python 3.12 and R 4.4 (or create the supplied Conda environment): `conda env create -f environment.yml`.
2. Ensure R packages `lme4` and `ordinal` are available.
3. From this folder run `python run_analysis.py` (Windows users may double-click `run_analysis.bat`).

The first run parses about 5.5 GB of eye-tracking workbooks and may take 10-30 minutes. Parsed fixation events are cached under `cache/`; use `python run_analysis.py --rebuild-eye` only when the source XLSX files change. All derived results are written to `outputs/`.

## Prespecified exclusion rules

- Behavior: exclude a participant if either condition has fewer than 24 valid responses, fewer than 3 correct responses, or fewer than 3 error responses.
- AUC: additionally require at least 24 valid confidence trials and at least 3 correct and 3 error confidence trials per condition.
- Eye tracking: primary threshold is at least 50% non-Gap coverage and at least 10 fixation events in each condition; 40% and 60% thresholds are sensitivity checks.
- SPAM/DSM: exclude participants whose total usable dyad count is below M - 2 SD. Inference uses normalized dyad frequency, permutation tests, and BH-FDR correction.

## Analysis scope

The pipeline produces participant-level condition summaries, trial-level GLMM/LMM/CLMM models, confidence-accuracy coupling analyses, stimulus-generation checks, AOI condition-by-region models, exploratory event/duration SPAM-DSM, continuous-AUC sensitivity analyses, diagnostics, publication figures (PNG/PDF/SVG), machine-readable CSV tables, and a concise Chinese Word report.

The interpretation is deliberately conservative: gravity versus zero-gravity is treated as a task-context/cue-alignment contrast, not as a unique causal test of internal gravity-prior violation.

## Data notes

`MainData.TOI` supplies `gravity` and `zero_gravity` labels. Eye files do not retain trial identifiers; therefore scan-path transitions may cross adjacent trial boundaries within a TOI and SPAM/DSM results are exploratory. Original source data are never overwritten.
"""
    (ROOT/"README.md").write_text(text,encoding="utf-8")


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--rebuild-eye",action="store_true");parser.add_argument("--skip-models",action="store_true");parser.add_argument("--skip-report",action="store_true");args=parser.parse_args()
    ensure_dirs();setup_plot_style();(LOG_DIR/"pipeline.log").write_text("",encoding="utf-8")
    participants,file_match=discover_participants();write_log(f"Matched participants: {len(participants)}");save_csv(file_match,"file_matching_audit.csv");update_readme(len(participants));write_runtime_manifest(participants)
    trial,qc,file_audit=load_behavior(participants);save_csv(file_audit,"behavior_file_audit.csv");save_csv(qc,"behavior_qc_by_condition.csv")
    summary,effects=summarize_behavior(trial,qc);save_csv(summary,"participant_condition_summary.csv");save_csv(effects,"paired_condition_effects.csv")
    write_log(f"Behavior included: {trial.drop_duplicates('subject').behavior_included.sum()}; AUC included: {trial.drop_duplicates('subject').auc_included.sum()}")
    events,eye_qc,eye_metrics=process_eye(participants,args.rebuild_eye);save_csv(eye_qc,"eye_qc_by_condition.csv");save_csv(eye_metrics,"eye_metrics_subject_condition_region.csv")
    er,dr,totals,auc=build_dyads(events,summary);save_csv(er,"event_dyad_subject_rates.csv");save_csv(dr,"duration_dyad_subject_rates.csv");save_csv(totals,"spam_dsm_dyad_qc.csv")
    event_res,event_cont=analyze_dsm(er,"event");dur_res,dur_cont=analyze_dsm(dr,"duration");dsm=pd.concat([event_res,dur_res],ignore_index=True);cont=pd.concat([event_cont,dur_cont],ignore_index=True)
    save_csv(dsm,"dsm_results_all.csv");save_csv(cont,"dsm_continuous_auc_sensitivity.csv")
    support=[]
    for rep,df in [("event",er),("duration",dr)]:
        for (cond,dyad),g in df.groupby(["condition","dyad"]):support.append({"representation":rep,"condition":cond,"dyad":dyad,"n_participants":g.subject.nunique(),"s_support":(g['count']>0).mean(),"i_support_total":g['count'].sum(),"mean_normalized_i_support":g.rate.mean()})
    save_csv(pd.DataFrame(support),"spam_support_summary.csv")
    flow=sample_flow(trial,eye_qc,totals);save_csv(flow,"sample_flow.csv");robustness_tables(trial,summary,events,eye_qc)
    model_input=prepare_r_input(trial,eye_metrics)
    if not args.skip_models:run_r_models(model_input)
    normalize_model_diagnostics()
    # Generate the fixed 183-mm Nature-style figure system after all source
    # tables and model diagnostics are available.
    import nature_figures
    nature_figures.generate_all()
    summary_json={"matched":len(participants),"behavior_included":int(flow.loc[flow.stage.eq('Behavior QC included'),'n'].iloc[0]),"auc_included":int(flow.loc[flow.stage.eq('AUC QC included'),'n'].iloc[0]),"eye_included":int(flow.loc[flow.stage.eq('Eye QC included (50%)'),'n'].iloc[0]),"spam_included":int(flow.loc[flow.stage.eq('SPAM/DSM M-2SD included'),'n'].iloc[0]),"significant_dsm_fdr":int((dsm.permutation_p_fdr<.05).sum())}
    (OUT_DIR/"analysis_summary.json").write_text(json.dumps(summary_json,ensure_ascii=False,indent=2),encoding="utf-8")
    if not args.skip_report:
        proc=subprocess.run([sys.executable,str(ROOT/"generate_report.py")],cwd=ROOT,text=True,capture_output=True,encoding="utf-8",errors="replace")
        (LOG_DIR/"report_stdout.log").write_text(proc.stdout,encoding="utf-8");(LOG_DIR/"report_stderr.log").write_text(proc.stderr,encoding="utf-8")
        if proc.returncode:raise RuntimeError(f"Report generation failed: {proc.stderr}")
    write_log("Analysis pipeline completed successfully")


if __name__=="__main__":main()
