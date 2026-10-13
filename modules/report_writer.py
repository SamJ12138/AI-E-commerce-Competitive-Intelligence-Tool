"""
report_writer.py - Generate Markdown and CSV reports.

Creates:
- Per-site Chinese insights in Markdown
- Consolidated comparison table
- CSV export
"""

import csv
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from datetime import datetime

from .models import SiteIntelligence, ChangeReport
from .insight_generator import generate_insights, format_changes
from .pressure_score import FACTOR_NAMES, RULES, format_input, score_pressure

logger = logging.getLogger(__name__)

BRANCH_NAMES = {
    'en': {'requests': 'requests', 'honest-ua': 'requests with the tool\'s own User-Agent',
           'browser': 'browser', 'cloudscraper': 'cloudscraper', 'no response': 'no response'},
    'zh': {'requests': 'HTTP 请求', 'honest-ua': '标明工具身份的 HTTP 请求', 'browser': '浏览器',
           'cloudscraper': 'cloudscraper', 'no response': '无响应'},
}
NOT_SEEN_TEXT = {
    'en': {
        'blocked': "⛔ blocked automated access. No page returned a 2xx response, so nothing about this "
                   "site is known; it is left out of every comparison, average and recommendation.",
        'unreachable': "⛔ could not be reached (no HTTP response). Nothing about this site is known; it is "
                       "left out of every comparison, average and recommendation.",
        'attempts': "Fetch branches tried",
        'not_compared': "Not compared",
        'none_compared': "No site could be compared.",
        'status': "Status",
        'short': {'blocked': "blocked automated access", 'unreachable': "could not be reached"},
    },
    'zh': {
        'blocked': "⛔ 网站阻止了自动访问。没有任何页面返回 2xx 响应，因此对该站点一无所知，"
                   "所有对比、平均值和建议均不包含该站点。",
        'unreachable': "⛔ 无法访问（没有任何 HTTP 响应）。对该站点一无所知，所有对比、平均值和建议均不包含该站点。",
        'attempts': "尝试过的抓取方式",
        'not_compared': "未参与对比",
        'none_compared': "没有可对比的站点。",
        'status': "状态",
        'short': {'blocked': "阻止了自动访问", 'unreachable': "无法访问"},
    },
}


def format_attempts(attempts: List[str], language: str) -> str:
    """['requests 403', 'cloudscraper 403'] -> 'requests (403) → cloudscraper (403)'."""
    names = BRANCH_NAMES.get(language, BRANCH_NAMES['en'])
    shown = []
    for attempt in attempts:
        branch, _, status = attempt.partition(' ')
        shown.append(f"{names.get(branch, branch)} ({names.get(status, status)})")
    return " → ".join(shown) or names['no response']


AI_TEXT = {
    'en': {
        'title': "AI analysis ({provider} / {model})",
        'note': "Written by a language model from the scanned values in this report; each point cites the "
                "field it rests on as [field: value]. The tool does not check what the model wrote.",
        'positioning': "Positioning", 'risks': "Risks", 'opportunities': "Opportunities",
        'unavailable': "AI analysis unavailable: {reason}.",
        'reasons': {'parse': "the model's answer did not have the requested sections, three items each with a "
                             "cited field (parse)",
                    'auth': "the provider refused the API key (auth)",
                    'rate_limit': "the provider's rate limit was hit twice (rate_limit)",
                    'timeout': "the provider did not answer in time (timeout)"},
        'reason_other': "the call failed ({error})",
    },
    'zh': {
        'title': "AI 分析（{provider} / {model}）",
        'note': "以下内容由语言模型根据本报告中的扫描数据写成，每条以 [字段: 值] 注明所依据的字段。工具不核实模型写的内容。",
        'positioning': "定位", 'risks': "风险", 'opportunities': "机会",
        'unavailable': "AI 分析不可用：{reason}。",
        'reasons': {'parse': "模型的回答不符合要求的格式（三个部分，各三条，每条注明字段）（parse）",
                    'auth': "服务商拒绝了 API 密钥（auth）",
                    'rate_limit': "两次触发服务商的速率限制（rate_limit）",
                    'timeout': "服务商未及时响应（timeout）"},
        'reason_other': "调用失败（{error}）",
    },
}


def ai_section_lines(ai: Dict, language: str, heading: str = "###") -> List[str]:
    """The AI section for one site, labelled with provider and model; [] when the step did not run.
    A failed or unparsable answer prints "AI analysis unavailable" and no model text."""
    if not ai:
        return []
    t = AI_TEXT.get(language, AI_TEXT['en'])
    lines = [f"{heading} 🤖 {t['title'].format(provider=ai.get('provider', '?'), model=ai.get('model', '?'))}", ""]
    error = ai.get('error')
    if error:
        reason = t['reasons'].get(error) or t['reason_other'].format(error=error)
        return lines + [t['unavailable'].format(reason=reason), ""]
    lines += [f"*{t['note']}*", "", f"**{t['positioning']}**", "", ai['positioning'], ""]
    for key in ('risks', 'opportunities'):
        lines += [f"**{t[key]}**", ""] + [f"{i}. {item}" for i, item in enumerate(ai[key], 1)] + [""]
    return lines


def not_seen_lines(intel: SiteIntelligence, language: str) -> List[str]:
    """Status lines for a site the tool could not see."""
    t = NOT_SEEN_TEXT.get(language, NOT_SEEN_TEXT['en'])
    return [f"**{t['status']}**: {t.get(intel.status, t['blocked'])}",
            f"**{t['attempts']}**: {format_attempts(intel.fetch_attempts, language)}"]


class ReportWriter:
    """
    Generates Markdown and CSV reports from site intelligence.
    Supports both English and Chinese output.
    """
    
    # Translation dictionary for report content
    TRANSLATIONS = {
        'zh': {
            'title': '跨境电商竞品情报报告',
            'generated_time': '生成时间',
            'sites_analyzed': '分析站点数',
            'url': '网址',
            'platform': '平台',
            'pressure_score': '竞争压力评分（规则计算）',
            'pressure_note': '（加权和 {total}，四舍五入并限定在 1-10）。权重和规则固定，没有模型，也没有训练数据。',
            'pressure_header': ['因素', '权重', '得分 (0-10)', '加权', '输入', '规则'],
            'data_evidence': '数据证据',
            'analyzed_url': '分析网址',
            'scan_time': '扫描时间',
            'platform_detected': '平台检测',
            'confidence': '置信度',
            'price_range': '价格区间',
            'free_shipping': '免运费门槛',
            'return_period': '退货期限',
            'days': '天',
            'pages_analyzed': '分析页面数',
            'change_tracking': '变化追踪',
            'first_scan': '首次扫描，无历史数据对比',
            'hot_products': '热门产品示例',
            'comparison_table': '综合对比表',
            'website': '网站',
            'brand_positioning': '品牌定位',
            'main_categories': '主打品类',
            'promotions': '促销手段',
            'shipping_free': '运费/免邮',
            'returns': '退换货',
            'trust_signals': '信任要素',
            'key_takeaway': '关键可复制点',
            'generated_by': '报告由电商竞争情报工具自动生成',
            'no_info': '无明确信息',
            'none': '无',
            'free_shipping_all': '全场免运费',
            'has_shipping': '有运费',
            'free_returns': '免费',
            'warning_pages': '个页面有问题',
        },
        'en': {
            'title': 'E-commerce Competitive Intelligence Report',
            'generated_time': 'Generated',
            'sites_analyzed': 'Sites Analyzed',
            'url': 'URL',
            'platform': 'Platform',
            'pressure_score': 'Competitive pressure score (rule-based)',
            'pressure_note': ' (weighted sum {total}, rounded and clamped to 1-10). Fixed weights and rules; '
                             'no model, no training data.',
            'pressure_header': ['Factor', 'Weight', 'Score (0-10)', 'Weighted', 'Inputs', 'Rule'],
            'data_evidence': 'Data Evidence',
            'analyzed_url': 'Analyzed URL',
            'scan_time': 'Scan Time',
            'platform_detected': 'Platform Detected',
            'confidence': 'Confidence',
            'price_range': 'Price Range',
            'free_shipping': 'Free Shipping Threshold',
            'return_period': 'Return Period',
            'days': 'days',
            'pages_analyzed': 'Pages Analyzed',
            'change_tracking': 'Change Tracking',
            'first_scan': 'First scan - no historical data',
            'hot_products': 'Featured Products',
            'comparison_table': 'Comparison Table',
            'website': 'Website',
            'brand_positioning': 'Brand Positioning',
            'main_categories': 'Main Categories',
            'promotions': 'Promotions',
            'shipping_free': 'Shipping',
            'returns': 'Returns',
            'trust_signals': 'Trust Signals',
            'key_takeaway': 'Key Takeaway',
            'generated_by': 'Report generated by E-commerce Intelligence Tool',
            'no_info': 'No information',
            'none': 'None',
            'free_shipping_all': 'Free shipping',
            'has_shipping': 'Paid shipping',
            'free_returns': 'Free',
            'warning_pages': 'pages with issues',
        }
    }
    
    def __init__(self, output_dir: str = "output", language: str = "zh"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.language = language if language in self.TRANSLATIONS else 'zh'
        self.t = self.TRANSLATIONS[self.language]
    
    def write_full_report(
        self,
        intel_list: List[SiteIntelligence],
        changes: Dict[str, Optional[ChangeReport]],
        report_name: str = "report"
    ) -> tuple:
        """
        Write complete Markdown and CSV reports.
        
        Args:
            intel_list: List of SiteIntelligence objects
            changes: Dict mapping domain to ChangeReport (or None)
            report_name: Base name for output files
            
        Returns:
            Tuple of (markdown_path, csv_path)
        """
        md_path = self.output_dir / f"{report_name}.md"
        csv_path = self.output_dir / f"{report_name}.csv"
        
        # Generate Markdown
        md_content = self._generate_markdown(intel_list, changes)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"Wrote Markdown report to {md_path}")
        
        # Generate CSV
        self._write_csv(intel_list, csv_path)
        logger.info(f"Wrote CSV report to {csv_path}")
        
        return str(md_path), str(csv_path)
    
    def _generate_markdown(
        self,
        intel_list: List[SiteIntelligence],
        changes: Dict[str, Optional[ChangeReport]]
    ) -> str:
        """Generate complete Markdown report."""
        lines = []
        t = self.t
        
        analyzed = [i for i in intel_list if i.is_analyzed]
        not_seen = [i for i in intel_list if not i.is_analyzed]
        ns = NOT_SEEN_TEXT[self.language]

        # Header
        lines.append(f"# {t['title']}")
        lines.append("")
        lines.append(f"**{t['generated_time']}**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"**{t['sites_analyzed']}**: {len(analyzed)}")
        for intel in not_seen:
            lines.append(f"**{ns['short'][intel.status].capitalize()}**: {intel.url}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Per-site sections
        for intel in intel_list:
            if not intel.is_analyzed:
                lines.extend([f"## 🏪 {intel.domain}", "", f"**{t['url']}**: [{intel.url}]({intel.url})", ""]
                             + [line + "  " for line in not_seen_lines(intel, self.language)])
            else:
                lines.extend(self._generate_site_section(intel, changes.get(intel.domain)))
            lines.append("")
            lines.append("---")
            lines.append("")
        
        # Consolidated comparison table
        lines.append(f"## 📊 {t['comparison_table']}")
        lines.append("")
        if analyzed:
            lines.extend(self._generate_comparison_table(analyzed))
        else:
            lines.append(ns['none_compared'])
        if not_seen:
            lines.append("")
            lines.append(f"{ns['not_compared']}: " + ", ".join(
                f"{i.url} ({ns['short'][i.status]})" for i in not_seen))
        lines.append("")
        
        # Footer
        lines.append("---")
        lines.append("")
        lines.append(f"*{t['generated_by']}*")
        
        return '\n'.join(lines)
    
    def _generate_site_section(
        self,
        intel: SiteIntelligence,
        change_report: Optional[ChangeReport]
    ) -> List[str]:
        """Generate Markdown section for a single site."""
        lines = []
        t = self.t
        is_en = self.language == 'en'
        
        # Header
        lines.append(f"## 🏪 {intel.domain}")
        lines.append("")
        lines.append(f"**{t['url']}**: [{intel.url}]({intel.url})")
        lines.append(f"**{t['platform']}**: {intel.platform.value}")
        lines.append("")
        
        # Rule-based insights
        insights = generate_insights(intel, language=self.language)

        # Key insights
        key_insights_title = "Key Insights" if is_en else "关键洞察"
        lines.append(f"### 🔍 {key_insights_title}")
        lines.append("")
        for insight in insights['key_insights']:
            lines.append(f"- {insight}")
        lines.append("")

        # Recommendations
        rec_title = "Actionable Recommendations" if is_en else "可复制的动作建议"
        lines.append(f"### 💡 {rec_title}")
        lines.append("")
        for i, rec in enumerate(insights['recommendations'], 1):
            lines.append(f"{i}. {rec}")
        lines.append("")

        # The optional LLM step's section, next to the rule-based text it does not replace
        lines.extend(ai_section_lines(intel.ai_analysis, self.language))

        lines.extend(self._generate_pressure_section(intel))

        # Evidence (always show)
        insights = generate_insights(intel, language=self.language)
        lines.append(f"### 📋 {t['data_evidence']}")
        lines.append("")
        for evidence in insights['evidence']:
            lines.append(f"- {evidence}")
        lines.append("")
        
        # Policy Evidence Ladder (legal compliance)
        lines.extend(self._generate_policy_evidence_section(intel))
        
        # Change tracking
        lines.append(f"### 📈 {t['change_tracking']}")
        lines.append("")
        if change_report:
            change_lines = format_changes(change_report, self.language)
            for change in change_lines:
                lines.append(f"- {change}")
        else:
            lines.append(f"- {t['first_scan']}")
        lines.append("")
        
        # Products section (if available)
        if intel.hero_products:
            lines.append(f"### 🛒 {t['hot_products']}")
            lines.append("")
            for product in intel.hero_products[:3]:
                price_str = f"${product.price.current_price:.2f}" if product.price and product.price.current_price else ("Price N/A" if is_en else "价格未知")
                lines.append(f"- **{product.title}** - {price_str}")
            lines.append("")
        
        return lines
    
    def _generate_pressure_section(self, intel: SiteIntelligence) -> List[str]:
        """Rule-based competitive pressure score with every weight, factor score and input."""
        t = self.t
        result = score_pressure(intel)
        lines = [f"### 📐 {t['pressure_score']}", "",
                 f"**{result['score']}/10**" + t['pressure_note'].format(total=f"{result['weighted_sum']:.2f}"), "",
                 "| " + " | ".join(t['pressure_header']) + " |",
                 "|" + "---|" * len(t['pressure_header'])]
        sep = '; ' if self.language == 'en' else '；'
        for f in result['factors']:
            inputs = sep.join(format_input(k, v, self.language) for k, v in f['inputs'].items())
            lines.append(f"| {FACTOR_NAMES[self.language][f['key']]} | {f['weight']:.2f} | {f['score']} | "
                         f"{f['weight'] * f['score']:.2f} | {inputs} | {RULES[self.language][f['key']]} |")
        lines.append("")
        return lines

    def _generate_policy_evidence_section(self, intel: SiteIntelligence) -> List[str]:
        """Generate the Policy Evidence Ladder section for legal compliance."""
        lines = []
        is_en = self.language == 'en'
        
        # Section header
        if is_en:
            lines.append("### 📜 Policy Data Sources")
            lines.append("")
            lines.append("| Policy | Status | Source | Verification |")
            lines.append("|--------|--------|--------|--------------|")
        else:
            lines.append("### 📜 政策数据来源")
            lines.append("")
            lines.append("| 政策类型 | 状态 | 数据来源 | 验证状态 |")
            lines.append("|---------|------|---------|---------|")
        
        # Shipping policy evidence
        ship_status, ship_source, ship_verify = self._get_policy_evidence_row(
            intel.shipping_policy, 'shipping', is_en
        )
        if is_en:
            lines.append(f"| Shipping | {ship_status} | {ship_source} | {ship_verify} |")
        else:
            lines.append(f"| 运费政策 | {ship_status} | {ship_source} | {ship_verify} |")
        
        # Return policy evidence
        ret_status, ret_source, ret_verify = self._get_policy_evidence_row(
            intel.return_policy, 'returns', is_en
        )
        if is_en:
            lines.append(f"| Returns | {ret_status} | {ret_source} | {ret_verify} |")
        else:
            lines.append(f"| 退货政策 | {ret_status} | {ret_source} | {ret_verify} |")
        
        lines.append("")
        
        # Add note if any policies need verification
        needs_verify = False
        if intel.shipping_policy and getattr(intel.shipping_policy, 'requires_manual_verification', False):
            needs_verify = True
        if intel.return_policy and getattr(intel.return_policy, 'requires_manual_verification', False):
            needs_verify = True
        
        if needs_verify:
            if is_en:
                lines.append("*⚠️ Some policy data requires manual verification. Visit the official website to confirm.*")
            else:
                lines.append("*⚠️ 部分政策数据需要手动验证，请访问官网确认。*")
            lines.append("")
        
        return lines
    
    def _get_policy_evidence_row(self, policy, policy_type: str, is_en: bool) -> Tuple[str, str, str]:
        """Get evidence row data for a policy."""
        if policy is None:
            if is_en:
                return "❓", "Not found", "N/A"
            else:
                return "❓", "未找到", "无"
        
        # Get evidence level
        evidence_level = getattr(policy, 'evidence_level', 0)
        evidence_source = getattr(policy, 'evidence_source', '')
        evidence_url = getattr(policy, 'evidence_url', '')
        requires_verify = getattr(policy, 'requires_manual_verification', False)
        
        # Determine status emoji
        if evidence_level == 1:
            status = "✅"
        elif evidence_level == 2:
            status = "✅"
        elif evidence_level == 3:
            status = "⚠️"
        elif evidence_level == 4:
            status = "❌"
        else:
            # Fallback for old data without evidence tracking
            has_data = False
            if policy_type == 'shipping':
                has_data = (getattr(policy, 'free_shipping_threshold', None) is not None or
                           getattr(policy, 'estimated_days_min', None) is not None)
            else:
                has_data = (getattr(policy, 'return_days', None) is not None)
            status = "✅" if has_data else "❓"
        
        # Determine source text
        if is_en:
            source_texts = {
                'official_policy': 'Official policy page',
                'policy_page': 'Official policy page',
                'faq_help_center': 'FAQ/Help center',
                'faq': 'FAQ/Help center',
                'product_cart': 'Product/cart page',
                'product_page': 'Product/cart page',
                'blocked': 'Blocked by robots.txt',
                '': 'Homepage/general'
            }
            verify_texts = {True: 'Manual check needed', False: 'Verified'}
        else:
            source_texts = {
                'official_policy': '官方政策页面',
                'policy_page': '官方政策页面',
                'faq_help_center': 'FAQ/帮助中心',
                'faq': 'FAQ/帮助中心',
                'product_cart': '产品/购物车页面',
                'product_page': '产品/购物车页面',
                'blocked': '被robots.txt阻止',
                '': '首页/通用'
            }
            verify_texts = {True: '需手动验证', False: '已验证'}
        
        source = source_texts.get(evidence_source, source_texts[''])
        verify = verify_texts[requires_verify]
        
        return status, source, verify
    
    def _generate_comparison_table(
        self,
        intel_list: List[SiteIntelligence]
    ) -> List[str]:
        """Generate consolidated comparison Markdown table."""
        lines = []
        t = self.t
        is_en = self.language == 'en'
        
        # Table header based on language
        if is_en:
            headers = [
                "Website", "Platform", "Brand Positioning", "Categories", "Price Range",
                "Promotions", "Shipping", "Returns", "Trust Signals", "Key Takeaway"
            ]
        else:
            headers = [
                "网站", "平台", "品牌定位", "主打品类", "价格区间",
                "促销手段", "运费/免邮", "退换货", "信任要素", "关键可复制点"
            ]
        
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        
        # Table rows
        for intel in intel_list:
            row = self._generate_table_row(intel)
            lines.append("| " + " | ".join(row) + " |")
        
        return lines
    
    def _generate_table_row(self, intel: SiteIntelligence) -> List[str]:
        """Generate a single table row for a site."""
        t = self.t
        is_en = self.language == 'en'
        no_info = "N/A" if is_en else "无明确信息"
        none_str = "None" if is_en else "无"
        
        # Website
        website = intel.domain
        
        # Platform
        platform = intel.platform.value.split('/')[0]  # Just first word
        
        # Brand positioning
        if intel.brand_positioning:
            text = intel.brand_positioning
            positioning = f"“{text[:80]}”" + ("…" if len(text) > 80 else "")
        else:
            positioning = no_info
        
        # Categories
        sep = ', ' if is_en else '、'
        categories = sep.join(intel.categories[:2]) if intel.categories else no_info
        if len(categories) > 25:
            categories = categories[:25] + "..."
        
        # Price range
        if intel.price_min and intel.price_max:
            price_range = f"${intel.price_min:.0f}-${intel.price_max:.0f}"
        else:
            price_range = no_info
        
        # Promotions
        promos = []
        if is_en:
            if intel.has_popup:
                promos.append("Popup")
            if intel.has_email_capture:
                promos.append("Email")
            if intel.has_loyalty_program:
                promos.append("Loyalty")
            if intel.announcement_bar_text:
                promos.append("Banner")
        else:
            if intel.has_popup:
                promos.append("弹窗")
            if intel.has_email_capture:
                promos.append("邮件订阅")
            if intel.has_loyalty_program:
                promos.append("会员")
            if intel.announcement_bar_text:
                promos.append("公告栏")
        # "None" only when every field it rests on is known; a field not determined (None) is N/A
        known_promos = all(x is not None for x in (intel.has_popup, intel.has_email_capture,
                                                    intel.has_loyalty_program, intel.announcement_bar_text))
        promotions = sep.join(promos[:3]) if promos else none_str if known_promos else no_info
        
        # Shipping
        if intel.shipping_policy:
            ship = intel.shipping_policy
            if ship.free_shipping_threshold is not None:
                if ship.free_shipping_threshold == 0:
                    shipping = "Free shipping" if is_en else "全场免运费"
                else:
                    shipping = f"Free over ${ship.free_shipping_threshold:.0f}" if is_en else f"满${ship.free_shipping_threshold:.0f}免运费"
            else:
                shipping = "No free-shipping offer found" if is_en else "未发现免运费政策"
        else:
            shipping = no_info
        
        # Returns
        if intel.return_policy and intel.return_policy.return_days:
            ret = intel.return_policy
            days_str = "days" if is_en else "天"
            free_str = "(Free)" if is_en else "(免费)"
            returns = f"{ret.return_days} {days_str}"
            if ret.free_returns:
                returns += free_str
        else:
            returns = no_info
        
        # Trust signals
        trust = []
        if is_en:
            if intel.review_platform:
                trust.append("Reviews")
            bnpl = [m for m in intel.payment_methods if m in ['Klarna', 'Afterpay', 'Affirm']]
            if bnpl:
                trust.append("BNPL")
            if any(s.signal_type == 'badge' for s in intel.trust_signals):
                trust.append("Badges")
        else:
            if intel.review_platform:
                trust.append("评论")
            bnpl = [m for m in intel.payment_methods if m in ['Klarna', 'Afterpay', 'Affirm']]
            if bnpl:
                trust.append("分期付款")
            if any(s.signal_type == 'badge' for s in intel.trust_signals):
                trust.append("信任徽章")
        trust_str = sep.join(trust[:2]) if trust else none_str if intel.review_platform is not None else no_info
        
        # Key replicable point
        if is_en:
            key_point = none_str
            if intel.has_subscriptions:
                key_point = "Subscription"
            elif intel.has_bundles:
                key_point = "Bundles"
            elif intel.shipping_policy and intel.shipping_policy.free_shipping_threshold == 0:
                key_point = "Free Shipping"
            elif intel.has_loyalty_program:
                key_point = "Loyalty"
            elif intel.review_platform:
                key_point = "Reviews"
        else:
            key_point = none_str
            if intel.has_subscriptions:
                key_point = "订阅模式"
            elif intel.has_bundles:
                key_point = "捆绑销售"
            elif intel.shipping_policy and intel.shipping_policy.free_shipping_threshold == 0:
                key_point = "免运费策略"
            elif intel.has_loyalty_program:
                key_point = "会员体系"
            elif intel.review_platform:
                key_point = "评论系统"
        
        if key_point == none_str and any(x is None for x in (intel.has_subscriptions, intel.has_bundles,
                                                             intel.has_loyalty_program, intel.review_platform,
                                                             intel.shipping_policy)):
            key_point = no_info

        return [
            website, platform, positioning, categories, price_range,
            promotions, shipping, returns, trust_str, key_point
        ]
    
    def _write_csv(
        self,
        intel_list: List[SiteIntelligence],
        csv_path: Path
    ) -> None:
        """Write CSV export of the comparison table."""
        headers = [
            "domain", "url", "status", "fetch_attempts", "platform", "brand_positioning",
            "categories", "price_min", "price_max", "price_median",
            "currency", "has_discounts", "announcement_bar",
            "has_popup", "has_email_capture", "has_loyalty",
            "has_referral", "free_shipping_threshold",
            "return_days", "free_returns", "review_platform",
            "review_count", "payment_methods", "pixels_detected",
            "scan_timestamp"
        ]
        
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            for intel in intel_list:
                row = {
                    "domain": intel.domain,
                    "url": intel.url,
                    "status": intel.status,
                    "fetch_attempts": "; ".join(intel.fetch_attempts),
                    "platform": intel.platform.value if intel.platform else None,
                    "brand_positioning": intel.brand_positioning or "",
                    "categories": "; ".join(intel.categories),
                    "price_min": intel.price_min,
                    "price_max": intel.price_max,
                    "price_median": intel.price_median,
                    "currency": intel.currency,
                    "has_discounts": intel.has_discounts,
                    "announcement_bar": intel.announcement_bar_text[:100] if intel.announcement_bar_text else "",
                    "has_popup": intel.has_popup,
                    "has_email_capture": intel.has_email_capture,
                    "has_loyalty": intel.has_loyalty_program,
                    "has_referral": intel.has_referral_program,
                    "free_shipping_threshold": intel.shipping_policy.free_shipping_threshold if intel.shipping_policy else None,
                    "return_days": intel.return_policy.return_days if intel.return_policy else None,
                    "free_returns": intel.return_policy.free_returns if intel.return_policy else None,
                    "review_platform": intel.review_platform,
                    "review_count": intel.total_reviews,
                    "payment_methods": "; ".join(intel.payment_methods),
                    "pixels_detected": "; ".join(p.name for p in intel.pixels if p.detected),
                    "scan_timestamp": intel.scan_timestamp.isoformat()
                }
                writer.writerow(row)


def write_markdown_report(
    intel_list: List[SiteIntelligence],
    changes: Dict[str, Optional[ChangeReport]],
    output_dir: str = "output"
) -> str:
    """
    Convenience function to write Markdown report.
    
    Args:
        intel_list: List of SiteIntelligence objects
        changes: Dict of domain to ChangeReport
        output_dir: Output directory
        
    Returns:
        Path to generated report
    """
    writer = ReportWriter(output_dir)
    md_path, _ = writer.write_full_report(intel_list, changes)
    return md_path


def write_csv(
    intel_list: List[SiteIntelligence],
    output_dir: str = "output"
) -> str:
    """
    Convenience function to write CSV report.
    
    Args:
        intel_list: List of SiteIntelligence objects
        output_dir: Output directory
        
    Returns:
        Path to generated CSV
    """
    writer = ReportWriter(output_dir)
    _, csv_path = writer.write_full_report(intel_list, {})
    return csv_path
