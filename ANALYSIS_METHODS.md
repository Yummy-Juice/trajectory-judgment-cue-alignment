# Second-revision analysis specification

The original analytical structure is retained, with AUC-based operations repeated for meta-d′, signed M-ratio, and AUC-ratio. Changes and design-sensitivity evaluations were conducted during the revision.

## Data sources and coding

Main analyses use only this folder's `behavioral_data/` and `eye_tracking_data/`. Questionnaire analyses use only `questionnaire_public/behavioral_data/`, linked exactly by the questionnaire's `participant_id` and filename stem. The verified original one-to-one crosswalk was used to create consistent public P identifiers; the internal crosswalk and recording timestamps are excluded from the public questionnaire files. Different source sets have separate QC and denominators.

In SDT, S=`ExpectedAnswer`, R=`UserAnswer`, with both restricted to 0/1; correctness is S=R. These are true-option and selected-option categories, not accuracy-coded stimuli. Confidence is an integer 1–7, increasing with certainty. All 28 S×R×confidence cells are exported, including zeros. In each 14-cell stimulus vector, response 0 runs from high to low confidence and response 1 from low to high confidence. Main data contain 36 trials per condition.

## Estimation choice and reliability

Maniscalco–Lau equal-variance conditional maximum likelihood is used, matching the supplied reference implementation and the reviewer's explicitly permitted MLE route. The revision preserves the participant-level AUC analysis structure and permits signed estimates. A hierarchical log-M model would impose positive M on records that include inverse confidence patterns and negative/near-zero d′; no hierarchical-model result is claimed.

Each cell receives 1/(2K) pseudocount, totaling .5 in each response block. d′ and c use the same corrected vectors. The conditional multinomial likelihood fits meta-d′ and 2(K−1) ordered response-specific relative confidence thresholds. The relative criterion restriction is meta-c=(meta-d′/d′)×c. Optimization is the supplied deterministic SLSQP procedure, with 500 iterations, ftol=1e−9, bounds meta-d′∈[−10,10], relative thresholds∈[−20,20], and ordered gaps≥1e−5. Boundary, nonconvergence, missing classes, constant confidence, and |d′|≤.01 statuses are retained. Signed M-ratio=meta-d′/d′ is not clipped.

AUC uses all confidence levels with ties given half credit, retaining the original undefined-constant-confidence rule. AUC-ratio divides observed AUC by the ideal-observer AUC projected from corrected d′ and all observed criteria, retaining original stimulus proportions. This normalized index can retain dependence on task sensitivity and is interpreted alongside M-ratio.

Group inference uses direct paired t differences (zero minus gravity), 95% t confidence intervals, dz, and Wilcoxon checks. All 10 endpoint t tests form one BH family; the four metacognition endpoints also have a separate q column. Main MLE comparison is on finite paired fits. Reliability outputs include full-state counts, same-participant comparisons, |d′|>.10 and d′>.10 in both conditions, one fixed 3-bin mapping (1–3/4–5/6–7), conditional in-sample predictions, and sparse-data recovery. These checks qualify individual precision; numerical optimizer success alone is not evidence of stable participant rankings.

## Directly repeated AUC operations

For each of AUC/meta-d′/M-ratio/AUC-ratio, accuracy correlations use condition-specific finite samples and both Pearson and Spearman coefficients. Extreme-group DSM uses strictly below Q1 and above Q3 within condition. The original event construction, pooled participant median duration classification, normalized dyad rates, M−2SD total-dyad QC, 5000 two-sided permutations, and HC3 continuous regressions are retained. Eligibility and dyad QC are recomputed for each metric. The original AUC tables remain identifiable as AUC; consolidated files have an explicit metric column.

DSM correction families are metric × condition × event/duration representation. Additional q columns correct across all four metrics within condition and representation. Selected-dyad intervals bootstrap participants within groups 3500 times. Correlations with sums of selected dyads are post-selection descriptions from the same data; they do not independently validate the selected patterns. Individual new-metric groups are explicitly named by their metric, without relabeling AUC groups as efficiency groups.

The base random seed is 20260713, matching the first revision. Selected-dyad bootstrap intervals use the first-revision seed 20260716 (base seed + 3), with an independent initialization for each metacognitive measure. Within each measure, selected duration-based contrasts are ordered by BH-adjusted permutation p and dyad name before resampling, following the first-revision figure calculation. The consolidated AUC intervals therefore reproduce the original AUC bootstrap table. Each row in `scanpath_selected_contrasts_by_metric.csv` records its `bootstrap_seed`.

## Condition-specific questionnaire comparisons and supplementary moderation

The principal questionnaire analyses are two exploratory, condition-specific group comparisons. Q13 independently defines the 3D gravity and two-dimensional billiards-like groups for gravity behavior only. Q14 independently defines the 3D zero/microgravity and two-dimensional billiards-like groups for zero-gravity behavior only. Other questionnaire responses do not enter these tests. All ten endpoints are included: accuracy, median and mean decision time, mean confidence, median confidence time, AUC, meta-d′, signed M-ratio, AUC-ratio, and first-order d′. Each endpoint uses its own valid sample and requires QC only in the specified condition. Two-sided participant-level Welch tests and 95% intervals compare two-dimensional billiards-like minus 3D means; Hedges g uses pooled sample SD and small-sample correction. Each question's ten endpoints form the main BH reporting family. The four-metacognition correction is supplementary. These comparisons supply Supplementary Table S16 and the condition-specific panels in Figure S4.

Supplementary analyses address the reviewer's moderation question (Table S14). Q14 focal groups additionally enter condition × interpretation models, preserving paired behavior QC. Accuracy uses a binomial-logit GLMM and confidence an ordinal cumulative-logit CLMM with velocity, directional size pairing, target side, linear/quadratic trial progression, condition×velocity/size interactions, and participant intercept/condition slopes subject to recorded fallback diagnostics. Each of the four metacognitive measures uses a Welch test of participant paired differences (zero−gravity), with difference-of-differences=billiards−3D and 5000 within-group participant bootstrap draws. The reported interaction correction covers all six endpoints: accuracy, confidence, AUC, meta-d′, signed M-ratio, and AUC-ratio. The original three-endpoint correction column is retained in the machine-readable output for reference. The within-condition group comparisons and the paired-condition interaction tests retain their respective estimands and eligibility rules.

Standardized accuracy and confidence predictions average the same pooled valid trial covariates with random effects set to zero. Intervals use 1000 joint multivariate-normal coefficient draws; confidence draws include fitted thresholds. The output distinguishes model-scale interaction ORs from outcome-scale standardized differences. Questionnaire responses were post-task; the comparisons remain exploratory associations.

## Confidence models and simulations

The cumulative-logit mixed models retain the first-revision participant intercept and condition slope, all fixed effects, and the primary Laplace approximation (`nAGQ=1`). Numerical recovery uses stable log-probability differences and an independent Gaussian random-effects likelihood implementation. Participant modes are solved with analytic scores and curvature; the adaptive transformation derivative is included in the marginal likelihood score. Reported information matrices are checked against independent marginal-likelihood differences, with positive curvature and maximum numerical-gradient tolerance .001. The original ordinal optimizer's failed iterations are retained outside the public results.

Higher-order integration is explicitly a numerical sensitivity analysis. Fifteen nodes per dimension are fitted and compared with a 21-node parameter refit; accepted fixed-parameter changes are below .01 of their 15-node standard errors. Full covariance estimates accompany the primary Laplace and 15-node fits. Software implementation, actual formulas, covariance dimensions, gradient checks, quadrature checks, and comparison coefficients are saved with the results. Differences between the primary and higher-order ordinal interactions are reported alongside the two confidence models.

The accuracy model interaction estimates the zero/gravity ratio of within-participant confidence slopes predicting correct responses. The ordinal-confidence model interaction estimates how correctness-associated proportional odds differ by condition. Both models are reported with their own endpoint, link, estimand, CI, and diagnostic state; neither interaction directly estimates metacognitive efficiency.

Paired-design sensitivity uses endpoint-specific finite n with assumed dz=0/.10/.20/.30, 5000 simulated normal participant differences, two-sided α=.05, and noncentral-t analytic power. It reports Monte Carlo SE, coverage, mean interval width, and the 80% detectable effect, without attributing the analysis to a recruitment decision.

The complex-model simulation uses the completed confidence–accuracy GLMM's actual trial design, nuisance fixed effects, and random-effect covariance. New participant random effects and binary responses are generated each time; the target condition×within-person-confidence interaction is set to OR=1 or .90, each 100 replicates. The exact fitted formula and fitting method are used in refits. Simulation rows retain convergence, singularity, errors, effect/CI, p, seed, and elapsed time. Failure is included in the total denominator and also shown separately; summaries include detection, Monte Carlo SE, interval coverage, bias, RMSE, and width. Checkpoints permit continuation by scenario/replicate.

Individual MLE recovery has four 36-trial scenarios (d′=.8/1.2; distributed/high-concentrated confidence; true M=.6), 200 replicates each. A type-1 response is generated from d′ and c, then confidence from the meta-d conditional distribution given stimulus and response. Recovery describes finite-sample bias and sampling spread conditional on successful fits, with every failure counted.

## Sample-size and power supplement

The standalone [G*Power supplement](power_analysis/README.md) provides 165 required-N and 126 fixed-N sensitivity calculations executed in G*Power 3.1.9.7. It specifies hypothetical effects, tail settings, alpha/power grids, analysis units, conservative multiplicity scenarios, and endpoint-retention planning. The existing participant-clustered GLMM simulation is retained as the model-specific evaluation. These calculations were conducted during revision; the software's `A priori` label denotes the mathematical calculation type. Native records, summaries, and reproduction instructions are available through [the power module](power_analysis/README.md).

## Sources

- [Maniscalco & Lau (2012)](https://doi.org/10.1016/j.concog.2011.09.021)
- [Fleming (2017)](https://doi.org/10.1093/nc/nix007)
- [Rahnev (2025)](https://doi.org/10.1038/s41467-025-56117-0), final publication of the preprint referenced in the supplied code.
- [lme4 simulation documentation](https://lme4.github.io/lme4/reference/simulate.merMod.html)
- [ordinal reference manual](https://cran.r-project.org/web/packages/ordinal/ordinal.pdf), including the Laplace and adaptive-quadrature definitions used for the numerical comparison.

## Figures and report outputs

`nature_figures.py` produces the four main result composites and Figures S1, S2 and S4. Questionnaire response bars and forests share the same drawing module. The package figure slots 1–4 correspond to manuscript Figures 3–6. Figure S4 retains its 2×2 response-count/forest layout. Plot calculations and source CSV tables are shared across export formats.

The default exports are 300-dpi PNG (used by the report) and vector PDF. `figure_formats` in `config.json` controls the full workflow; `python nature_figures.py --formats png pdf svg tiff` additionally produces editable SVG and LZW-compressed 600-dpi TIFF. `python generate_report.py` creates the Word, HTML and Markdown report from the completed result tables and PNGs.

Completed mixed-model simulation rows are published once in `outputs/simulation/mixed_model_power_replicates.csv`. During execution, worker checkpoint rows and job state are saved under `cache/simulation/`; a new run can seed its workers from the consolidated table. The consolidated summary is `outputs/tables/mixed_model_power_summary.csv`. Native G*Power protocols are retained within `gpower_results.jsonl`; the optional `--export-protocol` switch writes a separate text copy.
