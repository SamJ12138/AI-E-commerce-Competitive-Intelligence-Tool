# Phase 8: AI provider setting, DeepSeek as a second provider

The `--ai` step had one provider (a local Ollama model) and had never run against a real model.
This phase adds a provider setting, DeepSeek's API as a second provider, rewrites the prompt and
its parser, and runs it once on a stored allbirds scan. No store was fetched in this phase.

## 1. Provider abstraction

- Config key `ai_provider` (`ollama` or `deepseek`, no default) and `ai_model` (empty: `qwen2.5:7b`
  for ollama, `deepseek-chat` for deepseek); `--ai-provider` / `--ai-model` on the command line win
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
