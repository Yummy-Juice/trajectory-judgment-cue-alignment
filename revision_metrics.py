"""Second-revision metrics and direct extensions of the original AUC analyses."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

import metacognition as sd

METRICS = ['auc', 'meta_d', 'm_ratio', 'auc_ratio']
EXTRA = ['d_prime', 'meta_d', 'm_ratio', 'auc_ratio']
LABELS = {'auc': 'Type-2 ROC AUC', 'meta_d': "meta-d′", 'm_ratio': 'M-ratio',
          'auc_ratio': 'AUC-ratio', 'd_prime': 'd′', 'accuracy': 'Accuracy',
          'answer_rt_median': 'Decision RT (median)', 'answer_rt_mean': 'Decision RT (mean)',
          'confidence_mean': 'Mean confidence', 'confidence_rt_median': 'Confidence RT'}
FIT_SPEC = 'reference_equal_variance_7ratings_relative_c_pseudocount_1over14_v1'


def metric_values(data: pd.DataFrame, eligible: bool = True) -> tuple[dict, np.ndarray, np.ndarray]:
    """Use raw stimulus/response codes, fixed integer confidence, and original QC."""
    s = pd.to_numeric(data['ExpectedAnswer'], errors='coerce')
    r = pd.to_numeric(data['UserAnswer'], errors='coerce')
    c = pd.to_numeric(data['ConfidenceRating'], errors='coerce')
    valid = s.isin([0, 1]) & r.isin([0, 1]) & c.isin(range(1, 8))
    s, r, c = s[valid].to_numpy(), r[valid].to_numpy(), c[valid].to_numpy()
    a, b = sd.prepare_SDT_data(s, r, c)
    correct = s == r
    nratings = int(np.unique(c).size)
    record = dict(n_sdt_trials=len(s), n_stimulus_0=int(a.sum()), n_stimulus_1=int(b.sum()),
                  n_response_0=int((r == 0).sum()), n_response_1=int((r == 1).sum()),
                  n_correct_sdt=int(correct.sum()), n_error_sdt=int((~correct).sum()),
                  confidence_levels_used=nratings, empty_cells=int((a == 0).sum()+(b == 0).sum()),
                  auc=np.nan, d_prime=np.nan, meta_d=np.nan, m_ratio=np.nan,
                  expected_auc=np.nan, auc_ratio=np.nan, status='qc_failed',
                  optimizer_success=False, iterations=0, message='', fit_spec=FIT_SPEC)
    if not eligible:
        return record, a, b
    fit = sd.fit_meta_d_mle(a, b)
    record.update(fit)
    if 'relative_criteria' in record:
        record['relative_criteria'] = json.dumps(record['relative_criteria'])
    # Original public-package convention: constant confidence is undefined.
    if nratings >= 2 and np.unique(correct).size == 2:
        record['auc'] = sd.calculate_auc2_mannwhitney(c, correct.astype(int))
        record['expected_auc'] = sd.calculate_expected_auc_sdt(a, b)
        if np.isfinite(record['expected_auc']) and record['expected_auc'] > 0:
            record['auc_ratio'] = record['auc'] / record['expected_auc']
    return record, a, b


def fit_participants(trial: pd.DataFrame, root: Path, log=print) -> pd.DataFrame:
    checkpoint = root / 'cache' / 'metacognition_fits.csv'
    prior = {}
    if checkpoint.exists():
        old = pd.read_csv(checkpoint, dtype={'subject': str, 'input_mtime_ns': str})
        prior = {(r['subject'], r['condition']): r for r in old.to_dict('records')}
    rows, count_rows = [], []
    start, reused = time.monotonic(), 0
    groups = trial.groupby(['subject', 'condition'], sort=True)
    for i, ((subject, condition), g) in enumerate(groups, 1):
        stat = (root / 'behavioral_data' / f'{subject}.csv').stat()
        old = prior.get((str(subject), condition), {})
        if (old.get('fit_spec') == FIT_SPEC and str(old.get('input_mtime_ns')) == str(stat.st_mtime_ns)
                and old.get('input_size') == stat.st_size):
            result = old.copy()
            reused += 1
            _, a, b = metric_values(g, eligible=False)
        else:
            result, a, b = metric_values(g, eligible=bool(g.auc_included.iloc[0]))
        result.update(subject=str(subject), condition=condition,
                      input_mtime_ns=str(stat.st_mtime_ns), input_size=stat.st_size)
        rows.append(result)
        for stimulus, counts in enumerate([a, b]):
            for k, n in enumerate(counts):
                response = int(k >= 7)
                confidence = 7-k if response == 0 else k-6
                count_rows.append(dict(subject=str(subject), condition=condition, stimulus=stimulus,
                                       response=response, confidence=confidence, count=int(n)))
        if i % 40 == 0 or i == len(groups):
            pd.DataFrame(rows).to_csv(checkpoint, index=False, encoding='utf-8-sig')
            log(f'SDT fits {i}/{len(groups)}, reused {reused}, elapsed {time.monotonic()-start:.1f}s')
    fits = pd.DataFrame(rows)
    fits.drop(columns=['input_mtime_ns', 'input_size']).to_csv(
        root/'outputs/tables/metad_mle_subject_condition.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(count_rows).to_csv(root/'outputs/tables/metad_input_counts.csv', index=False, encoding='utf-8-sig')
    return fits


def extend_summary(pipeline, trial, summary, qc):
    fits = fit_participants(trial, pipeline.ROOT, pipeline.write_log)
    selected = fits[['subject', 'condition'] + EXTRA + ['expected_auc', 'status']].copy()
    summary = summary.merge(selected, on=['subject', 'condition'], how='left', validate='one_to_one')
    old = summary[['subject','condition','auc']].merge(fits[['subject','condition','auc']],
             on=['subject','condition'], suffixes=('_original','_reference'))
    finite = old[['auc_original','auc_reference']].notna().all(axis=1)
    if not np.allclose(old.loc[finite,'auc_original'], old.loc[finite,'auc_reference'], atol=1e-12):
        raise ValueError('Reference AUC and baseline AUC differ on common finite records')
    metrics = ['accuracy','answer_rt_median','answer_rt_mean','confidence_mean','confidence_rt_median','auc'] + EXTRA
    wide = summary.pivot(index='subject', columns='condition', values=metrics)
    wide.columns = [f'{a}_{b}' for a,b in wide.columns]
    effects = pd.DataFrame([pipeline.paired_effects(wide, m) for m in metrics])
    effects['p_bh'] = multipletests(effects.paired_t_p.fillna(1), method='fdr_bh')[1]
    effects['p_bh_metacognition'] = np.nan
    mask = effects.metric.isin(METRICS)
    effects.loc[mask, 'p_bh_metacognition'] = multipletests(effects.loc[mask,'paired_t_p'].fillna(1),method='fdr_bh')[1]
    flow = []
    for m in ['d_prime'] + METRICS:
        w = summary.pivot(index='subject',columns='condition',values=m)
        flow.append(dict(metric=m, behavioral_qc_participants=summary.subject.nunique(),
                         confidence_count_qc_participants=qc.loc[qc.auc_included.eq(True),'subject'].nunique(),
                         finite_gravity=int(w.gravity.notna().sum()), finite_zero_gravity=int(w.zero_gravity.notna().sum()),
                         finite_paired=int(w.notna().all(axis=1).sum())))
    pipeline.save_csv(pd.DataFrame(flow), 'metad_sample_flow.csv')
    status = fits.groupby(['condition','status'],dropna=False).size().rename('n').reset_index()
    pipeline.save_csv(status,'metad_fit_status_counts.csv')
    predictive=[]
    for row in fits[fits.status.eq('ok')].itertuples():
        selected=trial[(trial.subject.eq(row.subject))&(trial.condition.eq(row.condition))]
        _,a,b=metric_values(selected,eligible=False)
        cuts=np.r_[-np.inf,np.asarray(json.loads(row.relative_criteria))[:6],0,
                   np.asarray(json.loads(row.relative_criteria))[6:],np.inf]
        probabilities=[]
        for stimulus,counts in enumerate([a,b]):
            mean=(stimulus-.5)*row.meta_d-row.meta_d*row.criterion/row.d_prime
            mass=np.exp(sd._normal_log_interval(cuts[:-1]-mean,cuts[1:]-mean))
            pred=np.r_[mass[:7]/mass[:7].sum()*counts[:7].sum(),
                       mass[7:]/mass[7:].sum()*counts[7:].sum()]
            probabilities.append(pred)
        c,e=sd._correct_incorrect_counts(*probabilities,7)
        observed_c,observed_e=sd._correct_incorrect_counts(a,b,7)
        predicted_auc=sd._auc2_from_counts(c,e)
        predicted=np.r_[probabilities[0],probabilities[1]]
        observed=np.r_[a,b]
        predictive.append(dict(subject=row.subject,condition=row.condition,n_trials=int(observed.sum()),
                               observed_auc=row.auc,fitted_conditional_auc=predicted_auc,
                               auc_prediction_error=predicted_auc-row.auc,
                               confidence_distribution_mae=float(np.abs((c+e)/observed.sum()-(observed_c+observed_e)/observed.sum()).mean()),
                               predicted_count_sum=float(predicted.sum()),
                               max_count_reconstruction_error=float(abs(predicted.sum()-observed.sum())),
                               interpretation='In-sample conditional fit statistic; not out-of-sample validation'))
    pipeline.save_csv(pd.DataFrame(predictive),'metad_predictive_checks.csv')
    pipeline.save_csv(effects[effects.metric.isin(EXTRA+['auc'])], 'metad_condition_contrasts.csv')
    # One common sample and one small-d′ stability rule; no outcome-based trimming.
    common = summary.pivot(index='subject', columns='condition', values=METRICS).dropna().index
    dp = summary.pivot(index='subject', columns='condition', values='d_prime')
    stable = dp.index[(dp.abs() > .10).all(axis=1)]
    sens = []
    positive = dp.index[(dp > .10).all(axis=1)]
    for name, ids in [('all_four_metrics_common_sample',common),('both_abs_dprime_above_0.10',stable),
                      ('both_dprime_above_0.10',positive)]:
        for m in ['accuracy']+METRICS:
            subset = wide.loc[wide.index.isin(ids)]
            if len(subset) > 1:
                result = pipeline.paired_effects(subset,m)
                sens.append(dict(analysis=name,**result))
    pipeline.save_csv(pd.DataFrame(sens),'metad_sensitivity.csv')
    corr, loo = [], []
    for m in METRICS:
        for condition, g in summary.groupby('condition'):
            z = g[['accuracy',m]].replace([np.inf,-np.inf],np.nan).dropna()
            r,p = stats.pearsonr(z.accuracy,z[m]); rs,ps = stats.spearmanr(z.accuracy,z[m])
            corr.append(dict(metric=m,condition=condition,n=len(z),pearson_r=r,pearson_p=p,
                             spearman_rho=rs,spearman_p=ps))
        w = summary.pivot(index='subject',columns='condition',values=m).dropna()
        d = w.zero_gravity-w.gravity
        estimates = (d.sum()-d)/(len(d)-1)
        loo.append(dict(metric=m,n=len(d),full_difference=d.mean(),loo_min=estimates.min(),loo_max=estimates.max(),
                        sign_stable=bool((np.sign(estimates)==np.sign(d.mean())).all())))
    correlations = pd.DataFrame(corr)
    correlations['pearson_p_bh'] = multipletests(correlations.pearson_p,method='fdr_bh')[1]
    pipeline.save_csv(correlations,'accuracy_metacognition_correlations.csv')
    pipeline.save_csv(pd.DataFrame(loo),'metacognition_leave_one_subject_out.csv')
    return summary, effects


def selected_scanpath_contrasts(dsm, duration_rates, seed):
    """Use the first-revision bootstrap seed and contrast order for each metric."""
    intervals = []
    selected = dsm[(dsm.representation == 'duration') & (dsm.permutation_p_fdr < .05)]
    for metric, contrasts in selected.groupby('metric', sort=False):
        rng = np.random.default_rng(seed + 3)
        contrasts = contrasts.sort_values(['permutation_p_fdr', 'dyad'])
        for row in contrasts.itertuples():
            values = duration_rates[
                (duration_rates.metric == metric)
                & (duration_rates.condition == row.condition)
                & (duration_rates.dyad == row.dyad)
                & duration_rates.spam_included
            ]
            high = values.loc[values.metric_value > row.q3, 'rate'].to_numpy()
            low = values.loc[values.metric_value < row.q1, 'rate'].to_numpy()
            draws = (
                rng.choice(low, (3500, len(low)), replace=True).mean(axis=1)
                - rng.choice(high, (3500, len(high)), replace=True).mean(axis=1)
            )
            lo, hi = np.quantile(draws, [.025, .975])
            intervals.append(dict(
                metric=metric, condition=row.condition, dyad=row.dyad,
                n_low=len(low), n_high=len(high),
                low_minus_high=low.mean()-high.mean(), ci95_low=lo, ci95_high=hi,
                p_fdr=row.permutation_p_fdr, interval_method='participant bootstrap 3500',
                bootstrap_seed=seed + 3,
            ))
    return pd.DataFrame(intervals, columns=[
        'metric', 'condition', 'dyad', 'n_low', 'n_high', 'low_minus_high',
        'ci95_low', 'ci95_high', 'p_fdr', 'interval_method', 'bootstrap_seed',
    ])


def extend_dsm(pipeline, events, summary, baseline):
    dsm0, cont0, er0, dr0, totals0 = baseline
    dsms, conts = [dsm0.assign(metric='auc')], [cont0.assign(metric='auc')]
    erows, drows = [er0.assign(metric='auc',metric_value=er0.auc)], [dr0.assign(metric='auc',metric_value=dr0.auc)]
    totals = [totals0.assign(metric='auc')]
    for metric in METRICS[1:]:
        surrogate = summary[['subject','condition',metric]].rename(columns={metric:'auc'})
        er, dr, tq, _ = pipeline.build_dyads(events,surrogate)
        event_res,event_cont = pipeline.analyze_dsm(er,'event')
        duration_res,duration_cont = pipeline.analyze_dsm(dr,'duration')
        dsms.append(pd.concat([event_res,duration_res],ignore_index=True).assign(metric=metric))
        conts.append(pd.concat([event_cont,duration_cont],ignore_index=True).assign(metric=metric))
        erows.append(er.assign(metric=metric,metric_value=er.auc).drop(columns='auc'))
        drows.append(dr.assign(metric=metric,metric_value=dr.auc).drop(columns='auc'))
        totals.append(tq.assign(metric=metric))
        pipeline.write_log(f'{metric}: DSM candidates={len(tq)}, retained={int(tq.spam_included.sum())}')
    dsm, cont = pd.concat(dsms,ignore_index=True), pd.concat(conts,ignore_index=True)
    dsm['permutation_p_fdr_all_metrics'] = dsm.groupby(['representation','condition']).permutation_p.transform(
        lambda p:multipletests(p.fillna(1),method='fdr_bh')[1])
    cont['p_fdr_all_metrics'] = cont.groupby(['representation','condition']).p_value.transform(
        lambda p:multipletests(p.fillna(1),method='fdr_bh')[1])
    pipeline.save_csv(dsm,'dsm_results_by_metric.csv')
    pipeline.save_csv(cont.rename(columns={'auc_slope':'metric_slope'}),'dsm_continuous_by_metric.csv')
    ev, dur = pd.concat(erows,ignore_index=True), pd.concat(drows,ignore_index=True)
    ev = ev.drop(columns='auc',errors='ignore'); dur = dur.drop(columns='auc',errors='ignore')
    pipeline.save_csv(ev,'event_dyad_subject_rates_by_metric.csv')
    pipeline.save_csv(dur,'duration_dyad_subject_rates_by_metric.csv')
    pipeline.save_csv(pd.concat(totals,ignore_index=True),'spam_dsm_qc_by_metric.csv')
    # Full post-selection signatures: recomputed independently for each metric/condition.
    signatures, associations = [], []
    for (metric,condition), g in dsm.query("representation == 'duration'").groupby(['metric','condition']):
        selected = g.loc[g.permutation_p_fdr < .05,'dyad'].tolist()
        if not selected:
            associations.append(dict(metric=metric,condition=condition,n_selected=0,n=0,pearson_r=np.nan,
                                      pearson_p=np.nan,r_squared=np.nan,selected_dyads=''))
            continue
        z = dur[(dur.metric == metric)&(dur.condition == condition)]
        signature = z[z.dyad.isin(selected)].groupby(['subject','metric_value'],as_index=False).rate.sum()
        signature = signature.rename(columns={'rate':'signature_rate'}).assign(metric=metric,condition=condition)
        signatures.append(signature)
        r,p = stats.pearsonr(signature.metric_value,signature.signature_rate)
        associations.append(dict(metric=metric,condition=condition,n_selected=len(selected),n=len(signature),
                                  pearson_r=r,pearson_p=p,r_squared=r*r,selected_dyads=';'.join(selected),
                                  interpretation='descriptive post-selection association'))
    pipeline.save_csv(pd.concat(signatures,ignore_index=True) if signatures else pd.DataFrame(
        columns=['subject','metric_value','signature_rate','metric','condition']), 'scanpath_signatures_by_metric.csv')
    pipeline.save_csv(pd.DataFrame(associations),'scanpath_signature_associations_by_metric.csv')
    pipeline.save_csv(selected_scanpath_contrasts(dsm, dur, pipeline.SEED),
                      'scanpath_selected_contrasts_by_metric.csv')


def coupling_interpretation(pipeline):
    co = pd.read_csv(pipeline.TABLE_DIR/'behavior_mixed_model_coefficients.csv')
    rows=[]
    specs=[('confidence_accuracy_coupling_glmm','conditionzero_gravity:confidence_within',
            'correct','binomial logit','zero/gravity ratio of within-participant confidence slopes'),
           ('confidence_bias_clmm','conditionzero_gravity:correct_f1',
            'confidence_ord','cumulative logit','zero/gravity ratio of correctness-associated proportional odds')]
    for model,term,response,link,estimand in specs:
        z=co[(co.model == model)&(co.term == term)]
        if len(z) != 1:
            raise ValueError(f'Expected one coefficient for {model}/{term}')
        row=z.iloc[0].to_dict()
        row.update(response=response,link=link,estimand=estimand,
                   efficiency_interpretation='This interaction does not estimate meta-d/d or AUC-ratio')
        rows.append(row)
    pipeline.save_csv(pd.DataFrame(rows),'coupling_joint_interpretation.csv')
    reference=pipeline.ROOT/'reference/first_revision_ordinal_coefficients.csv'
    if reference.exists():
        first=pd.read_csv(reference)
        columns=['model','term','odds_ratio','ci_low','ci_high','p_value']
        comparison=first[columns].merge(co[columns],on=['model','term'],validate='one_to_one',suffixes=('_first_revision','_second_revision'))
        pipeline.save_csv(comparison,'ordinal_first_second_revision_comparison.csv')
