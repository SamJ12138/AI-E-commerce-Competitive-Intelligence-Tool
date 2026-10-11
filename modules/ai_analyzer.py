"""
ai_analyzer.py - The optional LLM step (--ai): a local model served by Ollama.

Provides:
- Chinese insight generation (default model qwen2.5:7b)
- Brand positioning text

This is the only part of the tool that is AI. The competitive pressure score is
a fixed rubric in pressure_score.py and runs without it.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from . import obs

logger = logging.getLogger(__name__)

# Check for optional dependencies
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:  # obs: import-time, reported by AIAnalyzer.__init__
    OLLAMA_AVAILABLE = False
    logger.warning("Ollama not installed. Install with: pip install ollama")

@dataclass
class AIConfig:
    """Configuration for AI analysis."""
    # Ollama settings
    ollama_model: str = "qwen2.5:7b"  # or "qwen2.5:14b", "deepseek-v3"
    ollama_host: str = "http://localhost:11434"
    
    # Analysis settings
    enable_chinese_insights: bool = True
    enable_competitive_analysis: bool = True


class OllamaClient:
    """
    Client for Ollama API to run local LLMs like Qwen2.5.
    """
    
    def __init__(self, model: str = "qwen2.5:7b", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host
        self._available = None
    
    def is_available(self) -> bool:
        """Check if Ollama is running and model is available."""
        if self._available is not None:
            return self._available
        
        if not OLLAMA_AVAILABLE:
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
                obs.degraded("ai_analyzer.py:OllamaClient.is_available", "external_api",
                             f"model {self.model} not in ollama.list()", fallback="AI unavailable",
                             stage="ai", event_name="fail", models=model_names)
                logger.warning(f"Model {self.model} not found. Available: {model_names}")
                logger.info(f"Pull the model with: ollama pull {self.model}")
                self._available = False
                
        except Exception as e:
            obs.swallowed("ai_analyzer.py:OllamaClient.is_available", error_type="external_api",
                          fallback="AI unavailable", stage="ai")
            logger.warning(f"Ollama not available: {e}")
            logger.info("Start Ollama with: ollama serve")
            self._available = False
        
        return self._available
    
    def generate(self, prompt: str, system: str = None) -> Optional[str]:
        """
        Generate text using the LLM.
        
        Args:
            prompt: User prompt
            system: Optional system prompt
            
        Returns:
            Generated text or None if failed
        """
        if not self.is_available():
            return None
        
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            
            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={
                    "temperature": 0.7,
                    "top_p": 0.9,
                }
            )
            
            return response['message']['content']

        except Exception as e:
            obs.swallowed("ai_analyzer.py:OllamaClient.generate", error_type="external_api",
                          fallback="None", stage="ai", model=self.model)
            logger.error(f"Ollama generation failed: {e}")
            return None


class ChineseInsightGenerator:
    """
    Generate intelligent Chinese insights using Qwen2.5 via Ollama.
    """
    
    SYSTEM_PROMPT = """你是一位专业的跨境电商竞品分析师，专门帮助中国卖家分析美国DTC品牌。
你的分析应该：
1. 直接、实用、可操作
2. 使用专业的电商术语
3. 给出具体的数据支持
4. 提供可立即执行的建议
请用简洁的中文回答。"""

    def __init__(self, ollama_client: OllamaClient):
        self.client = ollama_client
    
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
                         "Ollama unavailable", fallback="template insights", stage="ai")
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
        """Build analysis prompt from data."""
        # Safely handle potential None values
        announcement_text = data.get('announcement_bar_text') or '无'
        categories = data.get('categories', [])
        payment_methods = data.get('payment_methods', [])
        
        return f"""请分析以下美国电商网站的竞品情报数据：

**基本信息**
- 网站域名: {data.get('domain', 'Unknown')}
- 电商平台: {data.get('platform', 'Unknown')}
- 品牌名称: {data.get('brand_name', 'Unknown')}

**产品与定价**
- 产品品类: {', '.join(categories[:5]) if categories else '未知'}
- 价格区间: ${data.get('price_min') or 'N/A'} - ${data.get('price_max') or 'N/A'}
- 中位价格: ${data.get('price_median') or 'N/A'}
- 货币: {data.get('currency', 'USD')}
- 有折扣促销: {'是' if data.get('has_discounts') else '否'}

**营销策略**
- 公告栏内容: {announcement_text[:100] if announcement_text else '无'}
- 有弹窗: {'是' if data.get('has_popup') else '否'}
- 邮件订阅: {'是' if data.get('has_email_capture') else '否'}
- 会员计划: {'是' if data.get('has_loyalty_program') else '否'}
- 推荐计划: {'是' if data.get('has_referral_program') else '否'}

**物流与政策**
- 免运费门槛: ${data.get('free_shipping_threshold') or 'N/A'}
- 退货天数: {data.get('return_days') or 'N/A'}天
- 免费退货: {'是' if data.get('free_returns') else '否'}

**信任要素**
- 评论平台: {data.get('review_platform') or '无'}
- 评论数量: {data.get('total_reviews') or 'N/A'}
- 支付方式: {', '.join(payment_methods[:5]) if payment_methods else '未知'}

请提供：

## 关键洞察（6-8条）
针对这个竞品的核心竞争力和策略分析

## 可复制的动作建议（3条）
中国跨境卖家下周可以立即测试的具体行动

## 竞争威胁评估
评分1-10，并说明理由

## 定价策略建议
基于其价格区间，给出针对性的定价建议
"""
    
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

    def __init__(self, ollama_client: OllamaClient):
        self.client = ollama_client
    
    def analyze_positioning(self, intel_data: Dict) -> str:
        """Analyze brand positioning and market strategy."""
        if not self.client.is_available():
            obs.degraded("ai_analyzer.py:CompetitiveAnalyzer.analyze_positioning", "external_api",
                         "Ollama unavailable", fallback="'AI分析不可用' string", stage="ai")
            return "AI分析不可用"
        
        price_min = intel_data.get('price_min') or 0
        price_max = intel_data.get('price_max') or 0
        
        prompt = f"""分析这个品牌的市场定位：

品牌: {intel_data.get('brand_name', 'Unknown')}
产品: {', '.join(intel_data.get('categories', []))}
价格带: ${price_min:.0f} - ${price_max:.0f}
促销策略: {intel_data.get('announcement_bar_text', '无')}

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
    
    def __init__(self, config: AIConfig = None):
        self.config = config or AIConfig()
        
        # Initialize Ollama client
        self.ollama = OllamaClient(
            model=self.config.ollama_model,
            host=self.config.ollama_host
        )
        
        # Initialize components
        self.insight_generator = ChineseInsightGenerator(self.ollama)
        self.competitive_analyzer = CompetitiveAnalyzer(self.ollama)
        obs.event("ai", "success", kind="ai_init", ollama_importable=OLLAMA_AVAILABLE,
                  model=self.config.ollama_model, ollama_host_config=self.config.ollama_host,
                  ollama_host_used="ollama module default / OLLAMA_HOST env (config value not passed)")
    
    def is_ai_available(self) -> bool:
        """Check if AI features are available."""
        return self.ollama.is_available()
    
    def analyze_site(self, intel_data: Dict) -> Dict[str, Any]:
        """
        Perform comprehensive AI analysis on a site.
        
        Args:
            intel_data: Site intelligence dictionary
            
        Returns:
            Dictionary with all AI analysis results
        """
        results = {
            'ai_available': self.ollama.is_available(),
            'model_used': self.config.ollama_model if self.ollama.is_available() else None,
        }
        
        # Generate Chinese insights
        if self.config.enable_chinese_insights:
            results['insights'] = self.insight_generator.generate_insights(intel_data)
            from_llm = 'raw_response' in results['insights']
            results['insights_from_llm'] = from_llm
            obs.note('ai_insights', results['insights'].get('key_insights'), 'ai' if from_llm else 'default',
                     f"Ollama {self.config.ollama_model} response parsed by '##' headings" if from_llm
                     else "template fallback (_fallback_insights)", stage='ai')

        # Competitive positioning analysis
        if self.config.enable_competitive_analysis:
            results['positioning'] = self.competitive_analyzer.analyze_positioning(intel_data)
            from_llm = results['positioning'] not in ("AI分析不可用", "分析失败")
            results['positioning_from_llm'] = from_llm
            obs.note('ai_positioning', results['positioning'], 'ai' if from_llm else 'default',
                     f"Ollama {self.config.ollama_model} free text" if from_llm else "fixed failure string",
                     stage='ai')
        
        return results
    
    def compare_sites(self, intel_list: List[Dict]) -> str:
        """Generate comparative analysis across multiple sites."""
        return self.competitive_analyzer.compare_competitors(intel_list)


# Convenience function
def create_analyzer(model: str = "qwen2.5:7b") -> AIAnalyzer:
    """Create an AI analyzer with specified model."""
    config = AIConfig(ollama_model=model)
    return AIAnalyzer(config)
