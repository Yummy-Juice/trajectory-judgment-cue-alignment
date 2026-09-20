# Questionnaire analysis report

## Dataset

- Respondents: **286**
- Original submission timestamps were removed from the public dataset.
- Public respondent IDs were newly assigned and do not encode the source identifier.

## Requested comparison 1: original Q14

Among the **262** respondents who selected one of the two focal Q14 interpretations:

- **58 (22.1%)** selected 2D plane motion after collision, like billiards.
- **204 (77.9%)** selected 3D zero/microgravity motion without considering downward gravity.
- A paired-samples t-test was conducted on two binary indicators for the same respondents (category 2 minus category 1): **t(261) = 10.84, p < .001**.
- Mean difference in the binary indicators (3D zero/microgravity minus 2D billiards): **0.557**, 95% CI **[0.456, 0.658]**.
- Wilson 95% CI for the zero/microgravity proportion among focal responses: **[72.5%, 82.5%]**.

The t-test is conditional on the two focal options; the **24** other Q14 responses are not treated as support for either focal interpretation.

## Requested comparison 2: original Q13 versus original Q14

Binary indicators were defined within each respondent:

- Original Q13 indicator = selected the 3D falling-motion interpretation with downward gravity.
- Original Q14 indicator = selected the 3D zero/microgravity interpretation without downward gravity.

Marginally, **246/286 (86.0%)** endorsed the Q13 gravity-consistent interpretation, compared with **204/286 (71.3%)** for the Q14 zero-gravity-consistent interpretation.

Because both indicators came from the same respondents, a paired-samples t-test was conducted on the two binary indicators:

- Q13-only: **66**
- Q14-only: **24**
- Both: **180**
- Neither: **16**
- Paired t-test for Q14 zero/microgravity minus Q13 gravity-consistent: **t(285) = -4.58, p < .001**.
- Mean difference in the binary indicators (Q14 minus Q13): **-0.147**, 95% CI **[-0.210, -0.084]**.

Thus, the gravity-consistent interpretation was endorsed more often in original Q13 than the zero-gravity-consistent interpretation was endorsed in original Q14, with a statistically significant paired marginal difference.

## Interpretation boundary

These results show how respondents described the task and how their interpretations differed across the two questionnaire prompts. They support a condition-associated difference in reported task understanding. They do not, by themselves, establish that an internal gravity prior was causally violated or updated, because the two task contexts may also differ in motion profile, cue alignment, and perceived task demands.

## Reproduction

Run:

```text
python analyze_questionnaire.py
```

The script writes the CSV tables, JSON summary, and PNG figure to `questionnaire_outputs/`.
