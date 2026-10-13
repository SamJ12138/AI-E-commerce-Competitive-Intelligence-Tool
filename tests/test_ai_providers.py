"""The AI provider setting: ollama or deepseek, off unless configured. DeepSeek is called through
requests with a fake HTTP transport (a requests adapter that answers from a list), so no test here
touches the network except the one marked `live`, which skips unless DEEPSEEK_API_KEY is set."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import requests

from modules import ai_analyzer, obs

REPO = Path(__file__).resolve().parent.parent
KEY = "sk-TEST-SECRET-0123456789"
PROMPT_MARK = "PROMPT-SENTINEL-7f3a"
COMPLETION = {"id": "x", "object": "chat.completion", "model": "deepseek-chat",
              "choices": [{"index": 0, "finish_reason": "stop",
                           "message": {"role": "assistant", "content": "MODEL-ANSWER"}}],
              "usage": {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168}}


class FakeTransport(requests.adapters.BaseAdapter):
    """Answers each request with the next item: (status, body, headers) or an exception to raise."""

    def __init__(self, answers):
        super().__init__()
        self.answers = list(answers)
        self.requests = []

    def send(self, request, **kwargs):
        self.requests.append(request)
        item = self.answers.pop(0)
        if isinstance(item, BaseException):
            raise item
        status, body, headers = item
        resp = requests.Response()
        resp.status_code = status
        resp._content = (body if isinstance(body, str) else json.dumps(body)).encode("utf-8")
        resp.headers.update(headers)
        resp.url, resp.request = request.url, request
        return resp

    def close(self):
        pass


def _provider(answers, sleeps=None):
    transport = FakeTransport(answers)
    session = requests.Session()
    session.mount("https://", transport)
    provider = ai_analyzer.DeepSeekProvider(api_key=KEY, session=session,
                                            sleep=(sleeps.append if sleeps is not None else lambda s: None))
    return provider, transport


@pytest.fixture
def run_log(tmp_path):
    obs.init_run(log_dir=str(tmp_path), run_id="ai")
    path = tmp_path / "run_ai.jsonl"
    yield lambda: [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    obs.close_run()


def _call(provider):
    return ai_analyzer.LLMClient(provider).generate(f"user {PROMPT_MARK}", system=f"system {PROMPT_MARK}")


def _ai_calls(events):
    return [e for e in events if e["stage"] == "ai" and e["context"].get("kind") == "ai_call"]


def _no_secrets(events):
    text = json.dumps(events, ensure_ascii=False)
    assert KEY not in text and PROMPT_MARK not in text


def test_success_posts_one_chat_completion_and_logs_tokens(run_log):
    provider, transport = _provider([(200, COMPLETION, {})])
    assert _call(provider) == "MODEL-ANSWER"
    (req,) = transport.requests
    assert req.method == "POST" and req.url == "https://api.deepseek.com/chat/completions"
    assert req.headers["Authorization"] == f"Bearer {KEY}"
    body = json.loads(req.body)
    assert body["model"] == "deepseek-chat" and body["stream"] is False
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    (e,) = _ai_calls(run_log())
    assert e["event"] == "success" and e["error_type"] is None
    ctx = e["context"]
    assert (ctx["provider"], ctx["model"]) == ("deepseek", "deepseek-chat")
    assert (ctx["prompt_tokens"], ctx["completion_tokens"]) == (123, 45)
    assert ctx["latency_ms"] >= 0 and e["duration_ms"] == ctx["latency_ms"]
    _no_secrets(run_log())


def test_401_is_auth_and_not_retried(run_log):
    provider, transport = _provider([(401, {"error": {"message": f"Authentication Fails, key {KEY[-4:]}"}}, {})])
    assert _call(provider) is None
    assert len(transport.requests) == 1
    (e,) = _ai_calls(run_log())
    assert (e["event"], e["error_type"]) == ("fail", "auth")
    assert e["context"]["provider"] == "deepseek" and e["context"]["model"] == "deepseek-chat"
    assert KEY[-4:] not in json.dumps(e)   # the response body is not logged
    _no_secrets(run_log())


def test_429_is_retried_once_then_succeeds(run_log):
    sleeps = []
    provider, transport = _provider([(429, {"error": "busy"}, {"Retry-After": "3"}), (200, COMPLETION, {})], sleeps)
    assert _call(provider) == "MODEL-ANSWER"
    assert len(transport.requests) == 2 and sleeps == [3.0]
    (e,) = _ai_calls(run_log())
    assert e["event"] == "success" and e["context"]["retries"] == 1


def test_429_twice_is_rate_limit(run_log):
    sleeps = []
    provider, transport = _provider([(429, "", {}), (429, "", {})], sleeps)
    assert _call(provider) is None
    assert len(transport.requests) == 2 and len(sleeps) == 1
    (e,) = _ai_calls(run_log())
    assert (e["event"], e["error_type"]) == ("fail", "rate_limit")


def test_timeout(run_log):
    provider, _ = _provider([requests.exceptions.ReadTimeout("read timed out")])
    assert _call(provider) is None
    (e,) = _ai_calls(run_log())
    assert (e["event"], e["error_type"]) == ("fail", "timeout")
    _no_secrets(run_log())


@pytest.mark.parametrize("body", ["{not json", {"choices": []}, {"unexpected": 1}])
def test_malformed_body_is_parse(run_log, body):
    provider, _ = _provider([(200, body, {"Content-Type": "application/json"})])
    assert _call(provider) is None
    (e,) = _ai_calls(run_log())
    assert (e["event"], e["error_type"]) == ("fail", "parse")


def test_ollama_provider_logs_the_same_fields(run_log, monkeypatch):
    def chat(model, messages, options=None):
        return {"message": {"content": "LOCAL-ANSWER"}, "prompt_eval_count": 10, "eval_count": 5}
    monkeypatch.setattr(ai_analyzer, "ollama", type("M", (), {"chat": staticmethod(chat)}), raising=False)
    monkeypatch.setattr(ai_analyzer.OllamaProvider, "is_available", lambda self: True)
    assert _call(ai_analyzer.OllamaProvider(model="qwen2.5:7b")) == "LOCAL-ANSWER"
    (e,) = _ai_calls(run_log())
    ctx = e["context"]
    assert (ctx["provider"], ctx["model"], ctx["prompt_tokens"], ctx["completion_tokens"]) == (
        "ollama", "qwen2.5:7b", 10, 5)
    _no_secrets(run_log())


def test_key_is_read_from_the_env_file_and_the_environment_wins(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nOTHER=1\nDEEPSEEK_API_KEY = 'from-file'\n", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert ai_analyzer.read_secret("DEEPSEEK_API_KEY", env_file) == "from-file"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-env")
    assert ai_analyzer.read_secret("DEEPSEEK_API_KEY", env_file) == "from-env"
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    assert ai_analyzer.read_secret("DEEPSEEK_API_KEY", tmp_path / "missing.env") is None


def test_dotenv_is_ignored_by_git():
    assert subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=REPO).returncode == 0


# --- main.py: the setting -------------------------------------------------------------------

def _main(tmp_path, *args, config="", env_file_text=None):
    (tmp_path / "sites.txt").write_text("http://127.0.0.1:9/\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text(config, encoding="utf-8")
    env_file = tmp_path / "test.env"
    if env_file_text is not None:
        env_file.write_text(env_file_text, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
    env.update(ECI_LOG_DIR=str(tmp_path / "logs"), ECI_ENV_FILE=str(env_file), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "main.py", "--sites", str(tmp_path / "sites.txt"),
                           "--outdir", str(tmp_path / "out"), "--config", str(tmp_path / "config.yaml"),
                           *args], cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)


def test_ai_without_a_provider_exits_1_naming_the_config_key(tmp_path):
    proc = _main(tmp_path, "--ai")
    assert proc.returncode == 1
    lines = [l for l in (proc.stdout + proc.stderr).splitlines() if l.strip()]
    assert len(lines) == 1 and "ai_provider" in lines[0], lines
    assert not (tmp_path / "out").exists()


def test_deepseek_without_a_key_exits_1_naming_the_variable(tmp_path):
    proc = _main(tmp_path, "--ai", config="ai_provider: deepseek\n", env_file_text="OTHER=1\n")
    assert proc.returncode == 1
    lines = [l for l in (proc.stdout + proc.stderr).splitlines() if l.strip()]
    assert len(lines) == 1 and "DEEPSEEK_API_KEY" in lines[0], lines


def test_unknown_provider_exits_1(tmp_path):
    proc = _main(tmp_path, "--ai", config="ai_provider: gpt\n")
    assert proc.returncode == 1 and "ai_provider" in proc.stdout + proc.stderr


def test_provider_without_ai_flag_leaves_ai_off(tmp_path):
    # the key is set, so only the missing --ai keeps the step off; nothing is sent anywhere
    proc = _main(tmp_path, "--max-pages", "1", config="ai_provider: deepseek\nrate_limit_delay: 0\n",
                 env_file_text=f"DEEPSEEK_API_KEY={KEY}\n")
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-1500:]
    log = next((tmp_path / "logs").glob("run_*.jsonl")).read_text(encoding="utf-8")
    assert '"kind": "ai_call"' not in log and KEY not in log and KEY not in proc.stdout + proc.stderr


def test_config_example_documents_the_provider_keys():
    import main
    assert main.CONFIG_KEYS["ai_provider"] is None and main.CONFIG_KEYS["ai_model"] is None
    text = (REPO / "config.example.yaml").read_text(encoding="utf-8")
    assert "deepseek" in text and "ollama" in text and "DEEPSEEK_API_KEY" in text


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("DEEPSEEK_API_KEY"), reason="DEEPSEEK_API_KEY not set")
def test_live_deepseek_round_trip(run_log):
    provider = ai_analyzer.DeepSeekProvider(api_key=os.environ["DEEPSEEK_API_KEY"])
    text = ai_analyzer.LLMClient(provider).generate("Reply with the single word OK.", system="Be brief.")
    assert text and "OK" in text.upper()
    (e,) = _ai_calls(run_log())
    assert e["context"]["prompt_tokens"] > 0 and e["context"]["completion_tokens"] > 0
    assert os.environ["DEEPSEEK_API_KEY"] not in json.dumps(run_log())
