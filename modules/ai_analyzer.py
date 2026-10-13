"""
ai_analyzer.py - The optional LLM step (--ai), off unless a provider is configured.

Providers (config key ai_provider):
- ollama: a local model served by Ollama (default model qwen2.5:7b). Nothing leaves the machine.
- deepseek: DeepSeek's OpenAI-compatible chat completions API (default model deepseek-chat),
  called with requests. The key is read from DEEPSEEK_API_KEY (environment, else the repo's .env)
  and is never printed or logged.

Every call writes one run-log event (stage "ai", kind "ai_call"): provider, model, prompt and
completion tokens, latency, and on failure error_type (auth, rate_limit, timeout, parse, http,
external_api). The prompt text and the key are never logged.

This is the only part of the tool that is AI. The competitive pressure score is
a fixed rubric in pressure_score.py and runs without it.
"""

import logging
import os
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
DEFAULT_MODELS = {"ollama": "qwen2.5:7b", "deepseek": "deepseek-chat"}
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
        response = ollama.chat(model=self.model, messages=messages, options={"temperature": 0.7, "top_p": 0.9})
        return ChatResult(text=response["message"]["content"], prompt_tokens=_get(response, "prompt_eval_count"),
                          completion_tokens=_get(response, "eval_count"), finish_reason=_get(response, "done_reason"))


class DeepSeekProvider:
    """DeepSeek's OpenAI-compatible chat completions endpoint, called with requests (no SDK).

    A 429 is retried once, after Retry-After seconds (default 2, at most 20). 401/403 is auth, a
    second 429 is rate_limit, a body that is not a chat completion is parse.
    """

    name = "deepseek"
    URL = "https://api.deepseek.com/chat/completions"

    def __init__(self, api_key: str, model: str = DEFAULT_MODELS["deepseek"], session=None,
                 timeout: float = 60, sleep=time.sleep, temperature: float = 0.7, max_tokens: int = 1500):
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
                   "temperature": self.temperature, "max_tokens": self.max_tokens}
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
                          finish_reason=choice.get("finish_reason"), retries=attempt)

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

    def is_available(self) -> bool:
        return self.provider.is_available()

    def generate(self, prompt: str, system: str = None) -> Optional[str]:
        """The model's text, or None when the call failed (logged with its error_type)."""
        if not self.is_available():
            return None
        context = {"kind": "ai_call", "provider": self.provider.name, "model": self.model}
        started = time.perf_counter()
        try:
            result = self.provider.chat(system, prompt)
        except Exception as exc:
            latency = round((time.perf_counter() - started) * 1000, 2)
            message = str(exc) if isinstance(exc, AIError) else type(exc).__name__
            obs.event("ai", "fail", duration_ms=latency, error_type=error_type_of(exc), error_message=message,
                      latency_ms=latency, prompt_tokens=None, completion_tokens=None, **context)
            logger.error(f"{self.provider.name} call failed: {message}")
            return None
        latency = round((time.perf_counter() - started) * 1000, 2)
        obs.event("ai", "success", duration_ms=latency, latency_ms=latency, prompt_tokens=result.prompt_tokens,
                  completion_tokens=result.completion_tokens, finish_reason=result.finish_reason,
                  retries=result.retries, **context)
        return result.text


@dataclass
class AIConfig:
    """Configuration for AI analysis."""
    provider: str = "ollama"
    model: Optional[str] = None   # None: the provider's default model

    # Analysis settings
    enable_chinese_insights: bool = True
    enable_competitive_analysis: bool = True


class ChineseInsightGenerator:
    """
    Generate Chinese insights with the configured provider.
    """

    SYSTEM_PROMPT = """你是一位专业的跨境电商竞品分析师，专门帮助中国卖家分析美国DTC品牌。
你的分析应该：
1. 直接、实用、可操作
2. 使用专业的电商术语
3. 给出具体的数据支持
4. 提供可立即执行的建议
请用简洁的中文回答。"""

    def __init__(self, client: LLMClient):
        self.client = client

    def generate_insights(self, intel_data: Dict) -> Dict[str, List[str]]:
        """
        Generate AI-powered Chinese insights from site intelligence.

        Args:
            intel_data: Dictionary with extracted site data

        Returns:
            Dictionary with 'key_insights', 'recommendations', 'analysis'
        """
        if not self.client.is_available():
            obs.degraded("ai_analyzer.py:ChineseInsightGenerator.generate_insights", "external_api",
                         "provider unavailable", fallback="template insights", stage="ai")
            return self._fallback_insights(intel_data)

        prompt = self._build_prompt(intel_data)
        response = self.client.generate(prompt, self.SYSTEM_PROMPT)

        if response:
            return self._parse_response(response)
        else:
            obs.degraded("ai_analyzer.py:ChineseInsightGenerator.generate_insights", "external_api",
                         "empty LLM response", fallback="template insights", stage="ai")
            return self._fallback_insights(intel_data)

    def _build_prompt(self, data: Dict) -> str:
        """
        Prompt from intel.to_dict(). Only fields the pipeline produces are used, and a line is
        left out when its value is unknown (no 'N/A' placeholders). Shipping and return values
        are read from the nested shipping_policy / return_policy.
        """
        ship = data.get('shipping_policy') or {}
        ret = data.get('return_policy') or {}
        yes_no = lambda v: None if v is None else ('是' if v else '否')
        threshold = ship.get('free_shipping_threshold')
        price_range = (f"${data['price_min']:g} - ${data['price_max']:g}"
                       if data.get('price_min') is not None and data.get('price_max') is not None else None)
        sections = [
            ('基本信息', [
                ('网站域名', data.get('domain')),
                ('电商平台', data.get('platform')),
                ('品牌名称', data.get('brand_name')),
                ('品牌定位（页面原文）', f"“{data['brand_positioning']}”" if data.get('brand_positioning') else None),
            ]),
            ('产品与定价', [
                ('产品品类', ', '.join((data.get('categories') or [])[:5]) or None),
                ('价格区间', price_range),
                ('中位价格', f"${data['price_median']:g}" if data.get('price_median') is not None else None),
                ('货币', data.get('currency')),
                ('有折扣促销', yes_no(data.get('has_discounts'))),
            ]),
            ('营销策略', [
                ('公告栏内容', (data.get('announcement_bar_text') or '')[:100] or None),
                ('有弹窗', yes_no(data.get('has_popup'))),
                ('邮件订阅', yes_no(data.get('has_email_capture'))),
                ('会员计划', yes_no(data.get('has_loyalty_program'))),
                ('推荐计划', yes_no(data.get('has_referral_program'))),
            ]),
            ('物流与政策', [
                ('免运费门槛', None if threshold is None else ('全场免运费' if threshold == 0 else f"${threshold:g}")),
                ('退货天数', f"{ret['return_days']}天" if ret.get('return_days') else None),
                ('免费退货', yes_no(ret.get('free_returns')) if ret else None),
            ]),
            ('信任要素', [
                ('评论平台', data.get('review_platform')),
                ('评论数量', data.get('total_reviews')),
                ('支付方式', ', '.join((data.get('payment_methods') or [])[:5]) or None),
            ]),
        ]
        lines = ["请分析以下美国电商网站的竞品情报数据（未列出的项目表示未采集到）：", ""]
        for title, facts in sections:
            present = [(label, value) for label, value in facts if value not in (None, '', [])]
            if present:
                lines.append(f"**{title}**")
                lines += [f"- {label}: {value}" for label, value in present]
                lines.append("")
        lines += ["请提供：", "", "## 关键洞察（6-8条）", "针对这个竞品的核心竞争力和策略分析", "",
                  "## 可复制的动作建议（3条）", "中国跨境卖家下周可以立即测试的具体行动", ""]
        return "\n".join(lines)

    def _parse_response(self, response: str) -> Dict[str, List[str]]:
        """Parse LLM response into structured data."""
        result = {
            'key_insights': [],
            'recommendations': [],
            'threat_analysis': '',
            'pricing_advice': '',
            'raw_response': response
        }

        # Simple parsing - split by sections
        sections = response.split('##')

        for section in sections:
            section = section.strip()
            if not section:
                continue

            lines = section.split('\n')
            title = lines[0].strip().lower()
            content = '\n'.join(lines[1:]).strip()

            if '关键洞察' in title or '洞察' in title:
                # Extract bullet points
                for line in content.split('\n'):
                    line = line.strip()
                    if line and (line.startswith('-') or line.startswith('•') or
                                 line[0].isdigit()):
                        # Clean up the line
                        cleaned = line.lstrip('-•0123456789.').strip()
                        if cleaned:
                            result['key_insights'].append(cleaned)

            elif '建议' in title or '动作' in title:
                for line in content.split('\n'):
                    line = line.strip()
                    if line and (line.startswith('-') or line.startswith('•') or
                                 line[0].isdigit()):
                        cleaned = line.lstrip('-•0123456789.').strip()
                        if cleaned:
                            result['recommendations'].append(cleaned)

            elif '威胁' in title or '评估' in title:
                result['threat_analysis'] = content

            elif '定价' in title:
                result['pricing_advice'] = content

        return result

    def _fallback_insights(self, data: Dict) -> Dict[str, List[str]]:
        """Generate template-based insights when AI is not available."""
        price_min = data.get('price_min') or 0
        price_max = data.get('price_max') or 0
        return {
            'key_insights': [
                f"【平台】使用{data.get('platform', 'Unknown')}平台",
                f"【价格】价格区间${price_min:.0f}-${price_max:.0f}",
            ],
            'recommendations': [
                "建议启用Ollama获取AI智能分析",
                "运行: ollama pull qwen2.5:7b",
            ],
            'threat_analysis': 'AI分析不可用，请安装Ollama',
            'pricing_advice': 'AI分析不可用',
            'ai_powered': False
        }


class CompetitiveAnalyzer:
    """
    Deep competitive analysis using LLM reasoning.
    """

    SYSTEM_PROMPT = """你是一位资深的电商竞争分析专家，擅长分析品牌定位、市场策略和竞争格局。
请基于提供的数据进行深度分析，给出专业、具体的商业洞察。"""

    def __init__(self, client: LLMClient):
        self.client = client

    def analyze_positioning(self, intel_data: Dict) -> str:
        """Analyze brand positioning and market strategy."""
        if not self.client.is_available():
            obs.degraded("ai_analyzer.py:CompetitiveAnalyzer.analyze_positioning", "external_api",
                         "provider unavailable", fallback="'AI分析不可用' string", stage="ai")
            return "AI分析不可用"

        facts = [
            ('品牌', intel_data.get('brand_name')),
            ('品牌定位（页面原文）', intel_data.get('brand_positioning')),
            ('产品', ', '.join(intel_data.get('categories') or []) or None),
            ('价格带', f"${intel_data['price_min']:.0f} - ${intel_data['price_max']:.0f}"
             if intel_data.get('price_min') is not None and intel_data.get('price_max') is not None else None),
            ('促销策略', intel_data.get('announcement_bar_text') or None),
        ]
        known = "\n".join(f"{label}: {value}" for label, value in facts if value)

        prompt = f"""分析这个品牌的市场定位：

{known}

请分析：
1. 目标客户群体
2. 品牌定位（高端/中端/低端）
3. 核心竞争优势
4. 潜在弱点

用简洁的中文回答，每点不超过2句话。"""

        return self.client.generate(prompt, self.SYSTEM_PROMPT) or "分析失败"

    def compare_competitors(self, intel_list: List[Dict]) -> str:
        """Generate comparative analysis across multiple competitors."""
        if not self.client.is_available() or len(intel_list) < 2:
            return "需要至少2个竞品进行对比分析"

        competitors_summary = "\n".join([
            f"- {d.get('domain')}: {d.get('platform')}, ${(d.get('price_min') or 0):.0f}-${(d.get('price_max') or 0):.0f}"
            for d in intel_list[:5]
        ])

        prompt = f"""对比分析以下竞品：

{competitors_summary}

请提供：
1. 价格定位对比
2. 营销策略差异
3. 各自优劣势
4. 市场机会点

用表格或对比形式呈现。"""

        return self.client.generate(prompt, self.SYSTEM_PROMPT) or "对比分析失败"


class AIAnalyzer:
    """
    Runs the LLM calls for one site (insights, positioning).
    """

    def __init__(self, config: AIConfig = None, provider=None):
        self.config = config or AIConfig()
        self.provider = provider or make_provider(self.config.provider, self.config.model)
        self.client = LLMClient(self.provider)
        self.model = self.provider.model

        # Initialize components
        self.insight_generator = ChineseInsightGenerator(self.client)
        self.competitive_analyzer = CompetitiveAnalyzer(self.client)
        obs.event("ai", "success", kind="ai_init", provider=self.provider.name, model=self.model,
                  ollama_importable=OLLAMA_AVAILABLE)

    def is_ai_available(self) -> bool:
        """Check if AI features are available."""
        return self.client.is_available()

    def analyze_site(self, intel_data: Dict) -> Dict[str, Any]:
        """
        Perform comprehensive AI analysis on a site.

        Args:
            intel_data: Site intelligence dictionary

        Returns:
            Dictionary with all AI analysis results
        """
        available = self.client.is_available()
        results = {
            'ai_available': available,
            'provider': self.provider.name,
            'model_used': self.model if available else None,
        }

        # Generate Chinese insights
        if self.config.enable_chinese_insights:
            results['insights'] = self.insight_generator.generate_insights(intel_data)
            from_llm = 'raw_response' in results['insights']
            results['insights_from_llm'] = from_llm
            obs.note('ai_insights', results['insights'].get('key_insights'), 'ai' if from_llm else 'default',
                     f"{self.provider.name} {self.model} response parsed by '##' headings" if from_llm
                     else "template fallback (_fallback_insights)", stage='ai')

        # Competitive positioning analysis
        if self.config.enable_competitive_analysis:
            results['positioning'] = self.competitive_analyzer.analyze_positioning(intel_data)
            from_llm = results['positioning'] not in ("AI分析不可用", "分析失败")
            results['positioning_from_llm'] = from_llm
            obs.note('ai_positioning', results['positioning'], 'ai' if from_llm else 'default',
                     f"{self.provider.name} {self.model} free text" if from_llm else "fixed failure string",
                     stage='ai')

        return results

    def compare_sites(self, intel_list: List[Dict]) -> str:
        """Generate comparative analysis across multiple sites."""
        return self.competitive_analyzer.compare_competitors(intel_list)


# Convenience function
def create_analyzer(provider: str = "ollama", model: Optional[str] = None) -> AIAnalyzer:
    """Create an AI analyzer for a provider (and model, else the provider's default)."""
    return AIAnalyzer(AIConfig(provider=provider, model=model))
