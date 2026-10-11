"""
pressure_score.py - Competitive pressure score (rule-based).

A weighted sum of six hand-set factor scores (0-10 each), rounded and clamped
to 1-10. There is no model and no training data: the weights and the rules
below are the whole method, and the report prints every weight, factor score
and input so a reader can recompute the result.
"""

from typing import Any, Dict, List, Optional

from .models import SiteIntelligence

WEIGHTS = {
    'platform_maturity': 0.15,
    'price_competitiveness': 0.20,
    'marketing_sophistication': 0.20,
    'trust_signals': 0.15,
    'shipping_advantage': 0.15,
    'brand_strength': 0.15,
}

PLATFORM_SCORES = {
    'Shopify': 9, 'BigCommerce': 8, 'WooCommerce': 7,
    'Magento': 7, 'Squarespace': 6, 'Wix': 5, 'Custom/Unknown': 4,
}
BNPL = ('Klarna', 'Afterpay', 'Affirm')

# The rule behind each factor, as printed in the report.
RULES = {
    'en': {
        'platform_maturity': "Shopify 9, BigCommerce 8, WooCommerce/Magento 7, Squarespace 6, Wix 5, unknown 4",
        'price_competitiveness': "median price <$25: 9, <$50: 7, <$100: 5, otherwise 3; unknown 5",
        'marketing_sophistication': "1 + popup 2 + email capture 2 + loyalty 2 + referral 2 + announcement bar 1 (max 10)",
        'trust_signals': "1 + review platform 3 + reviews >100: 2 / >0: 1 + BNPL 2 + 3 or more payment methods 1 (max 10)",
        'shipping_advantage': "free shipping on everything 9, threshold <$50: 7, <$100: 5, otherwise 3; unknown 5",
        'brand_strength': "5 + more than 500 reviews 2 + loyalty 1 + 3 or more categories 1 (max 10)",
    },
    'zh': {
        'platform_maturity': "Shopify 9，BigCommerce 8，WooCommerce/Magento 7，Squarespace 6，Wix 5，未知 4",
        'price_competitiveness': "中位价 <$25: 9，<$50: 7，<$100: 5，其余 3；未知 5",
        'marketing_sophistication': "1 + 弹窗 2 + 邮件订阅 2 + 会员 2 + 推荐 2 + 公告栏 1（最高 10）",
        'trust_signals': "1 + 评论平台 3 + 评论数 >100: 2 / >0: 1 + 分期付款 2 + 支付方式 ≥3 种 1（最高 10）",
        'shipping_advantage': "全场免运费 9，门槛 <$50: 7，<$100: 5，其余 3；未知 5",
        'brand_strength': "5 + 评论数 >500 加 2 + 会员 1 + 品类 ≥3 个 1（最高 10）",
    },
}

FACTOR_NAMES = {
    'en': {
        'platform_maturity': 'Platform maturity',
        'price_competitiveness': 'Price competitiveness',
        'marketing_sophistication': 'Marketing tactics',
        'trust_signals': 'Trust signals',
        'shipping_advantage': 'Shipping offer',
        'brand_strength': 'Brand signals',
    },
    'zh': {
        'platform_maturity': '平台成熟度',
        'price_competitiveness': '价格竞争力',
        'marketing_sophistication': '营销手段',
        'trust_signals': '信任要素',
        'shipping_advantage': '运费优惠',
        'brand_strength': '品牌信号',
    },
}

INPUT_NAMES = {
    'en': {
        'platform': 'platform', 'price_median': 'median price', 'has_popup': 'popup',
        'has_email_capture': 'email capture', 'has_loyalty': 'loyalty', 'has_referral': 'referral',
        'has_announcement_bar': 'announcement bar', 'review_platform': 'review platform',
        'review_count': 'reviews', 'bnpl': 'BNPL', 'payment_methods': 'payment methods',
        'free_shipping_threshold': 'free-shipping threshold', 'categories': 'categories',
    },
    'zh': {
        'platform': '平台', 'price_median': '中位价', 'has_popup': '弹窗',
        'has_email_capture': '邮件订阅', 'has_loyalty': '会员', 'has_referral': '推荐',
        'has_announcement_bar': '公告栏', 'review_platform': '评论平台',
        'review_count': '评论数', 'bnpl': '分期付款', 'payment_methods': '支付方式数',
        'free_shipping_threshold': '免运费门槛', 'categories': '品类数',
    },
}


def _price_score(median: Optional[float]) -> int:
    if not median or median <= 0:
        return 5
    if median < 25:
        return 9
    if median < 50:
        return 7
    if median < 100:
        return 5
    return 3


def _shipping_score(threshold: Optional[float]) -> int:
    if threshold is None:
        return 5
    if threshold == 0:
        return 9
    if threshold < 50:
        return 7
    if threshold < 100:
        return 5
    return 3


def score_pressure(intel: SiteIntelligence) -> Dict[str, Any]:
    """
    Competitive pressure score for one site.

    Returns {'score': 1-10, 'weighted_sum': float, 'factors': [{'key', 'weight',
    'score', 'inputs'}]} in WEIGHTS order.
    """
    platform = intel.platform.value
    median = intel.price_median if intel.price_median is not None else intel.price_min
    reviews = intel.total_reviews or 0
    payments = intel.payment_methods or []
    bnpl = [m for m in payments if m in BNPL]
    ship = intel.shipping_policy
    threshold = getattr(ship, 'free_shipping_threshold', None) if ship else None

    marketing = 1 + 2 * sum(bool(x) for x in (intel.has_popup, intel.has_email_capture,
                                               intel.has_loyalty_program, intel.has_referral_program))
    marketing += 1 if intel.announcement_bar_text else 0
    trust = 1 + (3 if intel.review_platform else 0) + (2 if reviews > 100 else 1 if reviews > 0 else 0)
    trust += (2 if bnpl else 0) + (1 if len(payments) >= 3 else 0)
    brand = 5 + (2 if reviews > 500 else 0) + (1 if intel.has_loyalty_program else 0)
    brand += 1 if len(intel.categories or []) >= 3 else 0

    factors: List[Dict[str, Any]] = [
        {'key': 'platform_maturity', 'score': PLATFORM_SCORES.get(platform, 5),
         'inputs': {'platform': platform}},
        {'key': 'price_competitiveness', 'score': _price_score(median),
         'inputs': {'price_median': median}},
        {'key': 'marketing_sophistication', 'score': min(marketing, 10),
         'inputs': {'has_popup': intel.has_popup, 'has_email_capture': intel.has_email_capture,
                    'has_loyalty': intel.has_loyalty_program, 'has_referral': intel.has_referral_program,
                    'has_announcement_bar': bool(intel.announcement_bar_text)}},
        {'key': 'trust_signals', 'score': min(trust, 10),
         'inputs': {'review_platform': intel.review_platform or None, 'review_count': intel.total_reviews,
                    'bnpl': bnpl, 'payment_methods': len(payments)}},
        {'key': 'shipping_advantage', 'score': _shipping_score(threshold),
         'inputs': {'free_shipping_threshold': threshold}},
        {'key': 'brand_strength', 'score': min(brand, 10),
         'inputs': {'review_count': intel.total_reviews, 'has_loyalty': intel.has_loyalty_program,
                    'categories': len(intel.categories or [])}},
    ]
    for f in factors:
        f['weight'] = WEIGHTS[f['key']]
    total = sum(f['weight'] * f['score'] for f in factors)
    return {'score': max(1, min(10, round(total))), 'weighted_sum': round(total, 2), 'factors': factors}


def format_input(name: str, value: Any, lang: str) -> str:
    """One input as 'label value' in the report language; None is 'unknown'."""
    zh = lang == 'zh'
    label = INPUT_NAMES['zh' if zh else 'en'].get(name, name)
    if value is None or value == []:
        shown = '未知' if zh else 'unknown'
        if name == 'bnpl':
            shown = '无' if zh else 'none'
    elif isinstance(value, bool):
        shown = ('是' if value else '否') if zh else ('yes' if value else 'no')
    elif isinstance(value, list):
        shown = ', '.join(str(v) for v in value)
    elif isinstance(value, float):
        shown = f"${value:g}" if name in ('price_median', 'free_shipping_threshold') else f"{value:g}"
    elif isinstance(value, int) and name in ('price_median', 'free_shipping_threshold'):
        shown = f"${value}"
    else:
        shown = str(value)
    return f"{label} {shown}" if not zh else f"{label}：{shown}"
