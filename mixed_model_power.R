suppressWarnings(Sys.setlocale("LC_CTYPE", if (.Platform$OS.type=="windows") "English_United States.utf8" else "C.UTF-8"))
suppressPackageStartupMessages(library(lme4))
args <- commandArgs(trailingOnly=TRUE)
root <- normalizePath(args[[1]],winslash="/",mustWork=TRUE)
B <- if(length(args)>=2) as.integer(args[[2]]) else 100L
first_rep <- if(length(args)>=3)as.integer(args[[3]]) else 1L
last_rep <- if(length(args)>=4)as.integer(args[[4]]) else B
shard <- if(length(args)>=5)args[[5]] else ''
model <- readRDS(file.path(root,"cache/models/confidence_accuracy_coupling_glmm.rds"))
target <- "conditionzero_gravity:confidence_within"
stopifnot(target %in% names(fixef(model)))
folder <- file.path(root,"outputs/simulation")
dir.create(folder,recursive=TRUE,showWarnings=FALSE)
canonical <- file.path(folder,"mixed_model_power_replicates.csv")
shard_folder <- file.path(root,"cache/simulation")
if(nchar(shard)) dir.create(shard_folder,recursive=TRUE,showWarnings=FALSE)
checkpoint <- if(nchar(shard))file.path(shard_folder,paste0('mixed_model_power_replicates_shard_',shard,'.csv')) else canonical
specpath <- file.path(folder,"mixed_model_power_spec.rds")
spec <- list(formula=paste(deparse(formula(model)),collapse=" "), n=nobs(model),
             beta=fixef(model),theta=getME(model,"theta"),target=target,
             odds_ratios=c(1,.90),seed=20260713L)
if(file.exists(specpath)){
  prior <- readRDS(specpath)
  if(!isTRUE(all.equal(prior,spec,tolerance=1e-8))) stop("Simulation model specification changed; use a separate simulation directory")
} else saveRDS(spec,specpath)
results <- if(file.exists(checkpoint)) read.csv(checkpoint,stringsAsFactors=FALSE) else data.frame()
if(nchar(shard)&&file.exists(canonical)){
  base<-read.csv(canonical,stringsAsFactors=FALSE)
  results<-rbind(results,base)
  results<-results[!duplicated(paste(results$scenario,results$replicate)),,drop=FALSE]
}
if(nrow(results)&&nchar(shard))results<-subset(results,replicate>=first_rep&replicate<=last_rep)
for(scenario in seq_along(spec$odds_ratios)){
  ratio <- spec$odds_ratios[[scenario]]
  beta <- fixef(model); beta[[target]] <- log(ratio)
  for(i in if(first_rep<=last_rep)seq.int(first_rep,last_rep) else integer()){
    if(nrow(results)>0 && any(results$scenario==scenario & results$replicate==i)) next
    seed <- 20260713L+scenario*10000L+i
    set.seed(seed)
    start <- proc.time()[[3]]
    warns <- character()
    fit <- tryCatch(withCallingHandlers({
      y <- simulate(model,nsim=1,newparams=list(beta=beta,theta=getME(model,"theta")),re.form=NA)[[1]]
      refit(model,y)
    },warning=function(w){warns<<-c(warns,conditionMessage(w)); invokeRestart("muffleWarning")}),error=function(e)e)
    status <- "error"; est <- se <- p <- low <- high <- NA_real_
    singular <- NA; converged <- FALSE; message <- ""
    if(inherits(fit,"error")) message <- conditionMessage(fit) else {
      est <- fixef(fit)[[target]]; se <- sqrt(diag(vcov(fit)))[[target]]
      low <- est-1.96*se; high <- est+1.96*se
      p <- 2*pnorm(-abs(est/se)); singular <- isSingular(fit,tol=1e-4)
      messages <- fit@optinfo$conv$lme4$messages
      converged <- length(messages)==0 && all(is.finite(c(est,se)))
      status <- if(!converged) "nonconverged" else if(singular) "singular" else "ok"
      message <- paste(c(warns,messages),collapse=" | ")
    }
    row <- data.frame(scenario=scenario,true_or=ratio,replicate=i,seed=seed,
        n_participants=nlevels(getME(model,"flist")[[1]]),n_trials=nobs(model),
        true_log_effect=log(ratio),estimate=est,std_error=se,ci95_low=low,ci95_high=high,
        p_value=p,status=status,converged=converged,singular=singular,
        elapsed_seconds=proc.time()[[3]]-start,message=message)
    results <- rbind(results,row)
    write.csv(results,checkpoint,row.names=FALSE,fileEncoding="UTF-8")
    cat("POWER",scenario,"OR",ratio,"replicate",i,"/",B,"status",status,"seconds",row$elapsed_seconds,"\n"); flush.console()
  }
}
if(!nchar(shard)){
rows <- lapply(split(results,results$scenario),function(g){
  good <- subset(g,status=="ok")
  rejected <- sum(good$p_value<.05,na.rm=TRUE)
  detection <- rejected/nrow(g)
  data.frame(model="confidence_accuracy_coupling_glmm",target=target,true_or=g$true_or[[1]],
      replicates=nrow(g),usable=nrow(good),failed=nrow(g)-nrow(good),
      detection_all_replicates=detection,monte_carlo_se=sqrt(detection*(1-detection)/nrow(g)),
      detection_successful=if(nrow(good)) mean(good$p_value<.05) else NA_real_,
      coverage_95_successful=if(nrow(good)) mean(good$ci95_low<=good$true_log_effect & good$ci95_high>=good$true_log_effect) else NA_real_,
      mean_estimate=mean(good$estimate),bias=mean(good$estimate-good$true_log_effect),
      rmse=sqrt(mean((good$estimate-good$true_log_effect)^2)),
      mean_ci_width=mean(good$ci95_high-good$ci95_low),
      n_participants=g$n_participants[[1]],n_trials=g$n_trials[[1]],
      role="Revision-stage parametric simulation on actual QC-valid design; nuisance parameters estimated from observed data")
})
summary_path<-file.path(root,"outputs/tables/mixed_model_power_summary.csv")
write.csv(do.call(rbind,rows),summary_path,row.names=FALSE,fileEncoding="UTF-8")
}
writeLines(c(paste("Formula:",spec$formula),paste("Target:",target),
             "New subject random effects are generated for each replicate with lme4::simulate(re.form=NA).",
             "Other fixed effects and random-effect covariance are calibrated from the actual fit.",
             "Each simulated outcome is refitted using the fitted model's same formula and estimation method.",
             "Wald two-sided alpha=.05; nonconverged/singular/error fits are counted separately and in the total denominator.",
             "This analysis evaluates the completed design and does not supply an a-priori recruitment rationale."),
           file.path(folder,"mixed_model_power_specification.txt"))
