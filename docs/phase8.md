# Phase 8: AI provider setting, DeepSeek as a second provider

The `--ai` step had one provider (a local Ollama model) and had never run against a real model.
This phase adds a provider setting, DeepSeek's API as a second provider, rewrites the prompt and
its parser, and runs it once on a stored allbirds scan. No store was fetched in this phase.

## 1. Provider abstraction

- Config key `ai_provider` (`ollama` or `deepseek`, no default) and `ai_model` (empty: `qwen2.5:7b`
  for ollama, `deepseek-flash` for deepseek; see section 3); `--ai-provider` / `--ai-model` on the command line win
  over the file. `--ai` with no provider exits 1 with one line naming `ai_provider`, before anything
  is printed or fetched; an unknown provider, or deepseek without a key, exits 1 the same way. A
  provider set without `--ai` does nothing.
- Client: plain `requests` (already a dependency), not the `openai` package. The endpoint is one
  POST to `https://api.deepseek.com/chat/completions` with a bearer token; an SDK would add a
  dependency for that one call. `requirements.txt` is unchanged.
- The key is read from `DEEPSEEK_API_KEY`: the environment first, else `.env` in the repository
  root (ignored by git; `ECI_ENV_FILE` points elsewhere, used by the tests). The project has no
  separate backend, so "backend .env" is this file. The key is held by the provider object only
  (its repr leaves it out) and goes into the Authorization header and nowhere else.
- Errors: 401/403 `auth` (not retried), 429 retried once after `Retry-After` (default 2 s, at most
  20 s), a second 429 `rate_limit`, no response within the timeout `timeout`, a body that is not a
  chat completion `parse`, any other status `http`, a connection error `external_api`. `auth` and
  `rate_limit` are new run-log error types (`modules/obs.py`, `scripts/failure_report.py`). The
  logged message is the status code only, never the response body (a DeepSeek 401 body quotes the
  end of the key).
- Run log: every call is one event, stage `ai`, `kind: ai_call`, with `provider`, `model`,
  `prompt_tokens`, `completion_tokens`, `latency_ms` (also `duration_ms`), `retries`,
  `finish_reason`, and `error_type` on failure. Ollama's token counts are its `prompt_eval_count`
  and `eval_count`. The prompt text and the key are not logged.
- Tests (`tests/test_ai_providers.py`): a fake HTTP transport (a requests adapter that answers from
  a list) for success, 401, 429 then 200, 429 twice, timeout, and three malformed bodies; the
  key and a sentinel in the prompt are checked absent from the run log. The command-line checks run
  `main.py` in a subprocess. `test_live_deepseek_round_trip` is marked `live` and skips unless
  `DEEPSEEK_API_KEY` is in the environment (a key only in `.env` does not run it, so the pre-commit
  hook never calls the paid API).
- The fake-Ollama end-to-end test now sets `ai_provider: ollama` in its config file.
- `AIConfig.ollama_host` is gone: it was never passed to the client (observations s.3). The `ollama`
  package reads `OLLAMA_HOST`.

## 2. Prompt and output

- What the Ollama path sent before: two calls per store, both in Chinese whatever `--lang` said
  (6-8 "key insights" plus 3 actions, and a free-text positioning paragraph). The prompt already
  held only fields the pipeline produces and left unknown values out; the N/A placeholders listed
  in observations s.3 had been removed in Phase 2 (B1). So "keep only real fields" needed no
  change of substance; the field list was renamed to the report.csv column names so a citation can
  be checked against it.
- Now one call per store (`build_prompt`): the known fields as `- field: value` lines (21 possible
  fields plus `products_sampled`; unknown values left out, never written as N/A), then a request
  for `## Positioning` (two or three sentences), `## Risks` (three numbered items: where the store
  is strong) and `## Opportunities` (three: gaps a competing seller could use), each citing the
  fact it rests on as `[field: value]`. The model writes in the report language; the headings stay
  English so the parser finds them. Temperature 0.3.
- `parse_analysis`: text outside the three sections is ignored (a preamble, a closing offer);
  `**Risks**` and `Risks:` count as headings; an item wrapped onto an indented line is joined.
  It is a parse failure when a section is missing or repeated, a list does not have exactly three
  items, or the positioning text or an item cites no field or a field the prompt did not list. A
  response cut off at the token limit (`finish_reason: length`) is a parse failure too. Only the
  field name of a citation is checked, not its value.
- A parse failure is logged on the `ai_call` event (`error_type: parse`, with the tokens the call
  used), and the store's AI section in both reports says "AI analysis unavailable" with the reason;
  none of the model's text is printed.
- `SiteIntelligence.ai_insights` / `ai_positioning` / `ai_model` are replaced by one
  `ai_analysis` dict (provider, model, and the three sections or an error). It is not stored in
  the snapshot.
- Reports: the rule-based Key Insights and Recommendations are always printed; the AI section is
  added after them (it used to replace them), titled `AI analysis (<provider> / <model>)` with a
  line saying a model wrote it from the scanned values and that the tool does not check it. The
  business report's per-store profile has the same section, and its methodology line names the
  provider and model and says where the scanned values went: "were sent to DeepSeek's API
  (api.deepseek.com)" or "were sent to a local Ollama model and did not leave this machine", plus
  whether the answer was used. Only the listed fields go into the prompt, never page HTML.
- Removed: `ChineseInsightGenerator`, `CompetitiveAnalyzer` (its `compare_competitors` was never
  called), the template fallback, `create_analyzer`.
- Tests: `tests/test_ai_prompt.py` (prompt fields, three canned responses: clean, extra prose,
  truncated; five shapes that must fail; one call per store; parse failures logged; labels in
  both reports and both languages); `tests/test_ai_fake_ollama.py` and `tests/test_ai_labels.py`
  rewritten for the one-call shape.

## 3. One real run, and what it is worth

- The owner put `DEEPSEEK_API_KEY` in `.env`. `GET /models` with it lists `deepseek-flash` and
  `deepseek-v4-pro`; `deepseek-chat` (the model the brief named) is not offered, and DeepSeek's
  pricing page does not list it. The owner asked for the flash model, so the default is now
  `deepseek-flash`.
- `scripts/ai_from_snapshot.py` rebuilds report.md, report.csv and business_report.md from the
  scans stored in a database, with the AI step, and writes `ai_run.json` (scan time, the facts the
  prompt listed, the call's run-log record). It fetches nothing. It ran on
  `output/demo-video/run/data/intel_cache.db`, the allbirds.com scan of 2026-10-12 20:37 that the
  demo video was made from. The committed allbirds sample comes from the 18:32 scan, whose
  database was not kept.
- First call (16:55 UTC): failed. DeepSeek turns thinking mode on unless told otherwise; the
  hidden reasoning counts against `max_tokens`, used all 1500, and no answer came back
  (`finish_reason: length`, 466 prompt tokens, 8.4 s). The parser rejected it as `parse`, as
  designed, and the report said "AI analysis unavailable". Fix: requests send
  `"thinking": {"type": "disabled"}`, and the run log also records `reasoning_tokens` and
  `prompt_cache_hit_tokens`. The owner approved one more call.
- Second call (16:57 UTC): success, 441 prompt tokens (0 cache hits), 470 completion tokens,
  3.36 s. Cost at DeepSeek's published off-peak `deepseek-flash` rate ($0.15 per million input
  tokens on a cache miss, $0.60 per million output tokens; the peak rate is double): $0.00035, plus
  $0.00097 for the failed call, $0.0013 in all. Output, metadata and verdict:
  [docs/sample/real/allbirds/ai-deepseek.md](sample/real/allbirds/ai-deepseek.md).
- Verdict: mostly a restatement of the tables. It said one thing the tables do not: the store's
  description promises "FREE shipping & returns" while its terms say free shipping over $100 and
  paid returns, which the hand-read ground truth confirms. It made two errors, each with a
  correct citation: it took the 50-product sample for the size of the catalogue, and called a
  store with 1 of 50 products marked down a discounter (the prompt has only `has_discounts: yes`).
  The README says so.
- The `live` test was not run: it would be a third paid call, and the two real calls exercise
  the same code.
