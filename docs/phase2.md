# Phase 2 changes

One section per batch, in commit order. Fixture scores are re-measured after every batch with
`python scripts/score_fixtures.py`; Phase 1 numbers are in `docs/baseline/`.

## Batch 1 - B1: synthetic ML removed, rule-based pressure score

- `PricingPredictor` (XGBoost / RandomForest fitted at start-up on 500 `np.random` rows) is deleted
  with its report section ("Pricing Strategy Recommendations": competitor median, suggested
  low / optimal / high), its translation keys, its config keys (`enable_pricing_prediction`,
  `pricing_model_path`) and the `data/*.pkl` ignore rule.
- `ThreatScorer` ("ML classification", no model) becomes `modules/pressure_score.py`:
  **competitive pressure score (rule-based)**. Same six factors and weights, same 1-10 rounding.
  report.md prints, per site, the score, the exact weighted sum, and a table of every factor with
  its weight, factor score, weighted contribution, inputs and rule. The unused
  `GradientBoostingClassifier` / `LabelEncoder` imports, `enable_threat_scoring` and
  `threat_model_path` are gone.
- Two behaviour changes in the score, both because the old inputs were wrong:
  - it runs on every scan; before it only ran with `--ai` **and** a reachable Ollama, although
    nothing in it uses the LLM;
  - the shipping factor reads `shipping_policy.free_shipping_threshold`; the old code read a
    top-level key `to_dict()` never produces, so that factor was always the neutral 5.
- AI wording: report.md shows the AI banner, "Key Insights (AI)" and the positioning text only
  when the Ollama step produced that text (`SiteIntelligence.ai_model` is set only then, and names
  the model). The template fallback (`建议启用Ollama...`) is never shown as AI output. The business
  report's methodology names the LLM and model only for the sites where it ran; otherwise it says
  the analysis is rule-based.
- requirements.txt: removed xgboost, scikit-learn, numpy, html5lib, pandas, sqlite-utils,
  python-dateutil, html2text, ratelimit, deepdiff. Batch 6 does not need deepdiff (change detection
  is a field-by-field comparison in `snapshot_store.py`), so its unused import is removed too.
  `tests/test_dependencies.py` fails if a requirement is not imported or a removed one comes back.
- Not exercised here: no Ollama in this environment. The analyzer contract is tested with a stubbed
  `OllamaClient` (`tests/test_ai_labels.py`).
- Fixture scores unchanged (shopify 12/1/3, woo 9/1/6, blocked 10/0/6).
