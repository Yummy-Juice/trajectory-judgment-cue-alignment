# Trajectory judgment and metacognition replication package

This package contains 393 matched main-sample behavioral/eye-tracking records and a separate questionnaire-linked behavioral sample with 286 exact public-ID matches. Paths resolve relative to this folder.

## Repository access

Citation metadata are in `CITATION.cff`. Code uses the MIT License (`LICENSE-CODE`), and data and derived outputs use CC BY 4.0 (`LICENSE-DATA`).

Data, code, and results are available through the [anonymous repository](https://anonymous.4open.science/r/trajectory-judgment-cue-alignment-5755/). Download the files and preserve the directory structure shown below. Run the analysis commands from the package root.

## Reproduce the analyses

Install Python 3.12 with `pip install -r requirements.txt`, plus R 4.4 with `lme4`, `ordinal`, and `MASS`, or use `environment.yml`. From the package root run:

```text
python run_analysis.py
```

The default command runs the main analyses, the two condition-specific questionnaire comparisons, supplementary Q14 interaction tests, design simulations, seven composite figures, and the Chinese result report. The principal questionnaire comparisons use Q13 groups with gravity behavior and Q14 groups with zero-gravity behavior; both include all ten endpoints and all four metacognitive measures. Windows and shell wrappers are included. [Analysis methods](ANALYSIS_METHODS.md) document estimands, coding, QC, model assumptions, and multiplicity.

`--reuse-models` reuses completed R models after directly matching their inputs and specification. Eye events and MLE fits are cached, and simulations resume completed scenario/replicate cells. Use `--rebuild-eye` after changing eye inputs. `--skip-report`, `--skip-figures`, `--skip-simulations`, and `--skip-questionnaire` select partial workflows.

The base random seed is 20260713. Selected scanpath contrasts use bootstrap seed 20260716 and 3500 within-group participant resamples, independently initialized for each measure. Contrasts are ordered by BH-adjusted permutation p and dyad name before resampling. The analysis methods and the `bootstrap_seed` column in `outputs/tables/scanpath_selected_contrasts_by_metric.csv` document these settings.

## Data, code, and results

| Location | Contents |
| --- | --- |
| `behavioral_data/`, `eye_tracking_data/` | The 393 matched main-sample records |
| [Questionnaire module](questionnaire_public/README.md) | Public responses, codebook, 286 matched behavioral files, comparisons and moderation |
| `run_analysis.py`, `r_models.R` | Main workflow and behavior/AOI mixed models |
| `metacognition.py`, `metacognition_analysis.py` | Meta-d′, signed M-ratio, AUC-ratio and repeated metric analyses |
| `ordinal_mixed.py`, `ordinal_workflow.py`, `ordinal_design.R` | Stable ordinal likelihood, design export and numerical diagnostics |
| `design_simulations.py`, `mixed_model_power.R` | Parameter recovery, paired-design sensitivity and model-based simulation |
| `nature_figures.py`, `generate_report.py` | All seven figures and the complete result report |
| [Power module](power_analysis/README.md) | Methods, results and standalone reproduction of 291 native G*Power calculations |
| `outputs/tables/` | Main effects, source data, SDT counts, model diagnostics, sensitivity and simulation summaries |
| `outputs/figures/` | Seven composites, each in PNG and vector PDF |
| `outputs/simulation/` | Consolidated replicate-level results and simulation specification |
| `outputs/power_analysis/` | G*Power native records, CSV results and numerical checks |
| `outputs/analysis_summary.json`, `outputs/runtime_manifest.json` | Workflow status, sample counts and executed environment |

Read the complete Chinese report in [HTML](outputs/report/轨迹判断与元认知分析报告.html), [Word](outputs/report/轨迹判断与元认知分析报告.docx), or [Markdown](outputs/report/轨迹判断与元认知分析报告.md). Result tables and all seven figures remain available alongside the report.

## Regenerate figures or the report

```text
python nature_figures.py
python generate_report.py
```

These commands read completed outputs. Figures default to PNG/PDF, controlled by `figure_formats` in `config.json`. To also export editable SVG and 600-dpi TIFF, run `python nature_figures.py --formats png pdf svg tiff`. G*Power has separate Windows commands in the power module and is not launched by the main workflow.

## Runtime files and interpretation

`cache/` holds reusable model fits and temporary worker checkpoints; `outputs/logs/` holds execution logs. Both are excluded from version control. Completed mixed-model replicates are consolidated in `outputs/simulation/mixed_model_power_replicates.csv`; their combined summary is in `outputs/tables/mixed_model_power_summary.csv`.

Main and questionnaire samples have separate QC and denominators. Questionnaire responses were collected after the task. AUC and meta-d′ measure metacognitive sensitivity; signed M-ratio and AUC-ratio measure metacognitive efficiency. Mean confidence and the two confidence models retain their distinct estimands. Questionnaire group differences and eye/scanpath findings are associations. The study and exploratory analyses were not preregistered. See the analysis methods for full eligibility and interpretation details.
