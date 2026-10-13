"""
insight_generator.py - Rule-based insights and recommendations, in English or Chinese.

Transforms extracted intelligence into bullet points and merchant recommendations.
Every sentence exists in both languages; text taken from the site (announcement
bar, positioning) is quoted as it appears on the page.
"""

import logging
from typing import List, Dict, Optional

from .models import SiteIntelligence, ChangeReport, Platform
from .product_sample import describe as describe_sample, price_note

logger = logging.getLogger(__name__)

TEXT = {
    'en': {
        'platform_names': {
            Platform.SHOPIFY: "Shopify", Platform.WOOCOMMERCE: "WooCommerce (WordPress plugin)",
            Platform.MAGENTO: "Magento", Platform.BIGCOMMERCE: "BigCommerce", Platform.WIX: "Wix",
            Platform.SQUARESPACE: "Squarespace", Platform.PRESTASHOP: "PrestaShop",
            Platform.CUSTOM: "a custom or unidentified platform",
        },
        'platform': "Platform: runs on {name}",
        'positioning': "Positioning: “{text}” ({source})",
        'sources': {'meta description': 'meta description', 'title': 'page title', 'headline': 'headline'},
        'categories': "Categories: {cats}, {breadth}",
        'focused': "a focused range", 'broad': "a broad range",
        'list_sep': ", ",
        'price_band': "Price band: {range}{median}, {tier}",
        'median': ", median ${median:.0f}",
        'tiers': ["low price, volume-driven", "lower mid-range", "mid-range", "upper mid-range", "premium"],
        'discounts': "Discounts: {count} of {total} priced products are marked down{avg}",
        'avg_discount': ", {pct:.0f}% off on average",
        'sales_models': "Sales model: {models}, which raises order value",
        'bundles': "bundles", 'subscriptions': "subscriptions",
        'announcement': "Announcement bar: “{text}”",
        'acquisition': "Lead capture: uses {tactics} to collect customer contacts",
        'popup': "popup", 'email': "email signup", 'and': " and ",
        'retention': "Retention: {programs}",
        'loyalty': "loyalty program", 'referral': "referral program",
        'free_all': "Shipping: free shipping on every order",
        'free_over': "Shipping: free shipping over ${threshold:.0f}",
        'delivery': "Delivery time: about {days} days",
        'returns': "Returns: {days}-day return window{free}",
        'free_returns': ", returns are free",
        'reviews': "Social proof: {platform}{count}",
        'review_count': ", {count} reviews",
        'bnpl': "Payments: buy now, pay later via {methods}",
        'pixels': "Tracking: {pixels} detected",
        'recs': {
            'low_price': "Test products in a similar price band; with a median under $30, volume and a "
                         "free-shipping threshold of $25-35 matter most",
            'mid_price': "In a mid-range band, product videos, detailed descriptions and the brand story carry "
                         "the sale",
            'high_price': "At high order values, invest in brand and service and consider buy now, pay later",
            'email_no_popup': "They collect emails without a popup; a first-order discount popup is worth testing",
            'popup': "They use a popup to collect emails; review its timing and copy and test a similar one",
            'reviews': "They use {platform} for reviews; genuine reviews are central to conversion",
            'no_reviews': "No review system is visible on this site; a strong review program would set you apart",
            'threshold': "Their free-shipping threshold is ${threshold:.0f}; set yours against your own average "
                         "order value",
            'free_all': "They ship everything free; build shipping into prices or set a low threshold",
            'meta_no_tiktok': "They advertise with Meta; if your audience is younger, test TikTok as well",
            'defaults': ["Look at their best-selling categories and test similar products",
                         "Study their product page layout and copy",
                         "Track their prices and adjust when they move"],
        },
        'evidence': {
            'url': "Analyzed URL: {url}", 'time': "Scan time: {time}",
            'platform': "Platform detected: {platform} (confidence {confidence:.0%})",
            'price': "Price range: ${lo:.2f} - ${hi:.2f}", 'no_price': "Price range: {note}",
            'sample': "Product sample: {text}",
            'threshold': "Free-shipping threshold: ${threshold:.0f}",
            'returns': "Return window: {days} days", 'reviews': "Reviews: {count}",
            'pages': "Pages analyzed: {count}", 'errors': "Fetch warnings: {count} pages had problems",
        },
        'changes': {
            'none': "No notable change since the last scan",
            'first': "First scan - no history to compare",
            'compared': "Compared: {old} → {new}",
        },
    },
    'zh': {
        'platform_names': {
            Platform.SHOPIFY: "Shopify建站", Platform.WOOCOMMERCE: "WooCommerce（WordPress插件）",
            Platform.MAGENTO: "Magento企业级平台", Platform.BIGCOMMERCE: "BigCommerce平台",
            Platform.WIX: "Wix建站平台", Platform.SQUARESPACE: "Squarespace建站",
            Platform.PRESTASHOP: "PrestaShop平台", Platform.CUSTOM: "自建/未知平台",
        },
        'platform': "【平台】使用{name}",
        'positioning': "【定位】“{text}”（{source}）",
        'sources': {'meta description': '页面描述', 'title': '页面标题', 'headline': '首页标题'},
        'categories': "【品类】主营{cats}，{breadth}",
        'focused': "品类聚焦", 'broad': "品类覆盖较广",
        'list_sep': "、",
        'price_band': "【价格带】{range}{median}，属于{tier}定位",
        'median': "，中位数${median:.0f}",
        'tiers': ["低价走量", "中低端", "中端", "中高端", "高端"],
        'discounts': "【促销力度】{total}个有价格的商品中有{count}个打折{avg}",
        'avg_discount': "，平均约{pct:.0f}%",
        'sales_models': "【销售模式】采用{models}，利于提升客单价",
        'bundles': "捆绑销售", 'subscriptions': "订阅模式",
        'announcement': "【公告栏】“{text}”",
        'acquisition': "【获客手段】使用{tactics}收集用户数据，可复用",
        'popup': "弹窗", 'email': "邮件订阅", 'and': "和",
        'retention': "【用户留存】有{programs}体系，重视复购",
        'loyalty': "会员积分", 'referral': "推荐返利",
        'free_all': "【运费策略】全场免运费",
        'free_over': "【运费策略】满${threshold:.0f}免运费",
        'delivery': "【时效】配送约{days}天",
        'returns': "【退换政策】{days}天退货窗口{free}",
        'free_returns': "，且免费退货",
        'reviews': "【社交证明】使用{platform}{count}",
        'review_count': "，共{count}条评论",
        'bnpl': "【支付方式】支持{methods}分期付款，降低购买门槛",
        'pixels': "【营销工具】检测到{pixels}",
        'recs': {
            'low_price': "测试相似价格带产品，走量为主，配合免运费门槛$25-35",
            'mid_price': "中等价格带需强调品质和品牌故事，考虑增加产品视频和详细描述",
            'high_price': "高客单价市场，需投资品牌建设和优质客服，考虑使用分期付款",
            'email_no_popup': "参考其邮件收集策略，可测试首单折扣弹窗",
            'popup': "该站使用弹窗收集邮件，建议参考其时机和文案，测试类似策略",
            'reviews': "参考其使用的{platform}评论系统，真实评论对转化至关重要",
            'no_reviews': "该站评论系统不明显，这是您的差异化机会，优先建立强评论体系",
            'threshold': "参考其${threshold:.0f}免运费门槛，结合您的客单价设定合理阈值",
            'free_all': "该站全场免运费，建议将运费计入产品定价或设置较低的免运费门槛竞争",
            'meta_no_tiktok': "该站重视Meta广告，如您目标人群偏年轻可考虑同时投放TikTok",
            'defaults': ["分析其热销品类，测试相似产品线",
                         "研究其产品页面布局和文案风格",
                         "监控其价格变动，适时调整竞争策略"],
        },
        'evidence': {
            'url': "分析网址: {url}", 'time': "扫描时间: {time}",
            'platform': "平台检测: {platform} (置信度 {confidence:.0%})",
            'price': "价格区间: ${lo:.2f} - ${hi:.2f}", 'no_price': "价格区间: {note}",
            'sample': "产品样本: {text}",
            'threshold': "免运费门槛: ${threshold:.0f}",
            'returns': "退货期限: {days}天", 'reviews': "评论数量: {count}",
            'pages': "分析页面数: {count}", 'errors': "采集警告: {count}个页面有问题",
        },
        'changes': {
            'none': "与上次扫描相比无明显变化",
            'first': "首次扫描，无历史数据对比",
            'compared': "对比时间: {old} → {new}",
        },
    },
}


class InsightGenerator:
    """
    Rule-based insights from site intelligence, in English ('en') or Chinese ('zh').

    Produces:
    - Key Insights - up to 12 bullet points
    - Actionable Recommendations - 3 bullets
    - Evidence - links and extracted values
    """

    def __init__(self, language: str = 'zh'):
        self.language = language if language in TEXT else 'zh'
        self.t = TEXT[self.language]

    def generate_insights(self, intel: SiteIntelligence) -> Dict[str, List[str]]:
        return {
            'key_insights': self._generate_key_insights(intel),
            'recommendations': self._generate_recommendations(intel),
            'evidence': self._generate_evidence(intel),
        }

    def _generate_key_insights(self, intel: SiteIntelligence) -> List[str]:
        t = self.t
        insights = [t['platform'].format(name=t['platform_names'].get(intel.platform, intel.platform.value))]

        if intel.brand_positioning:
            source = t['sources'].get(intel.brand_positioning_source or '', intel.brand_positioning_source or '')
            insights.append(t['positioning'].format(text=intel.brand_positioning[:160], source=source))

        if intel.categories:
            insights.append(t['categories'].format(
                cats=t['list_sep'].join(intel.categories[:5]),
                breadth=t['focused'] if len(intel.categories) <= 3 else t['broad']))

        if intel.price_min and intel.price_max:
            median = t['median'].format(median=intel.price_median) if intel.price_median else ""
            insights.append(t['price_band'].format(
                range=f"${intel.price_min:.0f}-${intel.price_max:.0f}", median=median,
                tier=self._get_price_tier(intel.price_median or intel.price_min)))

        if intel.has_discounts:
            priced = [p for p in intel.all_products if p.price and p.price.current_price]
            on_sale = [p for p in priced if p.price.is_on_sale]
            pcts = [p.price.discount_percent for p in on_sale if p.price.discount_percent]
            avg = t['avg_discount'].format(pct=sum(pcts) / len(pcts)) if pcts else ""
            insights.append(t['discounts'].format(count=len(on_sale), total=len(priced), avg=avg))

        if intel.has_bundles or intel.has_subscriptions:
            models = [t['bundles']] if intel.has_bundles else []
            models += [t['subscriptions']] if intel.has_subscriptions else []
            insights.append(t['sales_models'].format(models=t['list_sep'].join(models)))

        if intel.announcement_bar_text:
            insights.append(t['announcement'].format(text=intel.announcement_bar_text[:100]))

        if intel.has_popup or intel.has_email_capture:
            tactics = [t['popup']] if intel.has_popup else []
            tactics += [t['email']] if intel.has_email_capture else []
            insights.append(t['acquisition'].format(tactics=t['and'].join(tactics)))

        if intel.has_loyalty_program or intel.has_referral_program:
            programs = [t['loyalty']] if intel.has_loyalty_program else []
            programs += [t['referral']] if intel.has_referral_program else []
            insights.append(t['retention'].format(programs=t['list_sep'].join(programs)))

        ship = intel.shipping_policy
        if ship:
            threshold = getattr(ship, 'free_shipping_threshold', None)
            if threshold == 0:
                insights.append(t['free_all'])
            elif threshold:
                insights.append(t['free_over'].format(threshold=threshold))
            days_min = getattr(ship, 'estimated_days_min', None)
            if days_min:
                days_max = getattr(ship, 'estimated_days_max', None)
                insights.append(t['delivery'].format(days=f"{days_min}-{days_max}" if days_max else days_min))

        if intel.return_policy and intel.return_policy.return_days:
            ret = intel.return_policy
            insights.append(t['returns'].format(days=ret.return_days,
                                                free=t['free_returns'] if ret.free_returns else ""))

        if intel.review_platform:
            count = t['review_count'].format(count=intel.total_reviews) if intel.total_reviews else ""
            insights.append(t['reviews'].format(platform=intel.review_platform, count=count))

        bnpl = [m for m in intel.payment_methods if m in ('Klarna', 'Afterpay', 'Affirm', 'Sezzle')]
        if bnpl:
            insights.append(t['bnpl'].format(methods='/'.join(bnpl)))

        active_pixels = [p.name for p in intel.pixels if p.detected]
        if active_pixels:
            insights.append(t['pixels'].format(pixels='/'.join(active_pixels[:3])))

        return insights[:12]

    def _generate_recommendations(self, intel: SiteIntelligence) -> List[str]:
        r = self.t['recs']
        recommendations = []

        if intel.price_median:
            if intel.price_median < 30:
                recommendations.append(r['low_price'])
            elif intel.price_median < 80:
                recommendations.append(r['mid_price'])
            else:
                recommendations.append(r['high_price'])

        # None (not determined) is never read as "no": those recommendations are left out
        if intel.has_email_capture and intel.has_popup is False:
            recommendations.append(r['email_no_popup'])
        elif intel.has_popup:
            recommendations.append(r['popup'])

        if intel.review_platform:
            recommendations.append(r['reviews'].format(platform=intel.review_platform))
        elif intel.review_platform is not None and not intel.total_reviews:
            recommendations.append(r['no_reviews'])

        threshold = getattr(intel.shipping_policy, 'free_shipping_threshold', None) if intel.shipping_policy else None
        if threshold:
            recommendations.append(r['threshold'].format(threshold=threshold))
        elif threshold == 0:
            recommendations.append(r['free_all'])

        active_pixels = [p.name for p in intel.pixels if p.detected]
        if 'Meta Pixel' in active_pixels and 'TikTok Pixel' not in active_pixels:
            recommendations.append(r['meta_no_tiktok'])

        for rec in r['defaults']:
            if len(recommendations) >= 3:
                break
            if rec not in recommendations:
                recommendations.append(rec)

        return recommendations[:3]

    def _generate_evidence(self, intel: SiteIntelligence) -> List[str]:
        e = self.t['evidence']
        evidence = [
            e['url'].format(url=intel.url),
            e['time'].format(time=intel.scan_timestamp.strftime('%Y-%m-%d %H:%M')),
            e['platform'].format(platform=intel.platform.value, confidence=intel.platform_confidence),
        ]
        if intel.price_min and intel.price_max:
            evidence.append(e['price'].format(lo=intel.price_min, hi=intel.price_max))
        elif intel.price_note:
            evidence.append(e['no_price'].format(note=price_note(intel.price_note, self.language)))
        if intel.product_sample:
            evidence.append(e['sample'].format(text=describe_sample(intel.product_sample, self.language)))
        threshold = getattr(intel.shipping_policy, 'free_shipping_threshold', None) if intel.shipping_policy else None
        if threshold is not None:
            evidence.append(e['threshold'].format(threshold=threshold))
        if intel.return_policy and intel.return_policy.return_days:
            evidence.append(e['returns'].format(days=intel.return_policy.return_days))
        if intel.total_reviews:
            evidence.append(e['reviews'].format(count=intel.total_reviews))
        if intel.pages_crawled:
            evidence.append(e['pages'].format(count=len(intel.pages_crawled)))
        if intel.errors:
            evidence.append(e['errors'].format(count=len(intel.errors)))
        return evidence

    def _get_price_tier(self, price: float) -> str:
        tiers = self.t['tiers']
        for limit, tier in zip((20, 50, 100, 200), tiers):
            if price < limit:
                return tier
        return tiers[-1]

    def format_change_report(self, report: ChangeReport) -> List[str]:
        """Change report as bullet points (the change texts are produced in this language)."""
        c = self.t['changes']
        if not report.has_changes():
            return [c['none']]
        changes = [c['compared'].format(old=report.previous_scan.strftime('%Y-%m-%d'),
                                        new=report.current_scan.strftime('%Y-%m-%d'))]
        changes += [f"💰 {x}" for x in report.price_changes]
        changes += [f"📢 {x}" for x in report.promo_changes]
        changes += [f"🆕 {x}" for x in report.new_products]
        changes += [f"❌ {x}" for x in report.removed_products]
        changes += [f"📂 {x}" for x in report.category_changes]
        changes += [f"📋 {x}" for x in report.policy_changes]
        return changes


def generate_insights(intel: SiteIntelligence, language: str = 'zh') -> Dict[str, List[str]]:
    """Insights, recommendations and evidence for one site in 'en' or 'zh'."""
    return InsightGenerator(language=language).generate_insights(intel)


def format_changes(report: Optional[ChangeReport], language: str = 'zh') -> List[str]:
    """Change report lines in 'en' or 'zh'; None means this is the first scan."""
    generator = InsightGenerator(language=language)
    if report is None:
        return [generator.t['changes']['first']]
    return generator.format_change_report(report)


def format_changes_zh(report: Optional[ChangeReport]) -> List[str]:
    """Chinese change report lines (kept for callers of the old name)."""
    return format_changes(report, 'zh')
