"""Reproducible ordinal mixed-model numerical recovery and result export."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from concurrent.futures import ThreadPoolExecutor
from threadpoolctl import threadpool_limits
import ordinal_mixed as engine

MODEL_NAMES={'confidence':'confidence_clmm','bias':'confidence_bias_clmm','questionnaire':'interpretation_confidence_clmm'}


def input_matches(prefix,design,q):
    path=prefix.with_suffix('.npz')
    if not path.exists() or not prefix.with_suffix('.diagnostics.json').exists():return False
    diag=json.loads(prefix.with_suffix('.diagnostics.json').read_text(encoding='utf-8'))
    if diag.get('solver_version')!='adaptive_chain_rule_v2':return False
    old=np.load(path)
    model=engine.OrdinalMixed(pd.read_csv(design,dtype={'__subject':str}),q,3)
    return all(np.array_equal(old[name],getattr(model,name)) for name in ['X','y','group','Z'])


def healthy(d):
    return (d['min_hessian_eigenvalue']>0 and d.get('max_marginal_gradient',np.inf)<.001
            and d.get('max_score_derivative_discrepancy',np.inf)<.001
            and not d.get('parameters_at_bound',True))


def validate_order(root,kind,primary,design):
    """Refit at 21 nodes; assess parameter stability against primary 15-node information."""
    saved=primary.with_suffix('.npz');old=np.load(saved);t=old['parameters']
    path=root/'cache'/f'ordinal_{kind}_quadrature21_validation.json'
    if path.exists():
        prior=json.loads(path.read_text(encoding='utf-8'))
        if prior.get('solver_version')=='adaptive_chain_rule_v2' and np.array_equal(prior.get('primary_parameters',[]),t):
            return prior
    m=engine.OrdinalMixed(pd.read_csv(design,dtype={'__subject':str}),2,21)
    J=np.eye(len(t));J[:6,:6]=0;J[:6,0]=1
    for j in range(1,6):J[j:6,j]=np.exp(t[j])
    inverseJ=np.linalg.inv(J);cov=inverseJ@old['covariance']@inverseJ.T;cov=(cov+cov.T)/2
    ans=minimize(m.objective,t,jac=True,method='BFGS',options={'gtol':1e-5,'maxiter':80,'hess_inv0':cov,'xrtol':1e-12})
    value,score=m.objective(ans.x)
    def derivative(j):
        h=1e-4*(1+abs(ans.x[j]));a=ans.x.copy();b=ans.x.copy();a[j]+=h;b[j]-=h
        return (m.objective(a,False)-m.objective(b,False))/(2*h)
    with ThreadPoolExecutor(max_workers=2) as pool:gradient=np.array(list(pool.map(derivative,range(len(t)))))
    alpha,beta,_,sigma,_=m.unpack(ans.x)
    baseline=np.r_[old['alpha'],old['beta']];values=np.r_[alpha,beta]
    standard_errors=np.sqrt(np.diag(old['covariance'])[:len(values)])
    difference=values-baseline
    result=dict(solver_version='adaptive_chain_rule_v2',kind=kind,purpose='quadrature-order parameter validation; covariance from primary fit',
                nodes=21,nll=float(value),max_marginal_gradient=float(abs(gradient).max()),
                max_score_derivative_discrepancy=float(abs(gradient-score).max()),
                maximum_fixed_parameter_difference=float(abs(difference).max()),
                maximum_difference_in_standard_errors=float(np.max(abs(difference)/standard_errors)),
                primary_parameters=t.tolist(),validation_parameters=ans.x.tolist(),random_covariance=sigma.tolist(),
                optimizer_success=bool(ans.success),message=str(ans.message))
    result['passed']=bool(result['max_marginal_gradient']<.001 and result['max_score_derivative_discrepancy']<.001
                          and result['maximum_difference_in_standard_errors']<.01)
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(f"Ordinal {kind}: 21-node check, maximum parameter change {result['maximum_difference_in_standard_errors']:.5g} SE",flush=True)
    return result


def ensure(root:Path,kind:str,log=print):
    root=Path(root)
    proc=subprocess.run([shutil.which('Rscript'),str(root/'ordinal_design.R'),str(root),kind],
                         cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if proc.returncode:raise RuntimeError('Ordinal design export failed: '+proc.stderr)
    design=root/'cache'/f'ordinal_{kind}_design.csv'
    initial=root/'cache'/f'ordinal_{kind}_initial.csv'
    traces=[];selected=None;random_dimension=2
    with threadpool_limits(limits=1):
        for nodes in [15]:
            prefix=root/'cache'/f'ordinal_{kind}_agq{nodes}'
            if not input_matches(prefix,design,2):
                if prefix.with_suffix('.diagnostics.json').exists():
                    initial=prefix.with_suffix('.diagnostics.json')
                elif (root/'cache'/f'ordinal_{kind}_agq7.diagnostics.json').exists():
                    initial=root/'cache'/f'ordinal_{kind}_agq7.diagnostics.json'
                log(f'Ordinal {kind}: fitting original intercept/condition-slope structure, {nodes} nodes per axis')
                engine.fit(design,initial,prefix,2,nodes)
            diag=json.loads(prefix.with_suffix('.diagnostics.json').read_text(encoding='utf-8'))
            traces.append(dict(kind=kind,random_dimension=2,nodes=nodes,nll=diag['negative_log_likelihood'],
                               max_gradient=diag.get('max_marginal_gradient',np.nan),
                               score_discrepancy=diag.get('max_score_derivative_discrepancy',np.nan),
                               min_hessian_eigenvalue=diag['min_hessian_eigenvalue']))
            initial=prefix.with_suffix('.diagnostics.json')
            if nodes==15 and healthy(diag):selected=prefix;break
        if selected is None:
            raise RuntimeError(f'Ordinal {kind} needs further numerical recovery; retained all fit checkpoints')
    sensitivity=selected
    sensitivity_diag=json.loads(sensitivity.with_suffix('.diagnostics.json').read_text(encoding='utf-8'))
    with threadpool_limits(limits=1):validation=validate_order(root,kind,sensitivity,design)
    if not validation['passed']:raise RuntimeError(f'Ordinal {kind} needs higher-order integration; retained fit and validation checkpoints')
    traces.append(dict(kind=kind,random_dimension=2,nodes=21,nll=validation['nll'],
                       max_gradient=validation['max_marginal_gradient'],score_discrepancy=validation['max_score_derivative_discrepancy'],
                       purpose=validation['purpose'],maximum_difference_in_standard_errors=validation['maximum_difference_in_standard_errors']))
    # Use Laplace integration for the primary model and higher-order
    # quadrature to assess numerical sensitivity.
    selected=root/'cache'/f'ordinal_{kind}_agq1'
    if not input_matches(selected,design,2):
        with threadpool_limits(limits=1):engine.fit(design,sensitivity.with_suffix('.diagnostics.json'),selected,2,1)
    diag=json.loads(selected.with_suffix('.diagnostics.json').read_text(encoding='utf-8'))
    if not healthy(diag):raise RuntimeError(f'Ordinal {kind} primary Laplace fit failed numerical diagnostics')
    traces.append(dict(kind=kind,random_dimension=2,nodes=1,nll=diag['negative_log_likelihood'],
                       max_gradient=diag['max_marginal_gradient'],score_discrepancy=diag['max_score_derivative_discrepancy'],
                       min_hessian_eigenvalue=diag['min_hessian_eigenvalue'],purpose='Primary Laplace approximation with one quadrature node per dimension'))
    sigma=np.asarray(diag['random_covariance'])
    if np.linalg.eigvalsh(sigma).min()/np.linalg.eigvalsh(sigma).max()<1e-4:
        raise RuntimeError(f'Ordinal {kind} random covariance is effectively singular; use recorded intercept fallback')
    name=MODEL_NAMES[kind]
    coefficients=pd.read_csv(selected.with_suffix('.coefficients.csv'))
    coefficients['model']=name
    coefficients.to_csv(root/'outputs/tables'/f'{name}_stable_coefficients.csv',index=False,encoding='utf-8-sig')
    pd.read_csv(sensitivity.with_suffix('.coefficients.csv')).assign(model=name).to_csv(
        root/'outputs/tables'/f'{name}_agq15_sensitivity_coefficients.csv',index=False,encoding='utf-8-sig')
    npz=np.load(selected.with_suffix('.npz'))
    reported_terms=coefficients.term.tolist()
    covariance=pd.DataFrame(npz['covariance'][:len(reported_terms),:len(reported_terms)],index=reported_terms,columns=reported_terms)
    covariance.to_csv(root/'outputs/tables'/f'{name}_stable_covariance.csv',encoding='utf-8-sig')
    diagnostic=dict(model=name,n=diag['n_trials'],n_participants=diag['n_participants'],formula_index=1,
                    converged=True,singular=False,max_gradient=diag['max_marginal_gradient'],
                    score_derivative_discrepancy=diag['max_score_derivative_discrepancy'],
                    min_hessian_eigenvalue=diag['min_hessian_eigenvalue'],
                    quadrature_nodes_per_axis=diag['quadrature_nodes_per_axis'],random_dimension=2,
                    random_intercept_variance=sigma[0,0],random_condition_variance=sigma[1,1],random_covariance=sigma[0,1],
                    optimizer='BFGS; stable adaptive Gauss-Hermite cumulative-logit likelihood with adaptive-transformation derivatives',
                    optimizer_success=diag['success'],optimizer_message=diag['message'],
                    fallback_reason='Ordinal optimizer/Hessian failure. Estimated the specified model with a stable likelihood implementation.',
                    negative_log_likelihood=diag['negative_log_likelihood'])
    pd.DataFrame([diagnostic]).to_csv(root/'outputs/tables'/f'{name}_stable_diagnostics.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(traces).to_csv(root/'outputs/tables'/f'{name}_quadrature_checks.csv',index=False,encoding='utf-8-sig')
    return diagnostic

if __name__=='__main__':
    ensure(Path(__file__).resolve().parent,sys.argv[1])
