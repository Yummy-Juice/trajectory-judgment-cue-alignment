"""Bounded, checkpointed design simulations and sparse-count recovery checks."""
from __future__ import annotations
import json
import subprocess
import shutil
import os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import brentq
import metacognition as sd

SEED=20260713


def design_sensitivity(root: Path):
    effects=pd.read_csv(root/'outputs/tables/paired_condition_effects.csv')
    rows=[]
    for row in effects.itertuples():
        n=int(row.n)
        rng=np.random.default_rng(SEED+1200+n)
        for dz in [0,.10,.20,.30]:
            x=rng.normal(dz,1,(5000,n))
            means=x.mean(axis=1); ses=x.std(axis=1,ddof=1)/np.sqrt(n)
            critical=stats.t.ppf(.975,n-1)
            rejected=np.abs(means/ses)>critical
            covered=(means-critical*ses<=dz)&(means+critical*ses>=dz)
            estimate=float(rejected.mean())
            nc=dz*np.sqrt(n)
            exact=stats.nct.sf(critical,n-1,-nc)+stats.nct.sf(critical,n-1,nc)
            power=lambda d:stats.nct.sf(critical,n-1,-d*np.sqrt(n))+stats.nct.sf(critical,n-1,d*np.sqrt(n))
            rows.append(dict(metric=row.metric,n=n,assumed_dz=dz,replicates=5000,alpha=.05,
                simulated_detection=estimate,monte_carlo_se=np.sqrt(estimate*(1-estimate)/5000),
                analytic_power=exact,coverage_95=covered.mean(),mean_ci_width=float((2*critical*ses).mean()),
                detectable_dz_80=brentq(lambda d:power(d)-.8,.0001,.5),
                role='Design sensitivity conditional on endpoint-specific valid sample sizes'))
    pd.DataFrame(rows).to_csv(root/'outputs/tables/paired_design_sensitivity.csv',index=False,encoding='utf-8-sig')


def generate_counts(rng,d,m,distances,n=36):
    """Type-1 choices followed by confidence conditional on S and R in the meta-d model."""
    criterion=0.
    thresholds=np.r_[-np.inf,-np.asarray(distances)[::-1],0,np.asarray(distances),np.inf]
    a=np.zeros(14); b=np.zeros(14)
    for stimulus,counts in [(0,a),(1,b)]:
        mu=(stimulus-.5)*d
        n_response0=int(rng.binomial(n//2,stats.norm.cdf(criterion-mu)))
        meta_mu=(stimulus-.5)*m*d
        probs=np.diff(stats.norm.cdf(thresholds-meta_mu))
        for start,number in [(0,n_response0),(7,n//2-n_response0)]:
            p=probs[start:start+7]; p=p/p.sum()
            counts[start:start+7]=rng.multinomial(number,p)
    return a,b


def recovery(root:Path,log=print):
    folder=root/'outputs/simulation'; folder.mkdir(parents=True,exist_ok=True)
    path=folder/'metad_recovery_replicates.csv'
    old=pd.read_csv(path) if path.exists() else pd.DataFrame()
    rows=old.to_dict('records')
    completed={(r['scenario'],int(r['replicate'])) for r in rows}
    scenarios=[('balanced_d08_M06',.8,.6,[.15,.35,.60,.90,1.25,1.7]),
               ('balanced_d12_M06',1.2,.6,[.15,.35,.60,.90,1.25,1.7]),
               ('highconf_d08_M06',.8,.6,[.02,.04,.08,.12,.18,.30]),
               ('highconf_d12_M06',1.2,.6,[.02,.04,.08,.12,.18,.30])]
    for sid,(name,d,m,distances) in enumerate(scenarios):
        for replicate in range(200):
            if (name,replicate) in completed:continue
            seed=SEED+100000+sid*1000+replicate
            a,b=generate_counts(np.random.default_rng(seed),d,m,distances)
            fit=sd.fit_meta_d_mle(a,b)
            fit.pop('relative_criteria',None)
            rows.append(dict(scenario=name,replicate=replicate,seed=seed,true_d=d,true_meta_d=d*m,
                             true_m_ratio=m,n_trials=36,**fit))
            if replicate%50==49:
                pd.DataFrame(rows).to_csv(path,index=False,encoding='utf-8-sig')
                log(f'MLE recovery {name}: {replicate+1}/200')
    full=pd.DataFrame(rows)
    full.to_csv(path,index=False,encoding='utf-8-sig')
    summaries=[]
    for scenario,g in full.groupby('scenario'):
        valid=g[g.status.eq('ok')]
        for metric,true_col in [('d_prime','true_d'),('meta_d','true_meta_d'),('m_ratio','true_m_ratio')]:
            z=valid[[metric,true_col]].dropna()
            error=z[metric]-z[true_col]
            summaries.append(dict(scenario=scenario,metric=metric,replicates=len(g),valid_fits=len(valid),
                                   failed_fits=len(g)-len(valid),true_value=g[true_col].iloc[0],
                                   mean_estimate=z[metric].mean(),median_estimate=z[metric].median(),
                                   bias=error.mean(),rmse=np.sqrt((error**2).mean()),
                                   estimate_q025=z[metric].quantile(.025),estimate_q975=z[metric].quantile(.975),
                                   role='individual sparse-count recovery; quantiles are sampling spread, not confidence intervals'))
    pd.DataFrame(summaries).to_csv(root/'outputs/tables/metad_parameter_recovery.csv',index=False,encoding='utf-8-sig')


def confidence_binning_sensitivity(root:Path,log=print):
    raw=pd.read_csv(root/'outputs/tables/metad_input_counts.csv',dtype={'subject':str})
    fits=pd.read_csv(root/'outputs/tables/metad_mle_subject_condition.csv',dtype={'subject':str})
    eligible=set(map(tuple,fits.loc[fits.status.ne('qc_failed'),['subject','condition']].to_numpy()))
    raw['coarse_confidence']=raw.confidence.map({1:1,2:1,3:1,4:2,5:2,6:3,7:3})
    records=[]
    for key,g in raw.groupby(['subject','condition']):
        if key not in eligible:continue
        arrays=[]
        for stimulus in [0,1]:
            a=np.zeros(6)
            for row in g[g.stimulus.eq(stimulus)].itertuples():
                idx=3-row.coarse_confidence if row.response==0 else 3+row.coarse_confidence-1
                a[idx]+=row.count
            arrays.append(a)
        fit=sd.fit_meta_d_mle(*arrays);fit.pop('relative_criteria',None)
        records.append(dict(subject=key[0],condition=key[1],**fit))
    df=pd.DataFrame(records)
    df.to_csv(root/'outputs/tables/metad_three_level_sensitivity_subject.csv',index=False,encoding='utf-8-sig')
    import run_analysis as original
    rows=[]
    for metric in ['d_prime','meta_d','m_ratio']:
        w=df.pivot(index='subject',columns='condition',values=metric)
        w.columns=[f'{metric}_{c}' for c in w.columns]
        rows.append(dict(analysis='fixed 1-3/4-5/6-7 confidence pooling',**original.paired_effects(w,metric)))
    paired_coarse=df.pivot(index='subject',columns='condition',values=['meta_d','m_ratio']).dropna().index
    for metric in ['meta_d','m_ratio']:
        w=fits[fits.subject.isin(paired_coarse)].pivot(index='subject',columns='condition',values=metric)
        w.columns=[f'{metric}_{c}' for c in w.columns]
        rows.append(dict(analysis='original seven levels on coarse-finite common sample',**original.paired_effects(w,metric)))
    pd.DataFrame(rows).to_csv(root/'outputs/tables/metad_three_level_sensitivity.csv',index=False,encoding='utf-8-sig')
    log('Fixed three-level confidence sensitivity completed')


def mixed_model_power(root:Path,log=print):
    folder=root/'outputs/simulation'
    folder.mkdir(parents=True,exist_ok=True)
    shard_folder=root/'cache/simulation'
    shard_folder.mkdir(parents=True,exist_ok=True)
    (root/'outputs/logs').mkdir(parents=True,exist_ok=True)
    config=json.loads((root/'config.json').read_text(encoding='utf-8'))
    requested_workers=int(config.get('design_simulations',{}).get('parallel_workers',4))
    workers=min(requested_workers,max(1,(os.cpu_count() or 2)//2))
    budget=100
    partitions=np.array_split(np.arange(1,budget+1),workers)
    processes=[];handles=[];records=[]
    for i,part in enumerate(partitions,1):
        shard=f'{i:02d}'
        cmd=[shutil.which('Rscript'),str(root/'mixed_model_power.R'),str(root),str(budget),str(int(part[0])),str(int(part[-1])),shard]
        stdout=(root/f'outputs/logs/power_shard_{shard}_stdout.log').open('w',encoding='utf-8')
        stderr=(root/f'outputs/logs/power_shard_{shard}_stderr.log').open('w',encoding='utf-8')
        handles.extend([stdout,stderr])
        process=subprocess.Popen(cmd,cwd=root,stdout=stdout,stderr=stderr)
        processes.append(process)
        records.append(dict(shard=shard,pid=process.pid,first_replicate=int(part[0]),last_replicate=int(part[-1]),status='running'))
    state=shard_folder/'mixed_model_power_jobs.json'
    state.write_text(json.dumps(records,indent=2),encoding='utf-8')
    for process,record in zip(processes,records):
        record['return_code']=process.wait()
        record['status']='completed' if process.returncode==0 else 'failed'
        state.write_text(json.dumps(records,indent=2),encoding='utf-8')
        log(f"Mixed-model simulation shard {record['shard']}: {record['status']}")
    for handle in handles:handle.close()
    if any(p.returncode for p in processes):raise RuntimeError('A mixed-model simulation shard failed; inspect power_shard logs and retain checkpoints')
    pieces=[pd.read_csv(path) for record in records
            if (path:=shard_folder/f"mixed_model_power_replicates_shard_{record['shard']}.csv").exists()]
    canonical=folder/'mixed_model_power_replicates.csv'
    if canonical.exists():pieces.append(pd.read_csv(canonical))
    all_rows=pd.concat(pieces,ignore_index=True).sort_values(['scenario','replicate'])
    all_rows=all_rows.drop_duplicates(['scenario','replicate'])
    expected={(s,r) for s in [1,2] for r in range(1,budget+1)}
    if set(map(tuple,all_rows[['scenario','replicate']].to_numpy()))!=expected:
        raise RuntimeError('Simulation replicate keys do not cover the frozen scenario/replicate plan')
    all_rows.to_csv(canonical,index=False,encoding='utf-8-sig')
    summaries=[]
    for scenario,g in all_rows.groupby('scenario'):
        good=g[g.status.eq('ok')]
        rejection=float((good.p_value<.05).sum()/len(g))
        z=stats.norm.ppf(.975);denominator=1+z*z/len(g)
        center=(rejection+z*z/(2*len(g)))/denominator
        radius=z/denominator*np.sqrt(rejection*(1-rejection)/len(g)+z*z/(4*len(g)**2))
        error=good.estimate-good.true_log_effect
        summaries.append(dict(model='confidence_accuracy_coupling_glmm',target='conditionzero_gravity:confidence_within',
            true_or=g.true_or.iloc[0],replicates=len(g),usable=len(good),failed=len(g)-len(good),
            detection_all_replicates=rejection,monte_carlo_se=np.sqrt(rejection*(1-rejection)/len(g)),
            monte_carlo_ci95_low=center-radius,monte_carlo_ci95_high=center+radius,
            detection_successful=float((good.p_value<.05).mean()),
            coverage_95_successful=float(((good.ci95_low<=good.true_log_effect)&(good.ci95_high>=good.true_log_effect)).mean()),
            mean_estimate=good.estimate.mean(),bias=error.mean(),rmse=np.sqrt((error**2).mean()),
            mean_ci_width=(good.ci95_high-good.ci95_low).mean(),n_participants=g.n_participants.iloc[0],n_trials=g.n_trials.iloc[0],
            role='Parametric simulation on the QC-valid trial design with fitted nuisance parameters'))
    pd.DataFrame(summaries).to_csv(root/'outputs/tables/mixed_model_power_summary.csv',index=False,encoding='utf-8-sig')


def run(root:Path,log=print):
    design_sensitivity(root)
    recovery(root,log)
    confidence_binning_sensitivity(root,log)
    log('Running checkpointed mixed-model power simulations (100 per scenario; configured independent shards)')
    mixed_model_power(root,log)
    log('Design sensitivity, MLE recovery, and mixed-model power simulations completed')

if __name__=='__main__':run(Path(__file__).resolve().parent)
