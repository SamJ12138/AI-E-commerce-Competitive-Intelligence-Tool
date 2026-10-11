"""
ai_analyzer.py - AI-powered analysis using local LLMs and ML models.

Provides:
- Chinese insight generation via Qwen2.5 (Ollama)
- Competitive analysis via DeepSeek/Qwen
- Pricing strategy prediction via scikit-learn/XGBoost
- Competitor threat scoring via custom classifier
"""

import logging
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import pickle
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Check for optional dependencies
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("Ollama not installed. Install with: pip install ollama")

try:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler, LabelEncoder
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not installed. Install with: pip install scikit-learn")

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logger.warning("XGBoost not installed. Install with: pip install xgboost")


@dataclass
class AIConfig:
    """Configuration for AI analysis."""
    # Ollama settings
    ollama_model: str = "qwen2.5:7b"  # or "qwen2.5:14b", "deepseek-v3"
    ollama_host: str = "http://localhost:11434"
    
    # Analysis settings
    enable_chinese_insights: bool = True
    enable_competitive_analysis: bool = True
    enable_pricing_prediction: bool = True
    enable_threat_scoring: bool = True
    
    # Model paths for saved ML models
    pricing_model_path: str = "data/pricing_model.pkl"
    threat_model_path: str = "data/threat_model.pkl"


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
                logger.warning(f"Model {self.model} not found. Available: {model_names}")
                logger.info(f"Pull the model with: ollama pull {self.model}")
                self._available = False
                
        except Exception as e:
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
            return self._fallback_insights(intel_data)
        
        prompt = self._build_prompt(intel_data)
        response = self.client.generate(prompt, self.SYSTEM_PROMPT)
        
        if response:
            return self._parse_response(response)
        else:
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


class PricingPredictor:
    """
    ML-based pricing strategy prediction using scikit-learn and XGBoost.
    """
    
    def __init__(self, model_path: str = "data/pricing_model.pkl"):
        self.model_path = Path(model_path)
        self.model = None
        self.scaler = StandardScaler() if SKLEARN_AVAILABLE else None
        self._load_or_create_model()
    
    def _load_or_create_model(self):
        """Load existing model or create new one."""
        if not SKLEARN_AVAILABLE:
            return
        
        if self.model_path.exists():
            try:
                with open(self.model_path, 'rb') as f:
                    saved = pickle.load(f)
                    self.model = saved['model']
                    self.scaler = saved['scaler']
                logger.info(f"Loaded pricing model from {self.model_path}")
            except Exception as e:
                logger.warning(f"Could not load model: {e}")
                self._create_default_model()
        else:
            self._create_default_model()
    
    def _create_default_model(self):
        """Create a default model with reasonable defaults."""
        if XGBOOST_AVAILABLE:
            self.model = xgb.XGBRegressor(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
        elif SKLEARN_AVAILABLE:
            self.model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=42
            )
        
        # Pre-train with synthetic data for reasonable predictions
        if self.model and SKLEARN_AVAILABLE:
            self._pretrain_with_synthetic_data()
    
    def _pretrain_with_synthetic_data(self):
        """Pre-train model with synthetic e-commerce pricing data."""
        np.random.seed(42)
        n_samples = 500
        
        # Features: [competitor_price, category_tier, has_reviews, has_free_shipping, brand_strength]
        X = np.column_stack([
            np.random.uniform(10, 200, n_samples),  # competitor_price
            np.random.randint(1, 4, n_samples),      # category_tier (1=low, 2=mid, 3=high)
            np.random.randint(0, 2, n_samples),      # has_reviews
            np.random.randint(0, 2, n_samples),      # has_free_shipping
            np.random.uniform(0.3, 1.0, n_samples),  # brand_strength
        ])
        
        # Target: optimal price (slightly below or competitive with competitor)
        y = X[:, 0] * (0.85 + 0.2 * X[:, 4]) + X[:, 1] * 5 - X[:, 3] * 3
        
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        
        logger.info("Pre-trained pricing model with synthetic data")
    
    def predict_optimal_price(
        self,
        competitor_price: float,
        category_tier: int = 2,
        has_reviews: bool = True,
        has_free_shipping: bool = False,
        brand_strength: float = 0.5
    ) -> Tuple[float, float, float]:
        """
        Predict optimal price range.
        
        Args:
            competitor_price: Average competitor price
            category_tier: 1=budget, 2=mid-range, 3=premium
            has_reviews: Whether your product has reviews
            has_free_shipping: Whether you offer free shipping
            brand_strength: Brand recognition score 0-1
            
        Returns:
            Tuple of (low_price, optimal_price, high_price)
        """
        if not self.model or not SKLEARN_AVAILABLE:
            # Simple rule-based fallback
            optimal = competitor_price * 0.9
            return (optimal * 0.85, optimal, optimal * 1.1)
        
        features = np.array([[
            competitor_price,
            category_tier,
            int(has_reviews),
            int(has_free_shipping),
            brand_strength
        ]])
        
        features_scaled = self.scaler.transform(features)
        optimal = self.model.predict(features_scaled)[0]
        
        # Ensure reasonable bounds
        optimal = max(5, min(optimal, competitor_price * 1.5))
        
        return (optimal * 0.9, optimal, optimal * 1.15)
    
    def save_model(self):
        """Save the trained model."""
        if self.model and SKLEARN_AVAILABLE:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.model_path, 'wb') as f:
                pickle.dump({
                    'model': self.model,
                    'scaler': self.scaler
                }, f)
            logger.info(f"Saved pricing model to {self.model_path}")


class ThreatScorer:
    """
    Score competitor threat level using ML classification.
    """
    
    # Threat level definitions
    THREAT_LEVELS = {
        1: "极低威胁",
        2: "很低威胁", 
        3: "低威胁",
        4: "较低威胁",
        5: "中等威胁",
        6: "较高威胁",
        7: "高威胁",
        8: "很高威胁",
        9: "极高威胁",
        10: "最高威胁"
    }
    
    def __init__(self):
        self.weights = {
            'platform_maturity': 0.15,
            'price_competitiveness': 0.20,
            'marketing_sophistication': 0.20,
            'trust_signals': 0.15,
            'shipping_advantage': 0.15,
            'brand_strength': 0.15
        }
    
    def calculate_threat_score(self, intel_data: Dict) -> Tuple[int, str, Dict[str, float]]:
        """
        Calculate competitor threat score.
        
        Args:
            intel_data: Site intelligence dictionary
            
        Returns:
            Tuple of (score 1-10, explanation, factor_scores)
        """
        factors = {}
        
        # Platform maturity (Shopify = most mature)
        platform = intel_data.get('platform', 'Custom/Unknown')
        platform_scores = {
            'Shopify': 9, 'BigCommerce': 8, 'WooCommerce': 7,
            'Magento': 7, 'Squarespace': 6, 'Wix': 5, 'Custom/Unknown': 4
        }
        factors['platform_maturity'] = platform_scores.get(platform, 5)
        
        # Price competitiveness (lower median = more competitive)
        price_median = intel_data.get('price_median') or intel_data.get('price_min') or 50
        if price_median and price_median > 0:
            if price_median < 25:
                factors['price_competitiveness'] = 9
            elif price_median < 50:
                factors['price_competitiveness'] = 7
            elif price_median < 100:
                factors['price_competitiveness'] = 5
            else:
                factors['price_competitiveness'] = 3
        else:
            factors['price_competitiveness'] = 5
        
        # Marketing sophistication
        marketing_score = 0
        if intel_data.get('has_popup'):
            marketing_score += 2
        if intel_data.get('has_email_capture'):
            marketing_score += 2
        if intel_data.get('has_loyalty_program'):
            marketing_score += 2
        if intel_data.get('has_referral_program'):
            marketing_score += 2
        if intel_data.get('announcement_bar_text'):
            marketing_score += 1
        factors['marketing_sophistication'] = min(marketing_score + 1, 10)
        
        # Trust signals
        trust_score = 0
        if intel_data.get('review_platform'):
            trust_score += 3
        total_reviews = intel_data.get('total_reviews') or 0
        if total_reviews > 100:
            trust_score += 2
        elif total_reviews > 0:
            trust_score += 1
        payment_methods = intel_data.get('payment_methods') or []
        if any(m in payment_methods for m in ['Klarna', 'Afterpay', 'Affirm']):
            trust_score += 2
        if len(payment_methods) >= 3:
            trust_score += 1
        factors['trust_signals'] = min(trust_score + 1, 10)
        
        # Shipping advantage
        shipping_score = 5  # neutral
        free_threshold = intel_data.get('free_shipping_threshold')
        if free_threshold is not None:
            if free_threshold == 0:
                shipping_score = 9  # Free shipping on all
            elif free_threshold < 50:
                shipping_score = 7
            elif free_threshold < 100:
                shipping_score = 5
            else:
                shipping_score = 3
        factors['shipping_advantage'] = shipping_score
        
        # Brand strength (based on available signals)
        brand_score = 5
        if total_reviews > 500:
            brand_score += 2
        if intel_data.get('has_loyalty_program'):
            brand_score += 1
        categories = intel_data.get('categories') or []
        if len(categories) >= 3:
            brand_score += 1
        factors['brand_strength'] = min(brand_score, 10)
        
        # Calculate weighted score
        total_score = sum(
            factors[k] * self.weights[k] 
            for k in self.weights.keys()
        )
        
        # Normalize to 1-10
        final_score = max(1, min(10, round(total_score)))
        
        # Generate explanation
        explanation = self._generate_explanation(final_score, factors, intel_data)
        
        return final_score, explanation, factors
    
    def _generate_explanation(
        self, 
        score: int, 
        factors: Dict[str, float],
        intel_data: Dict
    ) -> str:
        """Generate Chinese explanation for the threat score."""
        level = self.THREAT_LEVELS.get(score, "中等威胁")
        
        # Find top threats
        sorted_factors = sorted(factors.items(), key=lambda x: x[1], reverse=True)
        top_threats = sorted_factors[:2]
        
        factor_names = {
            'platform_maturity': '平台成熟度',
            'price_competitiveness': '价格竞争力',
            'marketing_sophistication': '营销专业度',
            'trust_signals': '信任要素',
            'shipping_advantage': '物流优势',
            'brand_strength': '品牌实力'
        }
        
        threat_reasons = [factor_names.get(f[0], f[0]) for f in top_threats]
        
        explanation = f"威胁等级: {score}/10 ({level})\n"
        explanation += f"主要威胁因素: {', '.join(threat_reasons)}\n"
        
        if score >= 7:
            explanation += "建议: 该竞品实力较强，需重点关注其策略变化，差异化竞争"
        elif score >= 4:
            explanation += "建议: 该竞品有一定竞争力，可借鉴其优势，针对性超越"
        else:
            explanation += "建议: 该竞品威胁较小，可专注自身增长"
        
        return explanation


class AIAnalyzer:
    """
    Main AI analysis orchestrator combining all AI capabilities.
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
        self.pricing_predictor = PricingPredictor(self.config.pricing_model_path)
        self.threat_scorer = ThreatScorer()
    
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
        
        # Competitive positioning analysis
        if self.config.enable_competitive_analysis:
            results['positioning'] = self.competitive_analyzer.analyze_positioning(intel_data)
        
        # Pricing prediction
        if self.config.enable_pricing_prediction:
            # Safely get price_median, defaulting to 50 if None
            price_median = intel_data.get('price_median')
            if price_median is None:
                price_median = intel_data.get('price_min')
            if price_median is None:
                price_median = 50  # Default fallback
            
            low, optimal, high = self.pricing_predictor.predict_optimal_price(
                competitor_price=float(price_median),
                has_reviews=bool(intel_data.get('total_reviews')),
                has_free_shipping=intel_data.get('free_shipping_threshold') == 0
            )
            results['pricing'] = {
                'competitor_median': float(price_median),
                'recommended_low': round(low, 2),
                'recommended_optimal': round(optimal, 2),
                'recommended_high': round(high, 2)
            }
        
        # Threat scoring
        if self.config.enable_threat_scoring:
            score, explanation, factors = self.threat_scorer.calculate_threat_score(intel_data)
            results['threat'] = {
                'score': score,
                'explanation': explanation,
                'factors': factors
            }
        
        return results
    
    def compare_sites(self, intel_list: List[Dict]) -> str:
        """Generate comparative analysis across multiple sites."""
        return self.competitive_analyzer.compare_competitors(intel_list)


# Convenience function
def create_analyzer(model: str = "qwen2.5:7b") -> AIAnalyzer:
    """Create an AI analyzer with specified model."""
    config = AIConfig(ollama_model=model)
    return AIAnalyzer(config)
