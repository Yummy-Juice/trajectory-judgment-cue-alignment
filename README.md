# Trajectory Judgment Cue-Alignment Replication Package

This repository contains **393 matched participants** with a behavioral CSV and an eye-tracking XLSX. It is a self-contained, reproducible analysis package for the manuscript revision. The participant count is discovered from the current matched filenames rather than hard-coded.

## Repository access

The original `.xlsx` workbooks are stored with Git Large File Storage (Git LFS). Clone the full replication package with:

```bash
git lfs install
git clone https://github.com/Yummy-Juice/trajectory-judgment-cue-alignment.git
cd trajectory-judgment-cue-alignment
git lfs pull
```

The repository excludes derived caches and Python bytecode. Code is released under the MIT License (`LICENSE-CODE`); data and derived outputs are released under CC BY 4.0 (`LICENSE-DATA`). Please cite the version-specific Git tag using the metadata in `CITATION.cff`.

## One-command reproduction

1. Install Python 3.12 and R 4.4 (or create the supplied Conda environment): `conda env create -f environment.yml`.
2. Ensure R packages `lme4` and `ordinal` are available.
3. From this folder run `python run_analysis.py` (Windows users may double-click `run_analysis.bat`).

The first run parses about 5.5 GB of eye-tracking workbooks and may take 10-30 minutes. Parsed fixation events are cached under `cache/`; use `python run_analysis.py --rebuild-eye` only when the source XLSX files change. All derived results are written to `outputs/`.

## Prespecified exclusion rules

- Behavior: exclude a participant if either condition has fewer than 24 valid responses, fewer than 3 correct responses, or fewer than 3 error responses.
- AUC: additionally require at least 24 valid confidence trials and at least 3 correct and 3 error confidence trials per condition.
- Eye tracking: primary threshold is at least 50% non-Gap coverage and at least 10 fixation events in each condition; 40% and 60% thresholds are sensitivity checks.
- SPAM/DSM: exclude participants whose total usable dyad count is below M - 2 SD. Inference uses normalized dyad frequency, permutation tests, and BH-FDR correction.

## Analysis scope

The pipeline produces participant-level condition summaries, trial-level GLMM/LMM/CLMM models, confidence-accuracy coupling analyses, stimulus-generation checks, AOI condition-by-region models, exploratory event/duration SPAM-DSM, continuous-AUC sensitivity analyses, diagnostics, publication figures (PNG/PDF/SVG), machine-readable CSV tables, and a concise Chinese Word report.

The interpretation is deliberately conservative: gravity versus zero-gravity is treated as a task-context/cue-alignment contrast, not as a unique causal test of internal gravity-prior violation.

## Data notes

`MainData.TOI` supplies `gravity` and `zero_gravity` labels. Eye files do not retain trial identifiers; therefore scan-path transitions may cross adjacent trial boundaries within a TOI and SPAM/DSM results are exploratory. Original source data are never overwritten.
