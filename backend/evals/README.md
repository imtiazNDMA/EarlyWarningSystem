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
