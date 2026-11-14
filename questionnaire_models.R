suppressWarnings(Sys.setlocale("LC_CTYPE", if (.Platform$OS.type=="windows") "English_United States.utf8" else "C.UTF-8"))
suppressPackageStartupMessages({library(lme4);library(ordinal)})
root<-normalizePath(commandArgs(trailingOnly=TRUE)[[1]],winslash='/',mustWork=TRUE)
out<-file.path(root,'questionnaire_public/questionnaire_outputs')
d<-read.csv(file.path(out,'questionnaire_trial_model_input.csv'),stringsAsFactors=FALSE)
d$correct<-ifelse(tolower(as.character(d$correct))=='true',1,ifelse(tolower(as.character(d$correct))=='false',0,suppressWarnings(as.numeric(d$correct))))
d<-subset(d,tolower(as.character(behavior_paired_included))%in%c('true','1'))
d$subject<-factor(d$subject);d$condition<-factor(d$condition,levels=c('gravity','zero_gravity'))
d$interpretation<-factor(d$interpretation,levels=c('three_d','billiards'))
d$velocity_f<-factor(d$velocity);d$size_pair<-factor(d$size_pair);d$target_f<-factor(d$target)
d$confidence_ord<-ordered(d$confidence,levels=1:7)
fixed<-'condition * interpretation + velocity_f + size_pair + target_f + trial_c + trial_c2 + condition:velocity_f + condition:size_pair'
same_frame<-function(m,z){
  old<-model.frame(m)
  if(!all(names(old)%in%names(z)))return(FALSE)
  current<-z[complete.cases(z[,names(old),drop=FALSE]),names(old),drop=FALSE]
  if(nrow(old)!=nrow(current))return(FALSE)
  all(vapply(names(old),function(nm){
    if(is.numeric(old[[nm]]))isTRUE(all.equal(as.numeric(old[[nm]]),as.numeric(current[[nm]]),tolerance=1e-12)) else
      identical(as.character(old[[nm]]),as.character(current[[nm]]))
  },logical(1)))
}
z<-subset(d,!is.na(correct))
random<-c('(1+condition|subject)','(1+condition||subject)','(1|subject)')
cached_path<-file.path(root,'cache/models/interpretation_accuracy_glmm.rds')
cached<-if(file.exists(cached_path))readRDS(cached_path) else NULL
fit<-NULL;reasons<-character()
for(i in seq_along(random)){
  formula<-as.formula(paste('correct ~',fixed,'+',random[[i]]))
  can_reuse<-!is.null(cached)&&identical(paste(deparse(formula(cached)),collapse=' '),paste(deparse(formula),collapse=' '))&&same_frame(cached,z)
  candidate<-if(can_reuse)cached else tryCatch(glmer(formula,data=z,family=binomial(),
    control=glmerControl(optimizer='bobyqa',optCtrl=list(maxfun=200000),check.conv.singular='ignore')),error=function(e)e)
  if(inherits(candidate,'error')){reasons<-c(reasons,conditionMessage(candidate));next}
  converged<-length(candidate@optinfo$conv$lme4$messages)==0;singular<-isSingular(candidate,tol=1e-4)
  if(converged&&!singular){fit<-candidate;chosen<-i;break}
  reasons<-c(reasons,paste('structure',i,'converged',converged,'singular',singular))
}
if(is.null(fit))stop(paste(reasons,collapse=' | '))
saveRDS(fit,cached_path)
tab<-as.data.frame(summary(fit)$coefficients);tab$term<-rownames(tab);rownames(tab)<-NULL
names(tab)[1:4]<-c('estimate','std_error','statistic','p_value')
tab$model<-'interpretation_accuracy_glmm';tab$odds_ratio<-exp(tab$estimate)
tab$ci_low<-exp(tab$estimate-1.96*tab$std_error);tab$ci_high<-exp(tab$estimate+1.96*tab$std_error)
tab<-tab[,c('term','estimate','std_error','statistic','p_value','odds_ratio','ci_low','ci_high','model')]
accuracy_diag<-data.frame(model='interpretation_accuracy_glmm',n_trials=nrow(z),n_participants=nlevels(droplevels(z$subject)),
  n_three_d=length(unique(z$subject[z$interpretation=='three_d'])),n_billiards=length(unique(z$subject[z$interpretation=='billiards'])),
  formula=paste(deparse(formula(fit)),collapse=' '),formula_index=chosen,converged=TRUE,singular=FALSE,
  max_gradient=NA_real_,min_hessian_eigenvalue=NA_real_,fallback_reason=paste(reasons,collapse=' | '),
  optimizer='lme4 bobyqa')
models<-list(accuracy=fit)

stable<-file.path(root,'outputs/tables/interpretation_confidence_clmm_stable_coefficients.csv')
cf<-read.csv(stable,stringsAsFactors=FALSE)
health<-read.csv(file.path(root,'outputs/tables/interpretation_confidence_clmm_stable_diagnostics.csv'),stringsAsFactors=FALSE)
zc<-subset(d,!is.na(confidence_ord))
stopifnot(nrow(health)==1,health$n==nrow(zc),health$max_gradient<.001,
          health$score_derivative_discrepancy<.001,health$min_hessian_eigenvalue>0)
threshold<-grepl('\\|',cf$term)
alpha<-setNames(cf$estimate[threshold],cf$term[threshold]);beta<-setNames(cf$estimate[!threshold],cf$term[!threshold])
covariance<-as.matrix(read.csv(file.path(root,'outputs/tables/interpretation_confidence_clmm_stable_covariance.csv'),row.names=1,check.names=FALSE))
confidence_fit<-structure(list(alpha=alpha,beta=beta,covariance=covariance),class='stableOrdinal')
vcov.stableOrdinal<-function(object,...)object$covariance
models$confidence<-confidence_fit
confidence_diag<-data.frame(model='interpretation_confidence_clmm',n_trials=nrow(zc),n_participants=nlevels(droplevels(zc$subject)),
  n_three_d=length(unique(zc$subject[zc$interpretation=='three_d'])),n_billiards=length(unique(zc$subject[zc$interpretation=='billiards'])),
  formula=paste('confidence_ord ~',fixed,'+ (1 + condition | subject)'),formula_index=1,converged=TRUE,singular=FALSE,
  max_gradient=health$max_gradient,min_hessian_eigenvalue=health$min_hessian_eigenvalue,
  fallback_reason=health$fallback_reason,optimizer=health$optimizer)
write.csv(rbind(tab,cf[!threshold,names(tab)]),file.path(out,'questionnaire_moderation_model_coefficients.csv'),row.names=FALSE,fileEncoding='UTF-8')
write.csv(rbind(accuracy_diag,confidence_diag),file.path(out,'questionnaire_moderation_model_diagnostics.csv'),row.names=FALSE,fileEncoding='UTF-8')
cat('Accuracy and ordinal-confidence moderation models validated.\n');flush.console()

# Fixed-effect standardized predictions at the pooled empirical covariate distribution.
# Random effects are set to zero; the same task-factor distribution is used in all four cells.
template <- d[,c("velocity_f","size_pair","target_f","trial_c","trial_c2"),drop=FALSE]
predictions <- list();contrasts <- list()
for(endpoint in names(models)){
  fit<-models[[endpoint]]
  beta<-if(endpoint=="accuracy") fixef(fit) else fit$beta
  covariance<-if(endpoint=="accuracy") as.matrix(vcov(fit)) else as.matrix(vcov(fit))
  set.seed(20260713L+if(endpoint=="accuracy")3000L else 3001L)
  if(endpoint=='accuracy'){
    draws<-MASS::mvrnorm(1000,beta,covariance)
  }else{
    joint_mean<-c(fit$alpha,beta)
    joint_draws<-MASS::mvrnorm(1000,joint_mean,covariance[names(joint_mean),names(joint_mean),drop=FALSE])
    draws<-joint_draws[,names(beta),drop=FALSE]
    threshold_draws<-joint_draws[,names(fit$alpha),drop=FALSE]
  }
  cells<-list()
  for(group in c("three_d","billiards")) for(condition in c("gravity","zero_gravity")){
    new<-template;new$condition<-factor(condition,levels=levels(d$condition));new$interpretation<-factor(group,levels=levels(d$interpretation))
    X<-model.matrix(as.formula(paste("~",fixed)),new)
    X<-X[,names(beta),drop=FALSE]
    eta<-as.vector(X%*%beta)
    simulated<-X%*%t(draws)
    if(endpoint=="accuracy"){
      expected<-mean(plogis(eta)); values<-colMeans(plogis(simulated))
    }else{
      expected<-mean(1+rowSums(sapply(fit$alpha,function(a)plogis(eta-a))))
      values<-rep(1,ncol(simulated))
      for(j in seq_along(fit$alpha)) values<-values+colMeans(plogis(sweep(simulated,2,threshold_draws[,j],'-')))
    }
    key<-paste(group,condition,sep="_");cells[[key]]<-list(mean=expected,draws=values)
    predictions[[paste(endpoint,key)]]<-data.frame(endpoint=endpoint,interpretation=group,condition=condition,
         estimate=expected,ci95_low=quantile(values,.025),ci95_high=quantile(values,.975),
         interval="1000 multivariate-normal coefficient draws, including confidence thresholds",
         standardization="pooled QC-valid trial covariates; participant random effects zero")
  }
  delta3<-cells$three_d_zero_gravity$mean-cells$three_d_gravity$mean
  deltab<-cells$billiards_zero_gravity$mean-cells$billiards_gravity$mean
  values<-(cells$billiards_zero_gravity$draws-cells$billiards_gravity$draws)-(cells$three_d_zero_gravity$draws-cells$three_d_gravity$draws)
  contrasts[[endpoint]]<-data.frame(endpoint=endpoint,three_d_condition_difference=delta3,billiards_condition_difference=deltab,
       difference_of_differences=deltab-delta3,ci95_low=quantile(values,.025),ci95_high=quantile(values,.975))
}
write.csv(do.call(rbind,predictions),file.path(out,"questionnaire_moderation_standardized_predictions.csv"),row.names=FALSE,fileEncoding="UTF-8")
write.csv(do.call(rbind,contrasts),file.path(out,"questionnaire_moderation_standardized_contrasts.csv"),row.names=FALSE,fileEncoding="UTF-8")
