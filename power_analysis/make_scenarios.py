"""Write the fixed, hypothetical-effect G*Power scenario specification."""
from itertools import product
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
POWER = "Power (1-β err prob)"
ALPHA = "α err prob"
PAIRED = "Means: Difference between two dependent means (matched pairs)"
INDEPENDENT = "Means: Difference between two independent means (two groups)"
CORRELATION = "Correlation: Bivariate normal model"
REGRESSION = "Linear multiple regression: Fixed model, R² increase"


def scenarios():
    rows = []
    def add(group, family, test, mode, inputs, role, unit="participants"):
        rows.append(dict(id=f"{group}-{sum(r['group'] == group for r in rows)+1:03d}",
                         group=group, family=family, test=test, mode=mode,
                         inputs=inputs, role=role, unit=unit))

    add("paired-reference", "t tests", PAIRED, "A priori",
        {"Tail(s)": "One", "Effect size dz": .5, ALPHA: .05, POWER: .8},
        "One-sided paired-samples reference scenario")
    for effect, alpha, power in product([.1, .15, .2, .25, .3, .5],
                                       [.05, .01, .005], [.8, .9, .95]):
        add("paired", "t tests", PAIRED, "A priori",
            {"Tail(s)": "Two", "Effect size dz": effect, ALPHA: alpha, POWER: power},
            "Participant-level paired condition differences")
    for effect, alpha, power in product([.15, .2, .3], [.05, .005], [.8, .9]):
        add("signed-rank", "t tests", "Means: Wilcoxon signed-rank test (matched pairs)",
            "A priori", {"Tail(s)": "Two", "Parent distribution": "Normal",
                         "Effect size dz": effect, ALPHA: alpha, POWER: power},
            "Normal location-shift planning benchmark for the rank robustness check")
    for effect, alpha, power in product([.1, .15, .2, .25, .3, .4],
                                       [.05, .005], [.8, .9, .95]):
        add("correlation", "Exact", CORRELATION, "A priori",
            {"Tail(s)": "Two", "Correlation ρ H1": effect, ALPHA: alpha,
             POWER: power, "Correlation ρ H0": 0},
            "Independent participants, bivariate-normal Pearson correlation")
    for effect, alpha, power in product([.3, .5, .8], [.05, .05/16, .05/64], [.8, .9]):
        add("extreme-groups", "t tests", INDEPENDENT, "A priori",
            {"Tail(s)": "Two", "Effect size d": effect, ALPHA: alpha,
             POWER: power, "Allocation ratio N2/N1": 1},
            "Balanced independent-group benchmark for exploratory DSM contrasts")
    for effect, predictors, alpha, power in product([.02, .05, .1, .15],
                                                     [1, 3], [.05, .005], [.8, .9]):
        add("regression", "F tests", REGRESSION, "A priori",
            {"Effect size f²": effect, ALPHA: alpha, POWER: power,
             "Number of tested predictors": 1, "Total number of predictors": predictors},
            "Classical fixed-design coefficient test; one predictor matches the continuous association design")
    for effect, other_r2, power in product([.8, .9, .95], [0, .25], [.8, .9]):
        add("logistic-reference", "z tests", "Logistic regression", "A priori",
            {"Tail(s)": "Two", "Odds ratio": effect, "Pr(Y=1|X=1) H0": .65,
             ALPHA: .05, POWER: power, "R² other X": other_r2,
             "X distribution": "Normal", "X parm μ": 0, "X parm σ": 1},
            "Illustration for independent binary outcomes; not a mixed-model participant requirement",
            "independent binary observations")
    for n, alpha, power in product([29, 393, 354, 351, 353, 258, 247, 269],
                                  [.05, .005], [.8, .9]):
        add("paired-sensitivity", "t tests", PAIRED, "Sensitivity",
            {"Tail(s)": "Two", ALPHA: alpha, POWER: power, "Total sample size": n},
            "Detectable standardized paired difference at the stated eligible n")
    for n, alpha, power in product([29, 393, 290, 272, 287, 263, 257, 254, 242, 234],
                                  [.05, .005], [.8, .9]):
        add("correlation-sensitivity", "Exact", CORRELATION, "Sensitivity",
            {"Tail(s)": "Two", "Effect direction": "r ≥ ρ", ALPHA: alpha,
             POWER: power, "Total sample size": n, "Correlation ρ H0": 0},
            "Detectable positive Pearson correlation at the stated eligible n")
    for (n1, n2), alpha, power in product([(59, 59), (61, 60), (61, 61), (64, 63), (64, 64)],
                                         [.05, .05/16, .05/64], [.8, .9]):
        add("extreme-sensitivity", "t tests", INDEPENDENT, "Sensitivity",
            {"Tail(s)": "Two", ALPHA: alpha, POWER: power,
             "Sample size group 1": n1, "Sample size group 2": n2},
            "Classical independent-group detectable effect at actual DSM group sizes")
    for n, alpha, power in product([234, 242, 254, 257],
                                  [.05, .05/16, .05/64], [.8, .9]):
        add("regression-sensitivity", "F tests", REGRESSION, "Sensitivity",
            {ALPHA: alpha, POWER: power, "Total sample size": n,
             "Number of tested predictors": 1, "Total number of predictors": 1},
            "Classical coefficient-test sensitivity; HC3/permutation/FDR power is not calculated by G*Power")
    return rows


if __name__ == "__main__":
    path = HERE / "scenarios.json"
    content = {"software": "G*Power 3.1.9.7", "specification_version": 1,
               "effect_selection": "Hypothetical planning grid; not fitted observed effects",
               "timing": "Exploratory design sensitivity and hypothetical sample-size planning",
               "multiplicity": "Alpha .005, .05/16 and .05/64 are conservative Bonferroni planning scenarios, not BH-FDR equivalences",
               "scenarios": scenarios()}
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != content:
        raise FileExistsError("Specification already exists with different settings; preserve it before changing.")
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(content['scenarios'])} scenarios to {path.name}")
