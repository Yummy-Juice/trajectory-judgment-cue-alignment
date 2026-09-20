# Publication figure design specification

Backend: direct Python/matplotlib implementation. Figures use a fixed 183-mm canvas, white background, English serif typography, lowercase panel labels, thin neutral reference lines, and a restrained navy–terracotta–teal palette. Each figure is exported as editable SVG, vector PDF, high-resolution PNG, and TIFF.

## Figure 1 — Behavioural signature

- Conclusion: the zero-gravity context is associated with lower accuracy, confidence, and type-2 ROC AUC; the unadjusted decision-time contrast is small.
- Structure: a standardized effect forest spanning the top row, followed by three participant-level paired distribution panels for accuracy, confidence, and AUC.
- Visual priority: effect direction and uncertainty first; raw paired heterogeneity second.

## Figure 2 — Metacognitive monitoring

- Conclusion: confidence remains diagnostic of correctness in both contexts, but the adjusted confidence–correctness coupling is weaker in the zero-gravity context.
- Structure: confidence calibration as the top-wide panel; adjusted model coefficients and condition-specific accuracy–AUC associations below.
- Visual priority: calibration shape and adjusted effect intervals; avoid decorative links or overlapping annotations.

## Figure 3 — Gaze reallocation

- Conclusion: gaze allocation shifts from the ball region toward the position region, with stable direction across eye-data coverage thresholds.
- Structure: stacked allocation summary, participant-level difference-in-differences, tightly scaled threshold-sensitivity intervals, and region-specific condition ratios.
- Visual priority: the ball-to-position contrast; reference lines remain close to the observed estimates.

## Figure 4 — Exploratory scan-path organization

- Conclusion: corrected high/low-AUC differences are sparse and restricted to three zero-gravity duration dyads.
- Structure: an all-dyad evidence map, bootstrap intervals for the corrected contrasts, and a directed transition network with neutral arrows and separate effect labels.
- Visual priority: multiplicity-adjusted evidence and interval width; arrows indicate direction without reusing the data-series colours.

## Figure S1 — Task structure and time course

- Conclusion: the accuracy contrast is broadly visible across speed levels and within-condition trial bins, while its magnitude varies by speed and ball-size pairing.
- Structure: accuracy by speed, a muted diverging size-pair heat map with in-cell values, and a full-width within-condition trial-course panel.
- Visual priority: stable condition direction alongside local heterogeneity.

## Figure S2 — Quality control and robustness

- Conclusion: endpoint-specific sample flow, eye coverage, sequence-data thresholds, and leave-one-participant-out checks make the robustness boundaries explicit.
- Structure: compact sample-flow diagram, eye-coverage histogram, dyad-count threshold distribution, and leave-one-out stability intervals.
- Visual priority: transparent denominators and thresholds without unused axes or empty coordinate regions.
