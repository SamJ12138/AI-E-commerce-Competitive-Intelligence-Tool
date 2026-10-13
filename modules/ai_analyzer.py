"""
ai_analyzer.py - The optional LLM step (--ai), off unless a provider is configured.

Providers (config key ai_provider):
- ollama: a local model served by Ollama (default model qwen2.5:7b). Nothing leaves the machine.
- deepseek: DeepSeek's OpenAI-compatible chat completions API (default model deepseek-flash),
  called with requests. The key is read from DEEPSEEK_API_KEY (environment, else the repo's .env)
  and is never printed or logged.

Every call writes one run-log event (stage "ai", kind "ai_call"): provider, model, prompt and
completion tokens (and DeepSeek's cache-hit prompt tokens), latency, and on failure error_type (auth, rate_limit, timeout, parse, http,
external_api). The prompt text and the key are never logged.

This is the only part of the tool that is AI. The competitive pressure score is
a fixed rubric in pressure_score.py and runs without it.
"""

import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from . import obs

logger = logging.getLogger(__name__)

# Check for optional dependencies
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:  # obs: import-time, reported by OllamaProvider.is_available
    OLLAMA_AVAILABLE = False

REPO = Path(__file__).resolve().parent.parent
DEFAULT_MODELS = {"ollama": "qwen2.5:7b", "deepseek": "deepseek-flash"}
PROVIDERS = tuple(DEFAULT_MODELS)
KEY_VARIABLES = {"deepseek": "DEEPSEEK_API_KEY"}


def env_file() -> Path:
    """The .env file secrets are read from: ECI_ENV_FILE, else .env in the repository root."""
    return Path(os.environ.get("ECI_ENV_FILE") or REPO / ".env")


def read_secret(name: str, path: Optional[Path] = None) -> Optional[str]:
    """The value of `name` from the environment, else from the .env file (KEY=VALUE lines)."""
    if os.environ.get(name):
        return os.environ[name]
    path = Path(path) if path is not None else env_file()
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == name:
            return value.strip().strip("'\"") or None
    return None


class AIError(Exception):
    """A failed LLM call. error_type is an obs error type; the message never holds a response body."""

    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type


@dataclass
class ChatResult:
    text: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    finish_reason: Optional[str] = None
    retries: int = 0
    cache_hit_tokens: Optional[int] = None   # DeepSeek: prompt tokens billed at the cache-hit rate
    reasoning_tokens: Optional[int] = None   # DeepSeek: completion tokens spent on hidden reasoning


def _get(obj: Any, key: str) -> Any:
    return obj.get(key) if hasattr(obj, "get") else getattr(obj, key, None)


def error_type_of(exc: BaseException) -> str:
    """obs error type for an exception raised by a provider call."""
    if isinstance(exc, AIError):
        return exc.error_type
    if isinstance(exc, requests.Timeout) or "Timeout" in type(exc).__name__:
        return "timeout"
    if isinstance(exc, (ValueError, KeyError, IndexError, TypeError)):
        return "parse"
    return "external_api"


class OllamaProvider:
    """A local model served by Ollama (the `ollama` package talks to OLLAMA_HOST, default localhost)."""

    name = "ollama"

    def __init__(self, model: str = DEFAULT_MODELS["ollama"]):
        self.model = model
        self._available = None

    def is_available(self) -> bool:
        """Check if Ollama is running and model is available."""
        if self._available is not None:
            return self._available

        if not OLLAMA_AVAILABLE:
            obs.degraded("ai_analyzer.py:OllamaProvider.is_available", "external_api",
                         "the ollama package is not installed", fallback="AI unavailable", stage="ai")
            self._available = False
            return False

        try:
            # Check if Ollama is running
            models = ollama.list()

            # Handle different response formats from ollama.list()
            # Some versions return {'models': [{'name': ...}]}
            # Others return a list directly or different structure
            model_names = []

            if isinstance(models, dict):
                model_list = models.get('models', [])
                for m in model_list:
                    if isinstance(m, dict):
                        # Try 'name' or 'model' key
                        name = m.get('name') or m.get('model') or str(m)
                        model_names.append(name)
                    else:
                        model_names.append(str(m))
            elif isinstance(models, list):
                for m in models:
                    if isinstance(m, dict):
                        name = m.get('name') or m.get('model') or str(m)
                        model_names.append(name)
                    else:
                        model_names.append(str(m))
            elif hasattr(models, 'models'):
                # Handle object with models attribute
                for m in models.models:
                    if hasattr(m, 'name'):
                        model_names.append(m.name)
                    elif hasattr(m, 'model'):
                        model_names.append(m.model)
                    else:
                        model_names.append(str(m))

            # Check if our model is available
            if any(self.model in name for name in model_names):
                self._available = True
            else:
                obs.degraded("ai_analyzer.py:OllamaProvider.is_available", "external_api",
                             f"model {self.model} not in ollama.list()", fallback="AI unavailable",
                             stage="ai", event_name="fail", models=model_names)
                logger.warning(f"Model {self.model} not found. Available: {model_names}")
                logger.info(f"Pull the model with: ollama pull {self.model}")
                self._available = False

        except Exception as e:
            obs.swallowed("ai_analyzer.py:OllamaProvider.is_available", error_type="external_api",
                          fallback="AI unavailable", stage="ai")
            logger.warning(f"Ollama not available: {e}")
            logger.info("Start Ollama with: ollama serve")
            self._available = False

        return self._available

    def chat(self, system: Optional[str], user: str) -> ChatResult:
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        response = ollama.chat(model=self.model, messages=messages, options={"temperature": 0.3})
        return ChatResult(text=response["message"]["content"], prompt_tokens=_get(response, "prompt_eval_count"),
                          completion_tokens=_get(response, "eval_count"), finish_reason=_get(response, "done_reason"))


class DeepSeekProvider:
    """DeepSeek's OpenAI-compatible chat completions endpoint, called with requests (no SDK).

    A 429 is retried once, after Retry-After seconds (default 2, at most 20). 401/403 is auth, a
    second 429 is rate_limit, a body that is not a chat completion is parse.

    Thinking mode is switched off (DeepSeek turns it on by default): its hidden reasoning counts
    against max_tokens, and on the first real run it used all 1500 and no answer came back.
    """

    name = "deepseek"
    URL = "https://api.deepseek.com/chat/completions"

    def __init__(self, api_key: str, model: str = DEFAULT_MODELS["deepseek"], session=None,
                 timeout: float = 60, sleep=time.sleep, temperature: float = 0.3, max_tokens: int = 1500):
        self._api_key = api_key
        self.model = model
        self.session = session or requests.Session()
        self.timeout = timeout
        self.sleep = sleep
        self.temperature = temperature
        self.max_tokens = max_tokens

    def __repr__(self) -> str:   # never show the key
        return f"DeepSeekProvider(model={self.model!r})"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def chat(self, system: Optional[str], user: str) -> ChatResult:
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "temperature": self.temperature, "max_tokens": self.max_tokens,
                   "thinking": {"type": "disabled"}}
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        for attempt in (0, 1):
            response = self.session.post(self.URL, json=payload, headers=headers, timeout=self.timeout)
            if response.status_code == 429 and attempt == 0:
                self.sleep(self._retry_after(response))
                continue
            break
        status = response.status_code
        if status in (401, 403):
            raise AIError("auth", f"HTTP {status} from {self.name}")
        if status == 429:
            raise AIError("rate_limit", f"HTTP 429 from {self.name} after one retry")
        if status != 200:
            raise AIError("http", f"HTTP {status} from {self.name}")
        body = response.json()
        if not isinstance(body, dict) or not body.get("choices"):
            raise AIError("parse", "response is not a chat completion (no choices)")
        choice = body["choices"][0]
        text = choice["message"]["content"]
        if not isinstance(text, str):
            raise AIError("parse", "response is not a chat completion (no message text)")
        usage = body.get("usage") or {}
        return ChatResult(text=text, prompt_tokens=usage.get("prompt_tokens"),
                          completion_tokens=usage.get("completion_tokens"),
                          finish_reason=choice.get("finish_reason"), retries=attempt,
                          cache_hit_tokens=usage.get("prompt_cache_hit_tokens"),
                          reasoning_tokens=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens"))

    @staticmethod
    def _retry_after(response) -> float:
        value = response.headers.get("Retry-After", "")
        return min(float(value), 20.0) if value.replace(".", "", 1).isdigit() else 2.0


def make_provider(name: str, model: Optional[str] = None):
    """The provider for config key ai_provider. Raises ValueError with a one-line message when the
    name is not a provider or its key is missing (the message names the setting, never a value)."""
    if name not in PROVIDERS:
        raise ValueError(f"ai_provider must be one of: {', '.join(PROVIDERS)} (got {name!r})")
    model = model or DEFAULT_MODELS[name]
    if name == "ollama":
        return OllamaProvider(model=model)
    variable = KEY_VARIABLES[name]
    key = read_secret(variable)
    if not key:
        raise ValueError(f"ai_provider {name} needs {variable}: set it in the environment or in {env_file().name}")
    return DeepSeekProvider(api_key=key, model=model)


class LLMClient:
    """One provider behind generate(); every call is one 'ai_call' event in the run log."""

    def __init__(self, provider):
        self.provider = provider
        self.model = provider.model
        self.last_error: Optional[str] = None
        self.last_call: Optional[Dict[str, Any]] = None   # what the last call logged (no prompt, no key)

    def is_available(self) -> bool:
        return self.provider.is_available()

    def generate(self, prompt: str, system: str = None, parse=None):
        """The model's text, or parse(text) when parse is given; None when the call failed or the
        text did not parse (logged with its error_type, also kept in last_error). A response cut
        off at the token limit is a parse failure."""
        self.last_error = self.last_call = None
        if not self.is_available():
            self.last_error = "external_api"
            return None
        context = {"kind": "ai_call", "provider": self.provider.name, "model": self.model}
        result = None
        started = time.perf_counter()
        try:
            result = self.provider.chat(system, prompt)
            if result.finish_reason == "length":
                raise AIError("parse", "response cut off at the token limit")
            value = parse(result.text) if parse else result.text
        except Exception as exc:
            message = str(exc) if isinstance(exc, AIError) else type(exc).__name__
            self.last_error = error_type_of(exc)
            fields = self._record("fail", started, result, context, error_type=self.last_error,
                                  error_message=message)
            obs.event("ai", "fail", duration_ms=fields["latency_ms"], error_type=self.last_error,
                      error_message=message, **fields)
            logger.error(f"{self.provider.name} call failed: {message}")
            return None
        fields = self._record("success", started, result, context)
        obs.event("ai", "success", duration_ms=fields["latency_ms"], **fields)
        return value

    def _record(self, event: str, started: float, result: Optional[ChatResult], context: Dict[str, Any],
                error_type: Optional[str] = None, error_message: Optional[str] = None) -> Dict[str, Any]:
        """The run-log fields of one call (no prompt, no key); also kept in last_call."""
        latency = round((time.perf_counter() - started) * 1000, 2)
        fields = dict(context, latency_ms=latency,
                      prompt_tokens=result.prompt_tokens if result else None,
                      prompt_cache_hit_tokens=result.cache_hit_tokens if result else None,
                      completion_tokens=result.completion_tokens if result else None,
                      reasoning_tokens=result.reasoning_tokens if result else None,
                      finish_reason=result.finish_reason if result else None,
                      retries=result.retries if result else None)
        self.last_call = dict(fields, event=event, error_type=error_type, error_message=error_message)
        return fields


# The prompt's facts, named as report.csv names them. Only these can be cited.
PROMPT_FIELDS = (
    "domain", "platform", "brand_name", "brand_positioning", "categories", "products_sampled",
    "price_min", "price_max", "price_median", "currency", "has_discounts", "announcement_bar",
    "has_popup", "has_email_capture", "has_loyalty", "has_referral", "free_shipping_threshold",
    "return_days", "free_returns", "review_platform", "review_count", "payment_methods",
)
SECTIONS = ("positioning", "risks", "opportunities")
LANGUAGE_NAMES = {"en": "English", "zh": "Simplified Chinese (简体中文)"}


def prompt_facts(data: Dict) -> Dict[str, str]:
    """{field: value as text} from intel.to_dict(), for the values the pipeline produced. An unknown
    value (None, empty) is left out, never written as N/A."""
    ship = data.get("shipping_policy") or {}
    ret = data.get("return_policy") or {}
    currency = data.get("currency")

    def money(v):
        if v is None:
            return None
        return f"${v:g}" if currency in (None, "USD") else f"{v:g} {currency}"

    def yes_no(v):
        return None if v is None else ("yes" if v else "no")

    sample = data.get("product_sample") or {}
    threshold = ship.get("free_shipping_threshold")
    values = {
        "domain": data.get("domain"),
        "platform": data.get("platform"),
        "brand_name": data.get("brand_name"),
        "brand_positioning": (data.get("brand_positioning") or "")[:300],
        "categories": ", ".join((data.get("categories") or [])[:8]),
        "products_sampled": (f"{sample['products']} products from {sample.get('collections', 0)} collections"
                             if sample.get("products") else None),
        "price_min": money(data.get("price_min")),
        "price_max": money(data.get("price_max")),
        "price_median": money(data.get("price_median")),
        "currency": currency,
        "has_discounts": yes_no(data.get("has_discounts")),
        "announcement_bar": (data.get("announcement_bar_text") or "")[:150],
        "has_popup": yes_no(data.get("has_popup")),
        "has_email_capture": yes_no(data.get("has_email_capture")),
        "has_loyalty": yes_no(data.get("has_loyalty_program")),
        "has_referral": yes_no(data.get("has_referral_program")),
        "free_shipping_threshold": (None if threshold is None else
                                    "free on every order" if threshold == 0 else money(threshold)),
        "return_days": str(ret["return_days"]) if ret.get("return_days") else None,
        "free_returns": yes_no(ret.get("free_returns")),
        "review_platform": data.get("review_platform"),
        "review_count": str(data["total_reviews"]) if data.get("total_reviews") is not None else None,
        "payment_methods": ", ".join(data.get("payment_methods") or []),
    }
    return {name: values[name] for name in PROMPT_FIELDS if values[name] not in (None, "")}


def build_prompt(data: Dict, language: str = "en"):
    """(system, user, facts) for one store. One call asks for a positioning summary, three risks and
    three opportunities, each citing a listed field as [field: value]. The section headings stay in
    English whatever the language, so the parser can find them."""
    facts = prompt_facts(data)
    system = ("You are a competitive analyst helping a small online seller. You are given facts that a "
              "scraper read from one competitor's storefront. Use only these facts: do not invent sales, "
              "traffic, customer reviews or anything else that is not listed, and do not assume a value "
              f"for a field that is not listed. Write in {LANGUAGE_NAMES.get(language, 'English')}.")
    lines = [f"Facts read from the storefront of {facts.get('domain', 'this store')} "
             "(a field that is not listed was not determined):", ""]
    lines += [f"- {name}: {value}" for name, value in facts.items()]
    lines += ["",
              "Answer with exactly these three sections, with these English headings, and nothing else:",
              "",
              "## Positioning",
              "Two or three sentences on how this store positions itself (price level, range, promise).",
              "",
              "## Risks",
              "Three numbered items: where this store is strong, so a seller competing with it should "
              "be careful.",
              "",
              "## Opportunities",
              "Three numbered items: gaps a seller competing with it could use.",
              "",
              "The positioning text and every item must cite the fact it rests on in square brackets, "
              "written [field: value] with a field name from the list above, for example "
              f"[{next(iter(facts), 'domain')}: {next(iter(facts.values()), 'example.com')}]."]
    return system, "\n".join(lines), facts


_HEADING = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*(positioning|risks|opportunities)\s*:?\s*(?:\*\*)?\s*:?\s*$",
                      re.I)
_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+(.*\S)\s*$")
_CITATION = re.compile(r"\[\s*([A-Za-z_]+)\s*:\s*[^\]]+\]")


def _check_citations(text: str, facts: Dict[str, str], where: str) -> None:
    cited = _CITATION.findall(text)
    if not cited:
        raise AIError("parse", f"{where} cites no field")
    unknown = sorted({name for name in cited if name not in facts})
    if unknown:
        raise AIError("parse", f"{where} cites fields the prompt did not list: {', '.join(unknown)}")


def parse_analysis(text: str, facts: Dict[str, str]) -> Dict[str, Any]:
    """{'positioning': str, 'risks': [3], 'opportunities': [3]} from the model's answer. Text outside
    the three sections is ignored. Raises AIError('parse') when a section is missing or repeated, a
    list does not have exactly three items, or the positioning text or an item cites no listed field
    (a cut-off answer fails one of these)."""
    body: Dict[str, List[str]] = {}
    current = None
    for line in (text or "").splitlines():
        m = _HEADING.match(line)
        if m:
            current = m.group(1).lower()
            if current in body:
                raise AIError("parse", f"section {current} appears twice")
            body[current] = []
        elif current:
            body[current].append(line)
    missing = [s for s in SECTIONS if s not in body]
    if missing:
        raise AIError("parse", f"missing section(s): {', '.join(missing)}")

    # positioning: the first paragraph under its heading
    paragraph: List[str] = []
    for line in body["positioning"]:
        if line.strip():
            paragraph.append(line.strip())
        elif paragraph:
            break
    positioning = " ".join(paragraph)
    _check_citations(positioning, facts, "positioning")

    result: Dict[str, Any] = {"positioning": positioning}
    for section in ("risks", "opportunities"):
        items: List[str] = []
        previous_was_item = False
        for line in body[section]:
            m = _ITEM.match(line)
            if m:
                items.append(m.group(1))
                previous_was_item = True
            elif previous_was_item and line[:1].isspace() and line.strip():
                items[-1] += " " + line.strip()   # an item wrapped onto an indented line
            else:
                previous_was_item = False
        if len(items) != 3:
            raise AIError("parse", f"{section} has {len(items)} items, expected 3")
        for i, item in enumerate(items, 1):
            _check_citations(item, facts, f"{section} item {i}")
        result[section] = items
    return result


@dataclass
class AIConfig:
    """Configuration for AI analysis."""
    provider: str = "ollama"
    model: Optional[str] = None   # None: the provider's default model
    language: str = "en"          # the language the model is asked to write in


class AIAnalyzer:
    """One LLM call per store: positioning, three risks, three opportunities."""

    def __init__(self, config: AIConfig = None, provider=None, language: Optional[str] = None):
        self.config = config or AIConfig()
        self.provider = provider or make_provider(self.config.provider, self.config.model)
        self.client = LLMClient(self.provider)
        self.model = self.provider.model
        self.language = language or self.config.language
        obs.event("ai", "success", kind="ai_init", provider=self.provider.name, model=self.model,
                  language=self.language, ollama_importable=OLLAMA_AVAILABLE)

    def is_ai_available(self) -> bool:
        """Check if AI features are available."""
        return self.client.is_available()

    def analyze_site(self, intel_data: Dict) -> Dict[str, Any]:
        """{'provider', 'model'} plus the parsed sections, or plus 'error' (an obs error type) when
        the call failed or its answer did not have the requested shape."""
        system, user, facts = build_prompt(intel_data, self.language)
        parsed = self.client.generate(user, system, parse=lambda text: parse_analysis(text, facts))
        result: Dict[str, Any] = {"provider": self.provider.name, "model": self.model}
        if parsed is None:
            result["error"] = self.client.last_error or "unknown"
        else:
            result.update(parsed)
        return result
