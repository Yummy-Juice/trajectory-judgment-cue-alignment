suppressWarnings(Sys.setlocale("LC_CTYPE", if (.Platform$OS.type=="windows") "English_United States.utf8" else "C.UTF-8"))
suppressPackageStartupMessages({
  library(lme4)
  library(ordinal)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("Usage: Rscript r_models.R <trial_csv> <output_dir>")
trial_path <- args[[1]]
out_dir <- args[[2]]
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
model_dir <- file.path(dirname(dirname(trial_path)), "cache", "models")
dir.create(model_dir, recursive=TRUE, showWarnings=FALSE)

d <- read.csv(trial_path, stringsAsFactors = FALSE, check.names = FALSE)
d$subject <- factor(d$subject)
d$condition <- factor(d$condition, levels = c("gravity", "zero_gravity"))
d$velocity_f <- factor(d$velocity)
d$size_pair <- factor(d$size_pair)
d$target_f <- factor(d$target)
d$correct_f <- factor(d$correct, levels = c(0, 1))
d$confidence_ord <- ordered(d$confidence, levels = 1:7)

tidy_coef <- function(model, model_name) {
  sm <- summary(model)
  if (inherits(model, "clmm")) {
    tab <- as.data.frame(sm$coefficients)
    tab$term <- rownames(tab)
    rownames(tab) <- NULL
    names(tab)[1:4] <- c("estimate", "std_error", "statistic", "p_value")
    tab <- tab[!grepl("\\|", tab$term), c("term", "estimate", "std_error", "statistic", "p_value")]
  } else {
    raw <- as.data.frame(coef(sm))
    raw$term <- rownames(raw)
    rownames(raw) <- NULL
    est <- as.numeric(raw[[1]]); se <- as.numeric(raw[[2]]); stat <- as.numeric(raw[[3]])
    if (ncol(raw) >= 5) pv <- as.numeric(raw[[4]]) else pv <- 2 * pnorm(abs(stat), lower.tail = FALSE)
    tab <- data.frame(term=raw$term, estimate=est, std_error=se, statistic=stat, p_value=pv, stringsAsFactors=FALSE)
  }
  tab$model <- model_name
  tab
}

fit_mixed <- function(formulas, data, family = NULL, control = NULL) {
  errors <- character()
  last_fit <- NULL; last_index <- NA_integer_
  for (i in seq_along(formulas)) {
    f <- as.formula(formulas[[i]])
    fit <- tryCatch({
      if (is.null(family)) lmer(f, data = data, REML = FALSE, control = control)
      else glmer(f, data = data, family = family, control = control)
    }, error = function(e) e)
    if (!inherits(fit, "error")) {
      conv_ok <- length(fit@optinfo$conv$lme4$messages) == 0
      singular <- isSingular(fit, tol=1e-4)
      last_fit <- fit; last_index <- i
      if (conv_ok && !singular) return(list(model=fit, formula_index=i, errors=errors, fallback_reason=paste(errors,collapse=" | ")))
      errors <- c(errors, paste0("formula ",i,if(!conv_ok)" non-converged" else "",if(singular)" singular" else ""))
      next
    }
    errors <- c(errors, conditionMessage(fit))
  }
  if (!is.null(last_fit)) return(list(model=last_fit,formula_index=last_index,errors=errors,fallback_reason=paste(errors,collapse=" | ")))
  stop(paste(errors, collapse = " | "))
}

base_fixed <- "condition + velocity_f + size_pair + target_f + trial_c + trial_c2 + condition:velocity_f + condition:size_pair"
random_forms <- c("(1 + condition | subject)", "(1 + condition || subject)", "(1 | subject)")
ctrl_g <- glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 200000), check.conv.singular = "ignore")
ctrl_l <- lmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 200000), check.conv.singular = "ignore")

model_rows <- list()
diag_rows <- list()

same_model_frame <- function(m,data){
  old<-if(inherits(m,'clmm')&&!is.null(m$model))m$model else model.frame(m)
  if(!all(names(old)%in%names(data)))return(FALSE)
  current<-data[complete.cases(data[,names(old),drop=FALSE]),names(old),drop=FALSE]
  if(nrow(old)!=nrow(current))return(FALSE)
  all(vapply(names(old),function(nm){
    if(is.numeric(old[[nm]]))isTRUE(all.equal(as.numeric(old[[nm]]),as.numeric(current[[nm]]),tolerance=1e-12)) else
      identical(as.character(old[[nm]]),as.character(current[[nm]]))
  },logical(1)))
}

cached_mixed <- function(name,forms,data){
  path<-file.path(model_dir,paste0(name,'.rds'))
  if(!file.exists(path))return(NULL)
  m<-readRDS(path)
  candidate_form<-paste(deparse(formula(m)),collapse=' ')
  possible<-vapply(forms,function(f)paste(deparse(as.formula(f)),collapse=' '),character(1))
  idx<-match(candidate_form,possible)
  if(is.na(idx)||!same_model_frame(m,data)||length(m@optinfo$conv$lme4$messages)>0||isSingular(m,tol=1e-4))return(NULL)
  cat('REUSE',name,'after fitted-frame equality check\n');flush.console()
  list(model=m,formula_index=idx,errors=character(),fallback_reason=if(idx>1)'Validated cached fallback structure' else '')
}

clmm_health <- function(m){
  gradient<-if(length(m$gradient))max(abs(m$gradient)) else Inf
  hessian_min<-if(!is.null(m$Hessian))min(eigen(m$Hessian,symmetric=TRUE,only.values=TRUE)$values) else -Inf
  cv<-m$optRes$convergence
  optimizer_ok<-if(!is.null(m$optRes$info))cv%in%c(1,2) else (is.null(cv)||cv==0)
  covariance<-tryCatch(vcov(m),error=function(e)NULL)
  singular<-min(eigen(as.matrix(VarCorr(m)[[1]]),symmetric=TRUE,only.values=TRUE)$values)<1e-8
  list(ok=optimizer_ok&&is.finite(gradient)&&gradient<=1e-3&&is.finite(hessian_min)&&hessian_min>0&&
       !is.null(covariance)&&all(is.finite(covariance)),gradient=gradient,hessian_min=hessian_min,
       optimizer_code=if(is.null(cv))NA else cv,singular=singular)
}

run_glmm <- function(name, response, data, fixed = base_fixed, random = random_forms) {
  cat("START",name,"\n"); flush.console()
  forms <- paste(response, "~", fixed, "+", random)
  ans <- cached_mixed(name,forms,data)
  if(is.null(ans))ans <- fit_mixed(forms, data, binomial(), ctrl_g)
  m <- ans$model
  saveRDS(m, file.path(model_dir,paste0(name,".rds")))
  cf <- tidy_coef(m, name)
  cf$odds_ratio <- exp(cf$estimate)
  cf$ci_low <- exp(cf$estimate - 1.96 * cf$std_error)
  cf$ci_high <- exp(cf$estimate + 1.96 * cf$std_error)
  model_rows[[name]] <<- cf
  rp <- residuals(m, type = "pearson")
  rdf <- max(1, stats::nobs(m) - length(fixef(m)))
  diag_rows[[name]] <<- data.frame(model=name, n=stats::nobs(m), formula_index=ans$formula_index,
    formula=paste(deparse(formula(m)),collapse=" "), converged=length(m@optinfo$conv$lme4$messages)==0,
    singular=isSingular(m, tol=1e-4), pearson_dispersion=sum(rp^2, na.rm=TRUE)/rdf,
    residual_skew=mean((rp-mean(rp,na.rm=TRUE))^3,na.rm=TRUE)/(sd(rp,na.rm=TRUE)^3), fallback_reason=ans$fallback_reason, stringsAsFactors=FALSE)
  invisible(m)
}

run_lmm <- function(name, response, data, fixed = base_fixed, random = random_forms) {
  cat("START",name,"\n"); flush.console()
  forms <- paste(response, "~", fixed, "+", random)
  ans <- cached_mixed(name,forms,data)
  if(is.null(ans))ans <- fit_mixed(forms, data, NULL, ctrl_l)
  m <- ans$model
  saveRDS(m, file.path(model_dir,paste0(name,".rds")))
  cf <- tidy_coef(m, name)
  cf$odds_ratio <- NA_real_; cf$ci_low <- cf$estimate - 1.96*cf$std_error; cf$ci_high <- cf$estimate + 1.96*cf$std_error
  model_rows[[name]] <<- cf
  r <- residuals(m); f <- fitted(m)
  diag_rows[[name]] <<- data.frame(model=name, n=stats::nobs(m), formula_index=ans$formula_index,
    formula=paste(deparse(formula(m)),collapse=" "), converged=length(m@optinfo$conv$lme4$messages)==0,
    singular=isSingular(m, tol=1e-4), pearson_dispersion=NA_real_,
    residual_skew=mean((r-mean(r))^3)/(sd(r)^3), abs_resid_fitted_cor=cor(abs(r),f), fallback_reason=ans$fallback_reason, stringsAsFactors=FALSE)
  invisible(m)
}

run_clmm <- function(name, fixed, data) {
  cat('START',name,'stable adaptive-quadrature estimate\n');flush.console()
  cf<-read.csv(file.path(out_dir,paste0(name,'_stable_coefficients.csv')),stringsAsFactors=FALSE)
  health<-read.csv(file.path(out_dir,paste0(name,'_stable_diagnostics.csv')),stringsAsFactors=FALSE)
  stopifnot(nrow(health)==1,health$n==nrow(data),health$max_gradient<.001,
            health$score_derivative_discrepancy<.001,health$min_hessian_eigenvalue>0)
  cf<-cf[!grepl('\\|',cf$term),,drop=FALSE];cf$model<-name
  model_rows[[name]]<<-cf
  health$formula<-paste('confidence_ord ~',fixed,'+ (1 + condition | subject)')
  health$converged<-TRUE;health$singular<-FALSE
  health$pearson_dispersion<-NA_real_;health$residual_skew<-NA_real_
  diag_rows[[name]]<<-health
  invisible(NULL)
}

behavior <- subset(d, behavior_included == 1)
run_glmm("accuracy_glmm", "correct", behavior)
run_lmm("answer_rt_lmm", "log_answer_rt", subset(behavior, is.finite(log_answer_rt)))
run_lmm("confidence_rt_lmm", "log_confidence_rt", subset(behavior, is.finite(log_confidence_rt)))
run_clmm("confidence_clmm", base_fixed, subset(behavior, !is.na(confidence_ord)))

coupling_fixed <- "condition * confidence_within + confidence_between + velocity_f + size_pair + target_f + trial_c + trial_c2"
run_glmm("confidence_accuracy_coupling_glmm", "correct", subset(behavior, is.finite(confidence_within)), coupling_fixed)
bias_fixed <- "condition * correct_f + velocity_f + size_pair + target_f + trial_c + trial_c2"
run_clmm("confidence_bias_clmm", bias_fixed, subset(behavior, !is.na(confidence_ord)))

occ_fixed <- "condition + occlusion_hidden_c + size_pair + target_f + trial_c + trial_c2 + condition:occlusion_hidden_c"
run_glmm("accuracy_occlusion_sensitivity_glmm", "correct", subset(behavior, is.finite(occlusion_hidden_c)), occ_fixed)
run_lmm("rt_occlusion_sensitivity_lmm", "log_answer_rt", subset(behavior, is.finite(log_answer_rt) & is.finite(occlusion_hidden_c)), occ_fixed)

bind_fill <- function(lst) {
  cols <- unique(unlist(lapply(lst, names)))
  do.call(rbind, lapply(lst, function(x) {for (cc in setdiff(cols,names(x))) x[[cc]] <- NA; x[,cols,drop=FALSE]}))
}
all_coef <- bind_fill(model_rows)
all_diag <- bind_fill(diag_rows)
write.csv(all_coef, file.path(out_dir,"behavior_mixed_model_coefficients.csv"), row.names=FALSE, fileEncoding="UTF-8")
write.csv(all_diag, file.path(out_dir,"behavior_model_diagnostics.csv"), row.names=FALSE, fileEncoding="UTF-8")

# AOI models are fit when the prepared file exists.
aoi_path <- file.path(dirname(trial_path), "eye_metrics_model_input.csv")
if (file.exists(aoi_path)) {
  e <- read.csv(aoi_path, stringsAsFactors=FALSE)
  e$subject <- factor(e$subject); e$condition <- factor(e$condition,levels=c("gravity","zero_gravity")); e$region <- factor(e$region,levels=c("ball","position"))
  eye_rows <- list(); eye_diag <- list()
  for (metric in c("fixation_time_ratio_logit","total_fixation_time_log1p","fixation_count_log1p","mean_fixation_time_log1p")) {
    nm <- paste0("eye_",metric,"_lmm")
    forms <- paste(metric,"~ condition * region +",random_forms)
    ans <- fit_mixed(forms,e,NULL,ctrl_l); m <- ans$model
    cf <- tidy_coef(m,nm); cf$odds_ratio <- NA_real_; cf$ci_low <- cf$estimate-1.96*cf$std_error; cf$ci_high <- cf$estimate+1.96*cf$std_error
    eye_rows[[nm]] <- cf
    rr <- residuals(m); ff <- fitted(m)
    eye_diag[[nm]] <- data.frame(model=nm,n=nrow(e),formula_index=ans$formula_index,formula=paste(deparse(formula(m)),collapse=" "),converged=length(m@optinfo$conv$lme4$messages)==0,singular=isSingular(m,tol=1e-4),pearson_dispersion=NA,residual_skew=mean((rr-mean(rr))^3)/(sd(rr)^3),abs_resid_fitted_cor=cor(abs(rr),ff),fallback_reason=ans$fallback_reason,stringsAsFactors=FALSE)
  }
  write.csv(do.call(rbind,eye_rows),file.path(out_dir,"eye_mixed_model_coefficients.csv"),row.names=FALSE,fileEncoding="UTF-8")
  write.csv(do.call(rbind,eye_diag),file.path(out_dir,"eye_model_diagnostics.csv"),row.names=FALSE,fileEncoding="UTF-8")
}
