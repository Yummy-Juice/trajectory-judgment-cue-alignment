# Sample-size and power analysis module

This module contains a revision-stage evaluation of participant-level design sensitivity and hypothetical sample-size requirements. All G*Power results were obtained from the native **G*Power 3.1.9.7 for Windows** application on 5 November 2026.

This document includes reproduction commands, assumptions, analysis-specific recommendations, and the relationship to the existing mixed-model simulation.

## Contents

| File | Purpose |
| --- | --- |
| `scenarios.json` | Complete input specification for 291 calculations |
| `make_scenarios.py` | Recreates the fixed scenario specification |
| `run_gpower.py` | Enters the scenarios into G*Power and captures native input/output fields and protocols |
| `summarize_power.py` | Produces CSV tables from completed G*Power records and aggregate study outputs |
| `../outputs/power_analysis/` | Published calculation records, tables, execution summary, and numeric checks |

The calculation module uses the Python standard library and Windows control messages. G*Power must be installed separately. It uses text controls and does not require screenshots. The main analysis command does not launch this Windows application automatically.

## Reproduce the calculations

Run the following from the package root. Replace the executable path with the local G*Power installation path. A separate output directory preserves the published results.

```text
python power_analysis/make_scenarios.py
python power_analysis/run_gpower.py --gpower-exe "C:\path\to\GPowerNT.exe" --output outputs/power_analysis_rerun
python power_analysis/summarize_power.py --output outputs/power_analysis_rerun
```

For an interrupted calculation, run the same `run_gpower.py` command with `--resume`. Completed scenarios are reused only when their full input specifications match. The JSONL checkpoint is flushed after each successful calculation. A completed checkpoint can also be summarized without opening G*Power.

Every JSONL record includes its complete native protocol. Add `--export-protocol` to the runner command to also produce `gpower_protocol.txt`; the default keeps the protocols in the JSONL records.

The application is launched in a hidden window. If an interrupted run leaves a dedicated G*Power process open, `--attach-pid PROCESS_ID --resume` reuses that process. Only use this option for a process dedicated to this module.

The following G*Power options must be active. The runner checks the native protocol and stops if an incompatible option is detected.

- Correlation: **exact distribution**. Set the exact-distribution threshold sufficiently high, for example 10,000, in Options.
- Wilcoxon signed-rank test: **A.R.E. method**, with **Normal** parent distribution.
- Logistic regression: **Large sample z-Test, Demidenko (2007) with var corr**.

## Output files

| File in `outputs/power_analysis/` | Contents |
| --- | --- |
| `gpower_results.jsonl` | One complete record per scenario, including the requested settings, actual entered fields, native outputs, and protocol text |
| `gpower_manifest.json` | Software version, expected/completed counts, and execution status |
| `gpower_sample_sizes.csv` | 165 required-sample-size calculations, including the historical audit |
| `gpower_sensitivity.csv` | 126 detectable-effect calculations at fixed sample sizes |
| `endpoint_sample_sizes.csv` | Current endpoint-specific valid sample sizes and retention fractions |
| `retention_planning.csv` | Future planning extrapolations from required valid participants to expected matched records before endpoint QC |
| `correlation_sample_sizes.csv` | Current condition-specific correlation sample sizes |
| `dsm_design_summary.csv` | Current extreme-group sizes and comparison-family counts |
| `existing_mixed_model_simulation.csv` | Selected fields from the already completed model-based simulation |
| `numeric_checks.json` | Input binding checks and independent numerical cross-checks performed for the published run |

CSV files use UTF-8, a header row, one scenario or design unit per row, and explicit effect-size/sample-unit fields. Blank cells indicate fields that do not apply to that test. Sample-size requirements are conditional on the stated effect, alpha, power, distribution, and independence assumptions.

## 1. Purpose and interpretation

This supplement evaluates the sample sizes required for explicitly assumed effects across the principal participant-level analyses. It also reports the effects detectable at the current valid sample sizes. The evaluation distinguishes participant-level paired comparisons, correlations, continuous associations, independent extreme-group comparisons, and mixed-effects models.

The native G*Power application executed 291 scenarios: 165 required-N calculations and 126 fixed-N sensitivity calculations. The hypothetical effect grids were specified without substituting the observed effect estimates into a calculation of achieved power. The historical single-test calculation is retained as a separate audit.

G*Power calls the sample-size-solving procedure “A priori.” All calculations in this module were performed during revision. They evaluate the completed design and inform future replication planning; they do not establish the timing or numerical basis of an earlier collection decision.

## 2. Statistical units and available samples

There are 393 matched main-sample records, with 72 formal trials per participant and 36 trials per condition. The participant is the independent unit for paired comparisons and individual-differences analyses. Trial observations remain clustered within participants in the mixed-effects models.

| Analysis or endpoint | Valid participants | Fraction of 393 matched records |
| --- | ---: | ---: |
| Accuracy, decision-time and mean-confidence paired summaries | 354 | 90.1% |
| d′ paired comparison | 351 | 89.3% |
| AUC and AUC-ratio paired comparisons | 258 | 65.6% |
| meta-d′ and M-ratio paired comparisons | 247 | 62.8% |
| Primary eye-tracking sample | 353 | 89.8% |
| Sequence-analysis sample | 269 | 68.4% |

The confidence-count eligibility count of 351 is distinguished from the finite paired AUC and MLE counts. Sample sizes for correlations are condition-specific: AUC/AUC-ratio use 290 and 272 participants; meta-d′/M-ratio use 287 and 263. Continuous sequence associations use 234–257 participants. Extreme-group comparisons use approximately 59–64 participants in each selected group.

Sources are the existing aggregate analysis tables. The exported [endpoint sample table](../outputs/power_analysis/endpoint_sample_sizes.csv), [correlation sample table](../outputs/power_analysis/correlation_sample_sizes.csv), and [DSM design table](../outputs/power_analysis/dsm_design_summary.csv) identify the relevant analysis units.

## 3. Planning assumptions and multiplicity

The main reference calculations use two-sided alpha = .05 and power targets of .80 and .90. Paired and correlation calculations also include .95 power. Required sample sizes are the integer counts returned by G*Power, conditional on the supplied assumptions.

| Analysis | Effect-size grid or design inputs |
| --- | --- |
| Paired t test | dz = .10, .15, .20, .25, .30, .50; alpha = .05/.01/.005; power = .80/.90/.95 |
| Wilcoxon signed-rank benchmark | dz = .15/.20/.30; Normal parent distribution; alpha = .05/.005; power = .80/.90 |
| Pearson correlation | rho under H1 = .10/.15/.20/.25/.30/.40; rho under H0 = 0; alpha = .05/.005; power = .80/.90/.95 |
| Independent extreme-group benchmark | d = .30/.50/.80; allocation ratio = 1; alpha = .05/.003125/.00078125; power = .80/.90 |
| Fixed-design regression coefficient | f² = .02/.05/.10/.15; one tested predictor; one or three total predictors; alpha = .05/.005; power = .80/.90 |
| Independent logistic-regression reference | OR = .80/.90/.95; null success probability = .65; normal predictor with mean 0 and SD 1; other-predictor R² = 0/.25; alpha = .05; power = .80/.90 |

For paired differences, dz = mean(condition difference)/SD(condition difference). For independent groups, d uses the between-participant pooled SD. For an incremental regression coefficient, f² is the increment in explained variance divided by unexplained variance in the full model. Effect sizes use different scales across tests and should be interpreted within their own analysis.

Alpha = .01 and .005 represent conservative five- and ten-test Bonferroni planning scenarios. For the duration-based sequence comparisons, .003125 = .05/16 and .00078125 = .05/64 represent conservative planning bounds for 16 comparisons within one metric and 64 across four metrics. Actual study analyses use their documented BH-FDR families. A fixed Bonferroni threshold does not reproduce the power of a data-dependent BH procedure.

For example, at alpha = .005 the paired dz = .20 requirement increases to 337/422 valid participants for 80%/90% power; the dz = .15 requirement is 596/747. The corresponding correlation requirements are 327/410 for r = .20 and 586/735 for r = .15. These comparisons quantify the impact of a stricter error threshold without treating a Bonferroni calculation as the actual BH procedure.

### Coverage of the study analyses

| Study analysis | Relevant planning calculation | Scope of the recommendation |
| --- | --- | --- |
| Accuracy, response-time, confidence and metacognition paired summaries | Paired t test and endpoint-specific fixed-N sensitivity | Valid paired participants; assumed standardized difference |
| Wilcoxon paired robustness check | Signed-rank Normal-ARE benchmark | Distribution-specific approximation |
| Accuracy–metacognition Pearson correlations | Exact bivariate-normal correlation | Valid independent participants within each condition |
| Spearman correlations | Pearson table as a reference | A rank-correlation-specific design would require its own distributional evaluation |
| Continuous sequence associations with HC3 uncertainty | One-predictor regression coefficient benchmark | Classical residual assumptions; HC3 power is not encoded |
| Extreme-group DSM | Independent-group benchmark and actual-group-size sensitivity | Selected group participants; permutation selection and FDR require separate simulation |
| Behavioral GLMM/LMM, ordinal CLMM and AOI mixed models | Participant-level benchmarks plus model-specific simulation | Full random structures require simulation of the relevant model; the existing simulation covers the confidence–accuracy GLMM |
| meta-d′/M-ratio participant-level comparisons | Paired benchmark plus existing 36-trial recovery | Participant count and within-participant trial precision are separate design dimensions |
| Leave-one-participant-out stability | Underlying endpoint's analysis sample | This diagnostic does not define an additional independent recruitment target |

## 4. Paired condition differences

G*Power settings: `t tests` → `Means: Difference between two dependent means (matched pairs)` → `A priori`; Tail(s) = Two.

| Assumed dz | Required valid N, 80% power | Required valid N, 90% power |
| --- | ---: | ---: |
| .10 | 787 | 1053 |
| .15 | 351 | 469 |
| .20 | 199 | 265 |
| .25 | 128 | 171 |
| .30 | 90 | 119 |
| .50 | 34 | 44 |

These rows use alpha = .05. The historical one-sided dz = .50, alpha = .05, power = .80 audit yields N = 27, with actual power .8118316. Its effect and tail assumptions differ from the expanded two-sided evaluation.

For fixed-N sensitivity, the same two-sided procedure gives:

| Valid N | Detectable dz, 80% power | Detectable dz, 90% power |
| --- | ---: | ---: |
| 29 | .5390 | .6237 |
| 393, if all records were eligible | .1417 | .1639 |
| 354, main behavioral sample | .1493 | .1728 |
| 353, primary eye sample benchmark | .1495 | .1730 |
| 351, d′ sample | .1499 | .1735 |
| 258, paired AUC/AUC-ratio sample | .1751 | .2026 |
| 247, paired meta-d′/M-ratio sample | .1790 | .2071 |

Thus, the behavioral sample supports an 80%-power benchmark close to dz = .15; the finite paired metacognition samples have benchmarks near .18. Power for a hypothetical dz = .10 is lower. The total matched count of 393 should not replace the endpoint-specific valid count in a power calculation.

The Wilcoxon Normal-location-shift benchmark requires N = 208/278 for dz = .20 at 80%/90% power and alpha = .05. G*Power uses an asymptotic relative-efficiency calculation. This is a distribution-specific reference for the rank robustness check.

Applying paired-difference planning to a ratio index evaluates a group mean contrast under its assumed difference distribution. Individual meta-d′ and M-ratio estimation precision also depends on the number and distribution of trials. The existing 36-trial parameter-recovery and confidence-binning analyses provide complementary evidence for that dimension of the design.

## 5. Correlations and continuous associations

G*Power settings: `Exact` → `Correlation: Bivariate normal model`; Tail(s) = Two; rho under H0 = 0; Options = exact distribution.

| Assumed population r | Required valid N, 80% power | Required valid N, 90% power |
| --- | ---: | ---: |
| .10 | 782 | 1046 |
| .15 | 346 | 462 |
| .20 | 193 | 258 |
| .25 | 123 | 164 |
| .30 | 84 | 112 |
| .40 | 46 | 61 |

These rows use alpha = .05. The condition-specific correlation samples of 263–290 exceed the .20-effect, 90%-power reference of 258. The weaker r = .15 planning scenario requires 346 valid participants for 80% power. The correlation assumptions are independent participants and bivariate-normal Pearson sampling; they provide a reference for the separately reported Spearman analyses.

The current continuous sequence association model has one metric predictor (`rate ~ metric`, using HC3 robust uncertainty). A classical coefficient-test planning benchmark uses `F tests` → `Linear multiple regression: Fixed model, R² increase`; one tested predictor and one total predictor.

| Assumed f² | Required valid N, 80% power | Required valid N, 90% power |
| --- | ---: | ---: |
| .02 | 395 | 528 |
| .05 | 159 | 213 |
| .10 | 81 | 108 |
| .15 | 55 | 73 |

These rows use alpha = .05. The actual continuous-association samples of 234–257 give 80%-power classical sensitivity bounds of f² = .0338–.0308. Results for three total predictors are an explicitly specified additional planning model, not the fitted sequence-association formula. The classical F calculation assumes homoscedastic independent residuals; it does not calculate HC3-robust or BH-adjusted power.

## 6. Exploratory extreme-group comparisons

G*Power settings: `t tests` → `Means: Difference between two independent means (two groups)`; two-sided; allocation ratio N2/N1 = 1.

| Assumed d | Total N / N per group, 80% power | Total N / N per group, 90% power |
| --- | ---: | ---: |
| .30 | 352 / 176 | 470 / 235 |
| .50 | 128 / 64 | 172 / 86 |
| .80 | 52 / 26 | 68 / 34 |

These rows use alpha = .05. They apply to the participants actually entering the two selected groups. Strict upper/lower quartile selection retains at most about half of the eligible continuous sample, with further differences possible because of ties and sequence QC. Consequently, a total-group requirement of 128 cannot be interpreted as 128 initial matched records.

The actual group sizes are 59–64 per group. Under the classical unadjusted model, these samples are close to the d = .50, 80%-power reference. The published tables also include alpha = .05/16 and .05/64 scenarios and the exact current unequal group sizes. The study's normalized-rate permutation tests, group selection, and BH-FDR procedure require design-specific simulation to assess their joint power; the independent t calculations provide a reference scale. These sequence findings retain their exploratory interpretation.

## 7. Mixed-effects models and the logistic reference

The participant-level paired and fixed-design calculations address specified simpler contrasts. The trial-level GLMMs, LMMs, ordinal CLMMs, and repeated AOI models include participant dependence and random effects. G*Power's ordinary regression modules do not encode their full design.

The existing simulation of the confidence–accuracy GLMM retains the actual valid trial design, fixed nuisance effects, and participant random-effect covariance. Every replicate generates new participant random effects and binary responses, followed by a refit using the same model specification.

| True condition-by-confidence OR | Participants | Valid trials | Replicates | Detection proportion | Monte Carlo 95% interval |
| --- | ---: | ---: | ---: | ---: | --- |
| 1.00 | 354 | 24,615 | 100 | .02 | [.006, .070] |
| .90 | 354 | 24,615 | 100 | .90 | [.826, .945] |

Both scenarios have 100 usable fits. These results evaluate one model and one actual sample size; they do not establish a minimum N across alternative recruitment sizes or guarantee equal power for other mixed-model terms. The existing simulation rows are provided in [the model-simulation extract](../outputs/power_analysis/existing_mixed_model_simulation.csv).

For transparency, the module also supplies 12 independent logistic-regression reference calculations. With a standard-normal predictor, null success probability .65, OR = .90, other-predictor R² = 0, alpha = .05, and the Demidenko variance-corrected z procedure, G*Power requires **3,123 independent binary observations** for 80% power and **4,178** for 90% power. These counts are not participant requirements for the clustered trial-level GLMM and must not be divided by 72 to obtain such a requirement.

## 8. Endpoint retention in replication planning

The required N tables concern valid analysis participants. The retention table applies the observed valid fraction among the 393 matched records as a future planning assumption:

`expected matched records before endpoint QC = ceiling(required valid N / observed valid fraction)`.

| Endpoint | Required valid N for dz = .20, 80% / 90% power | Expected matched records before QC, 80% / 90% power |
| --- | --- | --- |
| Accuracy | 199 / 265 | 221 / 295 |
| AUC or AUC-ratio | 199 / 265 | 304 / 404 |
| meta-d′ or M-ratio | 199 / 265 | 317 / 422 |
| Primary eye sample benchmark | 199 / 265 | 222 / 296 |

These rows use alpha = .05 and assume the same endpoint retention in a future study. They are expected-count extrapolations, not assurances that a fixed initial count will yield the target valid N. They concern matched records before endpoint QC. The values do not establish an earlier recruitment rationale. For dz = .15, the finite AUC and MLE retention assumptions imply substantially larger starting matched samples; all scenarios appear in the CSV.

The completed design therefore supports different levels of sensitivity across analyses. Precision, effect magnitude, uncertainty, multiplicity, and estimation reliability remain part of the interpretation alongside p values.

## 9. Reproducibility and numeric checks

All input fields, native outputs and complete native protocols are preserved in `gpower_results.jsonl`. The optional `--export-protocol` switch also writes `gpower_protocol.txt`. Scenario IDs connect these records to both CSV tables. The exact-distribution correlation, Normal-ARE rank procedure, and Demidenko variance-corrected logistic options are recorded and checked.

For the published run, all 291 requested input dictionaries matched the entered GUI fields. Independent noncentral-distribution calculations checked 203 scenarios, including all 117 applicable integer-N requirements and 86 sensitivity roots. Required-N boundaries agreed; the maximum power and effect-size differences were below 5 × 10⁻⁸ at G*Power's displayed precision. Correlation and logistic outputs retain their native application calculations and option records. Details are stored in `numeric_checks.json`.

See the [reproduction commands](#reproduce-the-calculations) for commands that reproduce the calculations in a separate output directory. No main study models need to be refitted to inspect or summarize this module.

## 10. Method references

- [G*Power official software page](https://www.psychologie.hhu.de/en/arbeitsgruppen/allgemeine-psychologie-und-arbeitspsychologie/gpower).
- [G*Power 3.1 manual, 1 June 2023](https://www.psychologie.hhu.de/fileadmin/redaktion/Fakultaeten/Mathematisch-Naturwissenschaftliche_Fakultaet/Psychologie/AAP/gpower/GPowerManual.pdf).
- [Faul, Erdfelder, Buchner, and Lang (2009), Statistical power analyses using G*Power 3.1](https://www.psychologie.hhu.de/fileadmin/redaktion/Fakultaeten/Mathematisch-Naturwissenschaftliche_Fakultaet/Psychologie/AAP/gpower/GPower31-BRM-Paper.pdf).
