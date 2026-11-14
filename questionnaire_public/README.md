# Public questionnaire analysis (second-revision comparisons)

This folder contains the de-identified questionnaire records and the matching behavioral CSV files used for the two exploratory comparisons in the second-revision package.

## Data and identifiers

- `questionnaire_data_public.csv` contains the public questionnaire responses, including original Q13 and Q14 labels and the public `participant_id` / `respondent_id`.
- `behavioral_data/` contains only this subpackage's matched behavioral CSV files. The script reads behavior only from this directory and joins each public questionnaire ID to an exact CSV filename stem. It checks unique IDs and one-to-one join cardinality; it does not match by row order.
- The public IDs are anonymous `Pxxx` codes. The internal ID crosswalk is not included in this public package.
- `questionnaire_codebook.csv` documents the public questionnaire variables. Data, codebook and group comparisons each have one CSV source.

## Principal exploratory comparisons

The script runs only these two comparisons:

1. Original Q13: the 3D gravity-understanding group versus the two-dimensional billiards-like group, using behavior in the gravity condition.
2. Original Q14: the 3D zero/microgravity-understanding group versus the two-dimensional billiards-like group, using behavior in the zero-gravity condition.

For each question, responses outside those two specified options are excluded from the group test. The effect direction is two-dimensional billiards-like minus 3D understanding. Endpoints include accuracy, positive decision-time measures in milliseconds, mean confidence, positive confidence-time measures, type-2 ROC AUC, meta-d-prime, M-ratio, AUC-ratio, and d-prime as a reference. Metacognitive measures use the shared `revision_metrics.metric_values` estimator.

Each item-condition comparison applies its own behavioral QC. Choice endpoints require at least 24 valid 0/1 stimulus-response trials and at least three correct and three incorrect responses. Confidence endpoints additionally require at least 24 integer 1–7 confidence trials with at least three correct and three incorrect trials. A participant does not need to pass QC in the other condition. Missing confidence does not remove trials from accuracy or decision-time calculations; reaction-time summaries use positive values only.

Group inference uses two-sided Welch independent-samples t tests, a 95% Welch confidence interval for the mean difference, and Hedges g using pooled SD with the small-sample correction. The main reporting family applies BH correction to all ten endpoints separately within each questionnaire item (`q_bh_10_endpoints`, also stored as `p_bh`). The separate four-metacognition correction is supplementary. All four metacognitive measures are included in each comparison. These results supply Supplementary Table S16 and Figure S4.

The questionnaire was completed after the task. These group differences are exploratory associations with reported task understanding.

## Outputs and reproduction

Run from this directory:

```text
python analyze_questionnaire.py
```

The script writes the following files to `questionnaire_outputs/`:

- `questionnaire_subject_metrics.csv`
- `questionnaire_group_comparisons.csv`
- `questionnaire_sample_flow.csv`
- `questionnaire_match_audit_public.csv` (aggregate counts only)
- `questionnaire_model_diagnostics.csv`
- `questionnaire_analysis_summary.json`
- `questionnaire_analysis_report.md`
- `questionnaire_all_conditions_metrics.csv` (both behavioral conditions for every matched questionnaire respondent)
- `questionnaire_trial_model_input.csv` (Q14 focal groups, both conditions, with condition-paired QC flags)

The script does not create figures. `questionnaire_trial_model_input.csv` codes `size_pair` as `LeftScale_RightScale` (for example, `0.8_0.9`) and standardizes each participant's row-order trial index across their file. Dependencies are `pandas`, `numpy`, `scipy`, and `statsmodels`; `revision_metrics.py` is imported from the package root.

## Supplementary condition-by-interpretation analyses

The complete package command also runs `questionnaire_moderation.py` from the package root. This adds Q14 condition-by-interpretation accuracy/ordinal-confidence models and paired-difference comparisons for AUC, meta-d′, signed M-ratio, and AUC-ratio, reported in Supplementary Table S14. These supplementary tests use both conditions from the same eligible participants and six-endpoint BH correction (`p_bh_all_six`); the original three-endpoint correction remains in the CSV for reference. Standalone `analyze_questionnaire.py` runs the two principal condition-specific group comparisons above. Moderation estimates, standardized predictions, diagnostics, and paired subjects are saved beside the group comparison tables.
