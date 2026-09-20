suppressPackageStartupMessages({
  library(lme4)
  library(ordinal)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("Usage: Rscript r_models.R <trial_csv> <output_dir>")
trial_path <- args[[1]]
out_dir <- args[[2]]
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

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

run_glmm <- function(name, response, data, fixed = base_fixed, random = random_forms) {
  cat("START",name,"\n"); flush.console()
  forms <- paste(response, "~", fixed, "+", random)
  ans <- fit_mixed(forms, data, binomial(), ctrl_g)
  m <- ans$model
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
  ans <- fit_mixed(forms, data, NULL, ctrl_l)
  m <- ans$model
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
  cat("START",name,"\n"); flush.console()
  full_formula <- as.formula(paste("confidence_ord ~",fixed,"+ (1 + condition | subject)"))
  int_formula <- as.formula(paste("confidence_ord ~",fixed,"+ (1 | subject)"))
  errs <- character(); m <- NULL; idx <- NA_integer_
  z <- tryCatch(clmm(full_formula, data=data, Hess=TRUE, nAGQ=1,
                     control=clmm.control(maxIter=200, gradTol=1e-4)), error=function(e)e)
  if (!inherits(z,"error") && (is.null(z$convergence) || is.null(z$convergence$code) || z$convergence$code==0)) {m <- z; idx <- 1}
  else errs <- c(errs, if(inherits(z,"error")) conditionMessage(z) else "full random-slope CLMM non-converged")
  if (is.null(m)) {
    z <- tryCatch(clmm(int_formula, data=data, Hess=TRUE, nAGQ=1,
                       control=clmm.control(maxIter=200, gradTol=1e-4)), error=function(e)e)
    if (!inherits(z,"error") && (is.null(z$convergence) || is.null(z$convergence$code) || z$convergence$code==0)) {m <- z; idx <- 3}
    else errs <- c(errs, if(inherits(z,"error")) conditionMessage(z) else "random-intercept CLMM non-converged")
  }
  if (is.null(m)) stop(paste(errs, collapse=" | "))
  cf <- tidy_coef(m,name); cf$odds_ratio <- exp(cf$estimate); cf$ci_low <- exp(cf$estimate-1.96*cf$std_error); cf$ci_high <- exp(cf$estimate+1.96*cf$std_error)
  model_rows[[name]] <<- cf
  diag_rows[[name]] <<- data.frame(model=name,n=stats::nobs(m),formula_index=idx,formula=paste(deparse(formula(m)),collapse=" "),
    converged=is.null(m$convergence) || is.null(m$convergence$code) || m$convergence$code==0,singular=NA,pearson_dispersion=NA,residual_skew=NA,fallback_reason=paste(errs,collapse=" | "),stringsAsFactors=FALSE)
  invisible(m)
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
