# Offline evaluations

`scenarios/rules_baseline.yaml` contains frozen provider payloads and expected hazard
and severity outcomes. The runner calls the production source parsers, packaged
thresholds and deterministic screening rules without using the network or database.

Run the eval scenarios on demand:

```bash
uv run pytest -m eval
```

Regenerate the committed rules-only baseline report:

```bash
uv run python -m ews.evals.runner \
  --output evals/reports/rules-baseline-v1.json
```

The metrics treat a district/hazard pair as a hazard detection. Severity accuracy is
calculated over correctly detected district/hazard pairs, so detecting the right hazard
at the wrong level increases recall but not severity accuracy.

Groundedness is the share of alert texts that pass the verifier gating publication:
every number and date in the evidence, and no other hazard or severity named. The
hold rate is the share that would be held. For the rules-only system these describe
the template wording, which is never revised, so the hold rate is one minus
groundedness; they are the figures model-written alerts are compared against.
