"""Stable adaptive-quadrature cumulative-logit mixed-model likelihood.

Numerical recovery for ordinal fits whose original optimizer/Hessian failed.
The likelihood retains ordered thresholds and Gaussian participant effects.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
from scipy.special import expit,log_expit,logsumexp
from scipy.optimize import minimize
from scipy import stats
from numpy.polynomial.hermite import hermgauss


class OrdinalMixed:
    def __init__(self,data:pd.DataFrame,q:int=2,nodes:int=11):
        self.features=[c for c in data if not c.startswith('__')]
        order=np.argsort(data['__subject'].to_numpy(),kind='stable')
        d=data.iloc[order].reset_index(drop=True)
        self.X=d[self.features].to_numpy(float)
        self.y=d['__rating'].to_numpy(int)-1
        _,self.group=np.unique(d['__subject'].astype(str),return_inverse=True)
        self.start=np.r_[0,np.flatnonzero(np.diff(self.group))+1]
        self.S=len(self.start);self.N=len(d);self.P=self.X.shape[1];self.Q=q
        self.Z=np.ones((self.N,q))
        if q==2:self.Z[:,1]=d['__zero'].to_numpy(float)
        x,w=hermgauss(nodes)
        if q==1:self.grid=x[:,None];self.logw=np.log(w)
        else:
            xx,yy=np.meshgrid(x,x,indexing='ij');ww,zz=np.meshgrid(w,w,indexing='ij')
            self.grid=np.column_stack([xx.ravel(),yy.ravel()]);self.logw=np.log(ww.ravel())+np.log(zz.ravel())
        self.nodes=nodes;self.last_mode=None

    def unpack(self,t):
        alpha=np.r_[t[0],t[0]+np.cumsum(np.exp(t[1:6]))]
        beta=t[6:6+self.P];c=t[6+self.P:]
        L=np.array([[np.exp(c[0])]]) if self.Q==1 else np.array([[np.exp(c[0]),0],[c[1],np.exp(c[2])]])
        sigma=L@L.T
        return alpha,beta,L,sigma,np.linalg.inv(sigma)

    def prob(self,eta,alpha):
        edges=np.r_[-np.inf,alpha,np.inf]
        upper,lower=edges[self.y+1],edges[self.y]
        gap=upper-lower
        if eta.ndim==2:upper=upper[:,None];lower=lower[:,None];gap=gap[:,None]
        u=upper-eta;l=lower-eta
        logp=log_expit(u)+log_expit(-l)+np.log(-np.expm1(-gap))
        su,sl=expit(u),expit(l)
        score=su+sl-1
        hess=su*expit(-u)+sl*expit(-l)
        return logp,score,hess,u,l,gap

    def reduce(self,values):return np.add.reduceat(values,self.start,axis=0)

    def modes(self,xbeta,alpha,inv):
        b=np.zeros((self.S,self.Q))
        for iteration in range(100):
            eta=xbeta+np.einsum('ij,ij->i',self.Z,b[self.group])
            logp,score,hess,*_=self.prob(eta,alpha)
            g=self.reduce(score[:,None]*self.Z)-b@inv
            H=self.reduce(hess[:,None,None]*self.Z[:,:,None]*self.Z[:,None,:])+inv
            if np.max(np.abs(g))<1e-8:break
            step=np.linalg.solve(H,g[...,None])[...,0]
            step/=np.maximum(1,np.max(np.abs(step),axis=1,keepdims=True)/5)
            old=self.reduce(logp)-.5*np.einsum('si,ij,sj->s',b,inv,b)
            factor=np.ones(self.S)
            for _ in range(30):
                candidate=b+step*factor[:,None]
                ep=xbeta+np.einsum('ij,ij->i',self.Z,candidate[self.group])
                lp=self.prob(ep,alpha)[0]
                value=self.reduce(lp)-.5*np.einsum('si,ij,sj->s',candidate,inv,candidate)
                bad=value<old-1e-9
                if not bad.any():break
                factor[bad]*=.5
            b=candidate
        else:raise RuntimeError('Conditional participant-mode Newton iterations did not converge')
        return b,H,float(np.max(np.abs(g)))

    def objective(self,t,gradient=True,chain=True):
        if not np.all(np.isfinite(t)):
            return (1e100,np.zeros_like(t)) if gradient else 1e100
        alpha,beta,L,sigma,inv=self.unpack(t)
        xbeta=self.X@beta
        try:
            if np.linalg.cond(sigma)>1e11:raise RuntimeError('Numerically singular covariance proposal')
            mode,H,mode_gradient=self.modes(xbeta,alpha,inv)
        except (RuntimeError,np.linalg.LinAlgError):
            return (1e100,np.zeros_like(t)) if gradient else 1e100
        C=np.linalg.cholesky(np.linalg.inv(H))
        b=mode[:,None,:]+np.sqrt(2)*np.einsum('sij,kj->ski',C,self.grid)
        eta=xbeta[:,None]+np.einsum('nq,nkq->nk',self.Z,b[self.group])
        logp,score,_,u,l,gap=self.prob(eta,alpha)
        likelihood=self.reduce(logp)
        lp=-.5*np.einsum('ski,ij,skj->sk',b,inv,b)-np.log(np.diag(L)).sum()-.5*self.Q*np.log(2*np.pi)
        integrand=likelihood+lp+self.logw[None,:]+(self.grid**2).sum(axis=1)[None,:]
        lognorm=logsumexp(integrand,axis=1)
        logdetH=np.linalg.slogdet(H)[1]
        loglike=float(np.sum(lognorm+.5*self.Q*np.log(2)-.5*logdetH))
        if not gradient:return -loglike
        weights=np.exp(integrand-lognorm[:,None])
        rowweights=weights[self.group]
        eta_score=np.sum(rowweights*score,axis=1)
        gbeta=self.X.T@eta_score
        ga=np.zeros(6)
        with np.errstate(over='ignore'):
            reciprocal=1/np.expm1(gap)
        for j in range(6):
            upper=self.y==j;lower=self.y==j+1
            ga[j]=np.sum(rowweights[upper]*(expit(-u[upper])+reciprocal[upper]))-np.sum(rowweights[lower]*(expit(l[lower])+reciprocal[lower]))
        galpha=np.r_[ga.sum(),np.exp(t[1:6])*np.cumsum(ga[:0:-1])[::-1]]
        Ebb=np.einsum('sk,ski,skj->ij',weights,b,b)
        GL=(inv@Ebb@inv-self.S*inv)@L
        gc=np.array([GL[0,0]*L[0,0]]) if self.Q==1 else np.array([GL[0,0]*L[0,0],GL[1,0],GL[1,1]*L[1,1]])
        self.last_mode=dict(max_gradient=mode_gradient)
        result=np.r_[galpha,gbeta,gc]
        if chain:
            # The finite quadrature rule changes with the posterior mode and scale.
            # Include that derivative rather than treating a finite-node Fisher score as exact.
            node_score=self.reduce(score[:,:,None]*self.Z[:,None,:])-np.einsum('ij,skj->ski',inv,b)
            for j in range(len(t)):
                h=1e-4*(1+abs(t[j]));plus=t.copy();minus=t.copy();plus[j]+=h;minus[j]-=h
                ap,bp,_,_,ip=self.unpack(plus);am,bm,_,_,im=self.unpack(minus)
                mp,Hp,_=self.modes(self.X@bp,ap,ip);mm,Hm,_=self.modes(self.X@bm,am,im)
                Cp=np.linalg.cholesky(np.linalg.inv(Hp));Cm=np.linalg.cholesky(np.linalg.inv(Hm))
                db=(mp-mm)[:,None,:]/(2*h)+np.sqrt(2)*np.einsum('sij,kj->ski',(Cp-Cm)/(2*h),self.grid)
                djac=-.5*(np.linalg.slogdet(Hp)[1]-np.linalg.slogdet(Hm)[1])/(2*h)
                result[j]+=np.sum(djac+np.sum(weights*np.sum(node_score*db,axis=2),axis=1))
        return -loglike,-result


def initial_parameters(model,initial):
    if 'parameters' in initial:
        if initial.get('features',model.features)!=model.features or initial.get('random_dimension',model.Q)!=model.Q:
            raise ValueError('Warm-start feature/random-effect specification differs')
        return np.asarray(initial['parameters'],float)
    alpha=np.array([initial.get(f'alpha_{j+1}',stats.logistic.ppf((j+1)/7)) for j in range(6)])
    beta=np.array([initial.get(name,0.) for name in model.features])
    sigma=float(initial.get('random_intercept_sd',2.0))
    cov=[np.log(sigma)] if model.Q==1 else [np.log(sigma),0.,np.log(.5)]
    return np.r_[alpha[0],np.log(np.diff(alpha)),beta,cov]


def fit(input_path:Path,initial_path:Path,prefix:Path,q=2,nodes=11):
    data=pd.read_csv(input_path,dtype={'__subject':str})
    ini=(pd.read_csv(initial_path).set_index('term').value.to_dict() if initial_path.suffix=='.csv' else
         json.loads(initial_path.read_text(encoding='utf-8'))) if initial_path.exists() else {}
    model=OrdinalMixed(data,q,nodes)
    t=initial_parameters(model,ini)
    bounds=[(-25,15)]+[(-5,4)]*5+[(-15,15)]*model.P+([(-5,3)] if q==1 else [(-5,3),(-15,15),(-5,3)])
    elapsed=time.monotonic();counter=[0]
    # Reuse curvature from the warm fit, or compute a starting preconditioner.
    warm_npz=Path(str(initial_path).removesuffix('.diagnostics.json')+'.npz')
    if initial_path.name.endswith('.diagnostics.json') and warm_npz.exists():
        previous=np.load(warm_npz);J=np.eye(len(t));J[:6,:6]=0;J[:6,0]=1
        for j in range(1,6):J[j:6,j]=np.exp(t[j])
        inverseJ=np.linalg.inv(J);initial_cov=inverseJ@previous['covariance']@inverseJ.T
    else:
        columns=[]
        for j in range(len(t)):
            h=1e-4*(1+abs(t[j]));a=t.copy();b=t.copy();a[j]+=h;b[j]-=h
            columns.append((model.objective(a,chain=False)[1]-model.objective(b,chain=False)[1])/(2*h))
        H0=np.column_stack(columns);H0=(H0+H0.T)/2
        eigen,vectors=np.linalg.eigh(H0);initial_cov=(vectors/np.maximum(eigen,.1))@vectors.T
    initial_cov=(initial_cov+initial_cov.T)/2
    def callback(x):
        counter[0]+=1
        if counter[0]%10==0:
            value,grad=model.objective(x)
            record=dict(iteration=counter[0],nll=value,max_gradient=float(abs(grad).max()),elapsed=time.monotonic()-elapsed,
                        q=q,nodes=nodes,parameters=x.tolist())
            prefix.with_suffix('.progress.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
            print(f'Ordinal {prefix.name}: iteration {counter[0]}, nll={value:.4f}, maxgrad={abs(grad).max():.5g}',flush=True)
    ans=minimize(model.objective,t,jac=True,method='BFGS',callback=callback,
                 options={'maxiter':250,'gtol':1e-5,'xrtol':1e-12,'hess_inv0':initial_cov})
    t=ans.x;value,grad=model.objective(t)
    # Curvature from the analytic likelihood score; node-gradient approximation is checked independently.
    def curvature_column(j):
        h=1e-4*(1+abs(t[j]));a=t.copy();b=t.copy();a[j]+=h;b[j]-=h
        va,ga=model.objective(a);vb,gb=model.objective(b)
        return (ga-gb)/(2*h),(va-vb)/(2*h)
    with ThreadPoolExecutor(max_workers=2) as pool:
        curvature=list(pool.map(curvature_column,range(len(t))))
    columns=[x[0] for x in curvature];numerical_gradient=[x[1] for x in curvature]
    Hess=np.column_stack(columns);Hess=(Hess+Hess.T)/2
    eigen=np.linalg.eigvalsh(Hess)
    alpha,beta,L,sigma,_=model.unpack(t)
    covariance=np.linalg.inv(Hess)
    # Transform ordered-gap coordinates to the reported alpha/beta coordinates.
    J=np.eye(len(t));J[:6,:6]=0;J[:6,0]=1
    for j in range(1,6):J[j:6,j]=np.exp(t[j])
    transformed_cov=J@covariance@J.T
    values=np.r_[alpha,beta];ses=np.sqrt(np.diag(transformed_cov)[:len(values)])
    terms=[f'{i}|{i+1}' for i in range(1,7)]+model.features
    coefficients=pd.DataFrame(dict(term=terms,estimate=values,std_error=ses,statistic=values/ses,
                                  p_value=2*stats.norm.sf(abs(values/ses))))
    coefficients['odds_ratio']=np.exp(coefficients.estimate)
    coefficients['ci_low']=np.exp(coefficients.estimate-1.96*coefficients.std_error)
    coefficients['ci_high']=np.exp(coefficients.estimate+1.96*coefficients.std_error)
    coefficients.to_csv(prefix.with_suffix('.coefficients.csv'),index=False,encoding='utf-8-sig')
    # Finite-difference checks use the marginal log likelihood, independently of the score.
    checks=[]
    for j in [0,6,len(t)-1]:
        h=2e-5*(1+abs(t[j]));a=t.copy();b=t.copy();a[j]+=h;b[j]-=h
        numerical=(model.objective(a,False)-model.objective(b,False))/(2*h)
        checks.append(dict(index=j,analytic=float(grad[j]),numerical=float(numerical),absolute_error=float(abs(grad[j]-numerical))))
    result=dict(success=bool(ans.success),message=str(ans.message),iterations=int(ans.nit),n_trials=model.N,
                solver_version='adaptive_chain_rule_v2',
                n_participants=model.S,random_dimension=q,quadrature_nodes_per_axis=nodes,
                negative_log_likelihood=value,max_gradient=float(abs(grad).max()),min_hessian_eigenvalue=float(eigen.min()),
                max_marginal_gradient=float(np.max(np.abs(numerical_gradient))),
                max_score_derivative_discrepancy=float(np.max(np.abs(grad-numerical_gradient))),
                parameters_at_bound=bool(any(x<=lo+1e-4 or x>=hi-1e-4 for x,(lo,hi) in zip(t,bounds))),
                hessian_condition_number=float(eigen.max()/eigen.min()),random_covariance=sigma.tolist(),
                conditional_mode_gradient=model.last_mode['max_gradient'],gradient_checks=checks,
                elapsed_seconds=time.monotonic()-elapsed,parameters=t.tolist(),features=model.features,
                method='stable cumulative-logit Gaussian random-effects adaptive Gauss-Hermite quadrature')
    prefix.with_suffix('.diagnostics.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    np.savez_compressed(prefix.with_suffix('.npz'),parameters=t,covariance=transformed_cov,alpha=alpha,beta=beta,
                        X=model.X,y=model.y,group=model.group,Z=model.Z)
    print(json.dumps({k:v for k,v in result.items() if k not in ['parameters','features']},indent=2),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('initial',type=Path);p.add_argument('prefix',type=Path)
    p.add_argument('--random-dimension',type=int,default=2);p.add_argument('--nodes',type=int,default=11)
    from threadpoolctl import threadpool_limits
    a=p.parse_args()
    with threadpool_limits(limits=1):fit(a.input,a.initial,a.prefix,a.random_dimension,a.nodes)
