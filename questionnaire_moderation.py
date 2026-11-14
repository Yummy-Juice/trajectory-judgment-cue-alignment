"""Reviewer-requested Q14 condition-by-interpretation moderation."""
from pathlib import Path
import json
import shutil
import subprocess
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests


def run(root:Path,reuse=False):
    import ordinal_workflow
    ordinal_workflow.ensure(root,'questionnaire')
    out=root/'questionnaire_public/questionnaire_outputs'
    q=pd.read_csv(root/'questionnaire_public/questionnaire_data_public.csv',dtype={'respondent_id':str})
    labels={'3D motion after collision under zero or microgravity; downward gravity need not be considered':'three_d',
            '2D plane motion after collision, like billiards':'billiards'}
    q['interpretation']=q.q08_original_q14_zero_gravity_understanding.map(labels)
    z=pd.read_csv(out/'questionnaire_all_conditions_metrics.csv',dtype={'subject':str})
    z=z.merge(q[['respondent_id','interpretation']].rename(columns={'respondent_id':'subject'}),on='subject',how='left',validate='many_to_one')
    z=z[z.interpretation.notna()]
    rows=[]; subject_rows=[]
    for metric in ['auc','meta_d','m_ratio','auc_ratio']:
        w=z.pivot(index=['subject','interpretation'],columns='condition',values=metric).dropna().reset_index()
        w['difference']=w.zero_gravity-w.gravity
        w['metric']=metric;subject_rows.append(w)
        a=w.loc[w.interpretation.eq('three_d'),'difference'].to_numpy()
        b=w.loc[w.interpretation.eq('billiards'),'difference'].to_numpy()
        se=np.sqrt(a.var(ddof=1)/len(a)+b.var(ddof=1)/len(b))
        df=(a.var(ddof=1)/len(a)+b.var(ddof=1)/len(b))**2/((a.var(ddof=1)/len(a))**2/(len(a)-1)+(b.var(ddof=1)/len(b))**2/(len(b)-1))
        delta=b.mean()-a.mean(); critical=stats.t.ppf(.975,df)
        test=stats.ttest_ind(b,a,equal_var=False)
        rng=np.random.default_rng(20260713+len(rows)+1900)
        draws=rng.choice(b,(5000,len(b)),replace=True).mean(axis=1)-rng.choice(a,(5000,len(a)),replace=True).mean(axis=1)
        blo,bhi=np.quantile(draws,[.025,.975])
        rows.append(dict(metric=metric,model='Welch test of participant paired condition differences',
                         estimand='(zero-gravity minus gravity) in two-dimensional billiards-like minus 3D interpretation',
                         n_three_d=len(a),n_billiards=len(b),effect=delta,ci95_low=delta-critical*se,ci95_high=delta+critical*se,
                         bootstrap_ci95_low=blo,bootstrap_ci95_high=bhi,p_value=test.pvalue,
                         three_d_condition_difference=a.mean(),billiards_condition_difference=b.mean(),
                         scale='raw difference of differences'))
    pd.concat(subject_rows,ignore_index=True).to_csv(out/'questionnaire_moderation_paired_subject.csv',index=False,encoding='utf-8-sig')
    input_path=out/'questionnaire_trial_model_input.csv'
    rscript=root/'questionnaire_models.R'
    state_path=root/'cache/questionnaire_models_state.json'
    old_state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    prior_input=root/'cache/questionnaire_model_input_completed.csv'
    same_input=False
    if prior_input.exists():
        try:
            pd.testing.assert_frame_equal(pd.read_csv(prior_input),pd.read_csv(input_path),check_dtype=False)
            same_input=True
        except (AssertionError,ValueError):pass
    can_reuse=reuse and same_input and old_state.get('script_mtime_ns')==rscript.stat().st_mtime_ns
    if not can_reuse:
        cmd=[shutil.which('Rscript'),str(rscript),str(root)]
        with (root/'outputs/logs/questionnaire_models_stdout.log').open('w',encoding='utf-8') as outlog, (root/'outputs/logs/questionnaire_models_stderr.log').open('w',encoding='utf-8') as errlog:
            proc=subprocess.run(cmd,cwd=root,stdout=outlog,stderr=errlog)
        if proc.returncode:raise RuntimeError('Questionnaire moderation models failed; inspect outputs/logs/questionnaire_models_stderr.log')
        shutil.copy2(input_path,prior_input)
        state_path.write_text(json.dumps({'script_mtime_ns':rscript.stat().st_mtime_ns,'status':'completed'}),encoding='utf-8')
    coef=pd.read_csv(out/'questionnaire_moderation_model_coefficients.csv')
    diagnostics=pd.read_csv(out/'questionnaire_moderation_model_diagnostics.csv')
    for metric,model in [('accuracy','interpretation_accuracy_glmm'),('confidence','interpretation_confidence_clmm')]:
        term=coef[(coef.model.eq(model))&coef.term.eq('conditionzero_gravity:interpretationbilliards')].iloc[0]
        sample=diagnostics[diagnostics.model.eq(model)].iloc[0]
        rows.append(dict(metric=metric,model=model,estimand='condition-by-Q14-interpretation interaction',
                         n_three_d=int(sample.n_three_d),n_billiards=int(sample.n_billiards),n_trials=int(sample.n_trials),
                         effect=term.odds_ratio,ci95_low=term.ci_low,ci95_high=term.ci_high,p_value=term.p_value,
                         scale='interaction proportional odds ratio' if metric=='confidence' else 'interaction odds ratio'))
    result=pd.DataFrame(rows)
    result['p_bh_all_six']=multipletests(result.p_value.fillna(1),method='fdr_bh')[1]
    result['p_bh_reviewer_primary_three']=np.nan
    primary=result.metric.isin(['accuracy','confidence','auc'])
    result.loc[primary,'p_bh_reviewer_primary_three']=multipletests(result.loc[primary,'p_value'].fillna(1),method='fdr_bh')[1]
    result.to_csv(out/'questionnaire_moderation_summary.csv',index=False,encoding='utf-8-sig')
    return result

if __name__=='__main__':run(Path(__file__).resolve().parent)
