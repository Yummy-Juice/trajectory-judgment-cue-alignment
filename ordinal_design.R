suppressWarnings(Sys.setlocale('LC_CTYPE',if(.Platform$OS.type=='windows')'English_United States.utf8' else 'C.UTF-8'))
suppressPackageStartupMessages({library(lme4);library(ordinal)})
args<-commandArgs(trailingOnly=TRUE)
root<-normalizePath(args[[1]],winslash='/',mustWork=TRUE)
kind<-args[[2]]
if(kind=='questionnaire'){
  d<-read.csv(file.path(root,'questionnaire_public/questionnaire_outputs/questionnaire_trial_model_input.csv'),stringsAsFactors=FALSE)
  d<-subset(d,tolower(as.character(behavior_paired_included))%in%c('true','1'))
  d$interpretation<-factor(d$interpretation,levels=c('three_d','billiards'))
  fixed<-'condition * interpretation + velocity_f + size_pair + target_f + trial_c + trial_c2 + condition:velocity_f + condition:size_pair'
  prior<-'interpretation_confidence_clmm'
}else{
  d<-read.csv(file.path(root,'cache/behavior_model_input.csv'),stringsAsFactors=FALSE)
  d<-subset(d,behavior_included==1)
  d$correct_f<-factor(d$correct,levels=c(0,1))
  fixed<-if(kind=='confidence')'condition + velocity_f + size_pair + target_f + trial_c + trial_c2 + condition:velocity_f + condition:size_pair' else
    'condition * correct_f + velocity_f + size_pair + target_f + trial_c + trial_c2'
  prior<-if(kind=='confidence')'confidence_clmm' else 'confidence_bias_clmm'
}
d$subject<-factor(d$subject);d$condition<-factor(d$condition,levels=c('gravity','zero_gravity'))
d$velocity_f<-factor(d$velocity);d$size_pair<-factor(d$size_pair);d$target_f<-factor(d$target)
d$confidence_ord<-ordered(d$confidence,levels=1:7)
vars<-c('subject','confidence_ord',all.vars(as.formula(paste('~',fixed))))
d<-d[complete.cases(d[,vars,drop=FALSE]),,drop=FALSE]
X<-model.matrix(as.formula(paste('~',fixed)),data=d)
stopifnot(qr(X)$rank==ncol(X))
X<-X[,colnames(X)!='(Intercept)',drop=FALSE]
result<-data.frame('__subject'=as.character(d$subject),'__rating'=as.numeric(d$confidence_ord),
                   '__zero'=as.integer(d$condition=='zero_gravity'),X,check.names=FALSE)
prefix<-file.path(root,'cache',paste0('ordinal_',kind))
write.csv(result,paste0(prefix,'_design.csv'),row.names=FALSE,fileEncoding='UTF-8')
initial<-data.frame(term=c(paste0('alpha_',1:6),colnames(X),'random_intercept_sd'),
                    value=c(qlogis((1:6)/7),rep(0,ncol(X)),2))
prior_path<-file.path(root,'cache/models',paste0(prior,'.rds'))
stable_path<-file.path(root,'outputs/tables',paste0(prior,'_stable_coefficients.csv'))
if(file.exists(stable_path)){
  oldcoef<-read.csv(stable_path,stringsAsFactors=FALSE)
  initial$value[1:6]<-oldcoef$estimate[match(paste0(1:6,'|',2:7),oldcoef$term)]
  initial$value[7:(6+ncol(X))]<-oldcoef$estimate[match(colnames(X),oldcoef$term)]
  info<-read.csv(file.path(root,'outputs/tables',paste0(prior,'_stable_diagnostics.csv')),stringsAsFactors=FALSE)
  initial$value[nrow(initial)]<-sqrt(info$random_intercept_variance)
}else if(file.exists(prior_path)){
  old<-readRDS(prior_path)
  initial$value[1:6]<-old$alpha
  initial$value[7:(6+ncol(X))]<-old$beta[colnames(X)]
  initial$value[nrow(initial)]<-sqrt(VarCorr(old)[[1]][1,1])
}else if(kind=='bias'){
  available<-file.path(root,'cache/models/confidence_clmm.rds')
  if(file.exists(available)){
    old<-readRDS(available);initial$value[1:6]<-old$alpha
    initial$value[nrow(initial)]<-sqrt(VarCorr(old)[[1]][1,1])
  }
  coefficients<-read.csv(file.path(root,'outputs/tables/behavior_mixed_model_coefficients.csv'),stringsAsFactors=FALSE)
  oldcoef<-subset(coefficients,model=='confidence_bias_clmm')
  matches<-match(colnames(X),oldcoef$term)
  initial$value[7:(6+ncol(X))]<-ifelse(is.na(matches),0,oldcoef$estimate[matches])
}
write.csv(initial,paste0(prefix,'_initial.csv'),row.names=FALSE,fileEncoding='UTF-8')
cat(kind,'design exported:',nrow(result),'rows,',ncol(X),'fixed coefficients\n')
