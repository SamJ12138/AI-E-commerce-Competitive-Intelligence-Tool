"""
insight_generator.py - Generate Chinese insights and recommendations.

Transforms extracted intelligence into actionable Chinese bullet points
and merchant recommendations.
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime

from .models import (
    SiteIntelligence, ChangeReport, Platform, 
    ShippingPolicy, ReturnPolicy
)

logger = logging.getLogger(__name__)


class InsightGenerator:
    """
    Generates insights from site intelligence.
    Supports both English and Chinese output.
    
    Produces:
    - Key Insights - 6-12 bullet points
    - Actionable Recommendations - 3 bullets
    - Evidence - Links and extracted values
    """
    
    def __init__(self, language: str = 'zh'):
        """Initialize with language preference."""
        self.language = language
        self.is_en = language == 'en'
    
    def generate_insights(self, intel: SiteIntelligence) -> Dict[str, List[str]]:
        """
        Generate all insights for a site.
        
        Args:
            intel: SiteIntelligence object
            
        Returns:
            Dictionary with 'key_insights', 'recommendations', 'evidence'
        """
        result = {
            'key_insights': [],
            'recommendations': [],
            'evidence': []
        }
        
        # Generate key insights
        result['key_insights'] = self._generate_key_insights(intel)
        
        # Generate recommendations
        result['recommendations'] = self._generate_recommendations(intel)
        
        # Generate evidence
        result['evidence'] = self._generate_evidence(intel)
        
        return result
    
    def _generate_key_insights(self, intel: SiteIntelligence) -> List[str]:
        """Generate 6-12 key insight bullets in Chinese."""
        insights = []
        
        # Platform insight
        platform_names = {
            Platform.SHOPIFY: "Shopify建站",
            Platform.WOOCOMMERCE: "WooCommerce（WordPress插件）",
            Platform.MAGENTO: "Magento企业级平台",
            Platform.BIGCOMMERCE: "BigCommerce平台",
            Platform.WIX: "Wix建站平台",
            Platform.SQUARESPACE: "Squarespace建站",
            Platform.CUSTOM: "自建/未知平台",
        }
        platform_text = platform_names.get(intel.platform, "未知平台")
        insights.append(f"【平台】使用{platform_text}，技术成熟度{'高' if intel.platform == Platform.SHOPIFY else '中等'}")
        
        # Brand positioning
        if intel.brand_description_zh:
            insights.append(f"【定位】{intel.brand_description_zh}")
        elif intel.meta_description:
            insights.append(f"【定位】{intel.meta_description[:80]}")
        
        # Categories
        if intel.categories:
            cats = '、'.join(intel.categories[:5])
            insights.append(f"【品类】主营{cats}，{'品类聚焦' if len(intel.categories) <= 3 else '品类覆盖较广'}")
        
        # Pricing
        if intel.price_min and intel.price_max:
            price_range = f"${intel.price_min:.0f}-${intel.price_max:.0f}"
            median_text = f"，中位数${intel.price_median:.0f}" if intel.price_median else ""
            price_tier = self._get_price_tier(intel.price_median or intel.price_min)
            insights.append(f"【价格带】{price_range}{median_text}，属于{price_tier}定位")
        
        # Discounts
        if intel.has_discounts:
            insights.append(f"【促销力度】存在促销折扣，{intel.discount_summary if intel.discount_summary else '部分商品打折'}")
        
        # Bundles/Subscriptions
        if intel.has_bundles or intel.has_subscriptions:
            models = []
            if intel.has_bundles:
                models.append("捆绑销售")
            if intel.has_subscriptions:
                models.append("订阅模式")
            insights.append(f"【销售模式】采用{'、'.join(models)}，利于提升客单价")
        
        # Promotions
        if intel.announcement_bar_text:
            insights.append(f"【公告栏】{intel.announcement_bar_text[:60]}...")
        
        if intel.has_popup or intel.has_email_capture:
            tactics = []
            if intel.has_popup:
                tactics.append("弹窗")
            if intel.has_email_capture:
                tactics.append("邮件订阅")
            insights.append(f"【获客手段】使用{'和'.join(tactics)}收集用户数据，可复用")
        
        # Loyalty/Referral
        if intel.has_loyalty_program or intel.has_referral_program:
            programs = []
            if intel.has_loyalty_program:
                programs.append("会员积分")
            if intel.has_referral_program:
                programs.append("推荐返利")
            insights.append(f"【用户留存】有{'、'.join(programs)}体系，重视复购")
        
        # Shipping
        if intel.shipping_policy:
            ship = intel.shipping_policy
            if ship.free_shipping_threshold is not None:
                if ship.free_shipping_threshold == 0:
                    insights.append("【运费策略】全场免运费，竞争激烈")
                else:
                    insights.append(f"【运费策略】满${ship.free_shipping_threshold:.0f}免运费，可参考设定门槛")
            
            if ship.estimated_days_min:
                days = f"{ship.estimated_days_min}-{ship.estimated_days_max}天" if ship.estimated_days_max else f"{ship.estimated_days_min}天内"
                insights.append(f"【时效】配送约{days}，{'符合美国本土消费者预期' if ship.estimated_days_min <= 7 else '时效较长需优化'}")
        
        # Returns
        if intel.return_policy and intel.return_policy.return_days:
            ret = intel.return_policy
            free_text = "，且免费退货" if ret.free_returns else ""
            insights.append(f"【退换政策】{ret.return_days}天退货窗口{free_text}，对跨境卖家成本控制有挑战")
        
        # Trust signals
        if intel.review_platform:
            review_text = f"共{intel.total_reviews}条评论" if intel.total_reviews else "有评论系统"
            insights.append(f"【社交证明】使用{intel.review_platform}，{review_text}，建立信任")
        
        # Payment methods
        bnpl_methods = [m for m in intel.payment_methods if m in ['Klarna', 'Afterpay', 'Affirm', 'Sezzle']]
        if bnpl_methods:
            insights.append(f"【支付方式】支持{'/'.join(bnpl_methods)}分期付款，降低购买门槛")
        
        # Pixels
        active_pixels = [p.name for p in intel.pixels if p.detected]
        if active_pixels:
            insights.append(f"【营销工具】检测到{'/'.join(active_pixels[:3])}，重视数据追踪与再营销")
        
        # Limit to 12 insights
        return insights[:12]
    
    def _generate_recommendations(self, intel: SiteIntelligence) -> List[str]:
        """Generate 3 actionable recommendations in Chinese."""
        recommendations = []
        
        # Price/positioning recommendation
        if intel.price_median:
            if intel.price_median < 30:
                recommendations.append("测试相似价格带产品，走量为主，配合免运费门槛$25-35")
            elif intel.price_median < 80:
                recommendations.append("中等价格带需强调品质和品牌故事，考虑增加产品视频和详细描述")
            else:
                recommendations.append("高客单价市场，需投资品牌建设和优质客服，考虑使用分期付款")
        
        # Promotion recommendation
        if intel.has_email_capture and not intel.has_popup:
            recommendations.append("参考其邮件收集策略，建议增加首单折扣弹窗，转化率可提升15-25%")
        elif intel.has_popup:
            recommendations.append("该站使用弹窗收集邮件，建议参考其时机和文案，测试类似策略")
        
        # Trust/conversion recommendation
        if intel.review_platform:
            recommendations.append(f"参考其使用的{intel.review_platform}评论系统，真实评论对转化至关重要")
        elif not intel.total_reviews:
            recommendations.append("该站评论系统不明显，这是您的差异化机会，优先建立强评论体系")
        
        # Shipping recommendation
        if intel.shipping_policy:
            ship = intel.shipping_policy
            if ship.free_shipping_threshold and ship.free_shipping_threshold > 0:
                recommendations.append(f"参考其${ship.free_shipping_threshold}免运费门槛，结合您的客单价设定合理阈值")
            elif ship.free_shipping_threshold == 0:
                recommendations.append("该站全场免运费，建议将运费计入产品定价或设置较低的免运费门槛竞争")
        
        # Analytics recommendation
        active_pixels = [p.name for p in intel.pixels if p.detected]
        if 'Meta Pixel' in active_pixels and 'TikTok Pixel' not in active_pixels:
            recommendations.append("该站重视Facebook广告，如您目标人群偏年轻可考虑同时投放TikTok")
        
        # Fill to 3 recommendations
        default_recs = [
            "分析其热销品类，测试相似产品线",
            "研究其产品页面布局和文案风格",
            "监控其价格变动，适时调整竞争策略",
        ]
        
        while len(recommendations) < 3:
            for rec in default_recs:
                if rec not in recommendations:
                    recommendations.append(rec)
                    break
            if len(recommendations) >= 3:
                break
        
        return recommendations[:3]
    
    def _generate_evidence(self, intel: SiteIntelligence) -> List[str]:
        """Generate evidence list with links and values."""
        evidence = []
        
        evidence.append(f"分析网址: {intel.url}")
        evidence.append(f"扫描时间: {intel.scan_timestamp.strftime('%Y-%m-%d %H:%M')}")
        evidence.append(f"平台检测: {intel.platform.value} (置信度 {intel.platform_confidence:.0%})")
        
        if intel.price_min and intel.price_max:
            evidence.append(f"价格区间: ${intel.price_min:.2f} - ${intel.price_max:.2f}")
        
        if intel.shipping_policy and intel.shipping_policy.free_shipping_threshold is not None:
            evidence.append(f"免运费门槛: ${intel.shipping_policy.free_shipping_threshold:.0f}")
        
        if intel.return_policy and intel.return_policy.return_days:
            evidence.append(f"退货期限: {intel.return_policy.return_days}天")
        
        if intel.total_reviews:
            evidence.append(f"评论数量: {intel.total_reviews}")
        
        if intel.pages_crawled:
            evidence.append(f"分析页面数: {len(intel.pages_crawled)}")
        
        if intel.errors:
            evidence.append(f"采集警告: {len(intel.errors)}个页面有问题")
        
        return evidence
    
    def _get_price_tier(self, price: float) -> str:
        """Classify price into tier."""
        if price < 20:
            return "低价走量"
        elif price < 50:
            return "中低端"
        elif price < 100:
            return "中端"
        elif price < 200:
            return "中高端"
        else:
            return "高端"
    
    def format_change_report_zh(self, report: ChangeReport) -> List[str]:
        """
        Format change report as Chinese bullet points.
        
        Args:
            report: ChangeReport object
            
        Returns:
            List of change description strings
        """
        if not report.has_changes():
            return ["与上次扫描相比无明显变化"]
        
        changes = []
        
        changes.append(f"对比时间: {report.previous_scan.strftime('%Y-%m-%d')} → {report.current_scan.strftime('%Y-%m-%d')}")
        
        for change in report.price_changes:
            changes.append(f"💰 {change}")
        
        for change in report.promo_changes:
            changes.append(f"📢 {change}")
        
        for product in report.new_products:
            changes.append(f"🆕 {product}")
        
        for product in report.removed_products:
            changes.append(f"❌ {product}")
        
        for change in report.category_changes:
            changes.append(f"📂 {change}")
        
        for change in report.policy_changes:
            changes.append(f"📋 {change}")
        
        return changes


def generate_insights(intel: SiteIntelligence, language: str = 'zh') -> Dict[str, List[str]]:
    """
    Convenience function for insight generation.
    
    Args:
        intel: SiteIntelligence object
        language: 'en' for English, 'zh' for Chinese (default)
        
    Returns:
        Dictionary with insights
    """
    generator = InsightGenerator(language=language)
    return generator.generate_insights(intel)


def format_changes_zh(report: Optional[ChangeReport]) -> List[str]:
    """
    Format change report in Chinese.
    
    Args:
        report: ChangeReport object or None
        
    Returns:
        List of change strings
    """
    if report is None:
        return ["首次扫描，无历史数据对比"]
    
    generator = InsightGenerator()
    return generator.format_change_report_zh(report)
