"""
business_report.py - Business summary of a scan, in English or Chinese.

Sections:
1. Executive Summary (key findings)
2. Market Overview            (two or more analysed sites only)
3. Site Profiles
4. Comparative Analysis       (two or more analysed sites only)
5. Recommendations
6. Appendix: methodology (what actually ran) and evidence levels

Only analysed sites (status 'ok') are counted, averaged or compared. Every
comparative sentence depends on how many there are: with one site the report
describes that site and makes no market or competitor claims. The methodology
states what ran: pages fetched, the fetch branch that served them, whether
robots.txt was respected, whether the LLM step ran and with which model.
"""

import logging
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .models import SiteIntelligence, ChangeReport
from .product_sample import describe as describe_sample, price_note
from .report_writer import BRANCH_NAMES, NOT_SEEN_TEXT, format_attempts, not_seen_lines

logger = logging.getLogger(__name__)

T = {
    'en': {
        'title': "# Competitive Intelligence Report",
        'date': "**Report Date:** {date}",
        'date_fmt': "%B %d, %Y",
        'sites': "**Sites Analyzed:** {n}",
        'not_seen_header': "**{status}:** {url} - not analyzed",
        'summary': "## Executive Summary",
        'findings': "### Key Findings",
        'no_sites': "No site could be analyzed, so there are no findings.",
        # one site
        'platform_one': "**Platform:** {site} runs on {platform}.",
        'pricing_one': "**Pricing:** {count} priced products from ${lo:.0f} to ${hi:.0f}, median ${median:.2f}.",
        'pricing_note': "**Pricing:** {note}.",
        'discounts_one': "**Discounts:** marked down: {k} of its {m} priced products.",
        'no_discounts_one': "**Discounts:** no marked-down product found.",
        'ship_free_all': "free shipping on every order",
        'ship_over': "free shipping over ${t:.0f}",
        'ship_none': "no free-shipping offer found",
        'shipping_one': "**Shipping:** {text}.",
        'returns_one': "**Returns:** {days}-day return window{free}.",
        'returns_none_one': "**Returns:** no return window found.",
        'free_suffix': ", returns are free",
        'loyalty_one': "**Loyalty:** {text}.",
        'loyalty_yes': "runs a loyalty program", 'loyalty_no': "no loyalty program found",
        # several sites
        'platforms_many': "**Platforms:** {dist}.",
        'pricing_many': "**Pricing:** across the {n} sites prices run from ${lo:.0f} to ${hi:.0f}; "
                        "the average of their median prices is ${avg:.2f}.",
        'shipping_many': "**Shipping:** {k} of {n} sites offer free shipping ({detail}).",
        'returns_many': "**Returns:** return windows found on {k} of {n} sites: {detail}.",
        'loyalty_many': "**Loyalty:** {k} of {n} sites run a loyalty program.",
        'changes_many': "**Changes since the last scan:** {k} of {n} sites changed.",
        'changes_one': "**Changes since the last scan:** yes, see the profile below.",
        # market overview
        'market': "## Market Overview",
        'platform_dist': "**Platform Distribution:**",
        'price_tiers': "### Pricing Landscape",
        'tiers': ("Budget (median < $50)", "Mid-range ($50-150)", "Premium ($150+)"),
        # profiles
        'profiles': "## Site Profiles",
        'website': "**Website:** [{url}]({url}) | **Platform:** {platform}",
        'history': "**Scan History:** {count} scans (First: {first}, Latest: {latest})",
        'metrics': "**Key Metrics:**",
        'm_price': "- **Price Range:** ${lo:.0f} - ${hi:.0f} (Median: ${median:.2f})",
        'm_price_note': "- **Price Range:** {note}",
        'm_shipping': "- **Shipping:** {text}",
        'm_returns': "- **Returns:** {days} days{free}",
        'free_short': " (free)",
        'm_marketing': "- **Marketing:** {tactics}",
        'tactics': {'popup': "Popup", 'email': "Email Capture", 'loyalty': "Loyalty Program",
                    'subscriptions': "Subscriptions"},
        'list_sep': ", ",
        'ai_insights': "**Key Insights (AI, Ollama model {model}):**",
        'changes': "**Changes Since Last Scan:**",
        # comparison
        'comparison': "## Comparative Analysis",
        'matrix': "### Feature Comparison Matrix",
        'matrix_header': "| Site | Price Range | Free Shipping | Returns | Loyalty | Subscriptions |",
        'all': "All", 'na': "N/A", 'days_short': "d",
        'notes': "### What the data shows",
        'same_platform': "All {n} sites run on {platform}.",
        'overlap': "The {n} sites' price ranges overlap between ${lo:.0f} and ${hi:.0f}.",
        'no_overlap': "The {n} sites' price ranges do not overlap.",
        'free_all_sites': "All {n} sites offer free shipping; the lowest threshold is ${t:.0f}.",
        'free_no_sites': "None of the {n} sites offers free shipping.",
        'subs_count': "{k} of {n} sites sell subscriptions.",
        # recommendations
        'recs': "## Recommendations",
        'recs_intro_one': "What to compare against this site:",
        'recs_intro_many': "What to compare against these {n} sites:",
        'r_price_one': "**Pricing:** compare your prices with this site's range (${lo:.0f}-${hi:.0f}, "
                       "median ${median:.2f}).",
        'r_price_many': "**Pricing:** compare your prices with the sites' medians ({detail}).",
        'r_ship_one': "**Shipping:** this site offers {text}; check your own threshold against your typical "
                      "order value.",
        'r_ship_many': "**Shipping:** free-shipping offers across the sites: {detail}; place yours against them.",
        'r_returns_one': "**Returns:** this site allows {days}-day returns{free}; compare with your policy.",
        'r_returns_many': "**Returns:** return windows across the sites: {detail}.",
        'r_loyalty_one': "**Retention:** this site runs a loyalty program; worth a look if repeat purchases "
                         "matter in your category.",
        'r_loyalty_many': "**Retention:** {k} of {n} sites run a loyalty program.",
        'r_email_one': "**Email capture:** this site collects emails{popup}.",
        'r_popup': " with a popup", 'r_no_popup': " without a popup",
        'r_none': "No recommendation: the analysed sites gave too little data.",
        # appendix
        'appendix': "## Appendix",
        'methodology': "### Methodology",
        'm_collection': "- **Data collection:** {pages} pages fetched from {n} sites; {robots}",
        'm_collection_one': "- **Data collection:** {pages} pages fetched; {robots}",
        'robots_yes': "robots.txt was respected.",
        'robots_no': "robots.txt was ignored (`--ignore-robots`).",
        'robots_unknown': "robots.txt handling not recorded for this run.",
        'm_site': "  - {site}: {pages} pages, served by {branches}",
        'm_sample': "  - {site}: product sample: {text}",
        'responses': "{branch} ({n} responses)",
        'm_site_not_seen': "  - {site}: {status} ({attempts})",
        'm_js': "- **JavaScript rendering:** {text}",
        'js_yes': "used (`--render-js`, a browser fetched the pages)",
        'js_no': "not used",
        'm_llm_none': "- **LLM step:** The LLM step was not run (`--ai` not given); all text is rule-based.",
        'm_llm_unavailable': "- **LLM step:** requested (`--ai`, model {model}) but Ollama was not available; "
                             "all text is rule-based.",
        'm_llm_one': "- **LLM step:** the key insights for this site were generated by a local LLM "
                     "(Ollama, {models}); everything else is rule-based.",
        'm_llm_many': "- **LLM step:** key insights for {k} of {n} sites were generated by a local LLM "
                      "(Ollama, {models}); everything else is rule-based.",
        'm_pressure': "- **Competitive pressure score:** a fixed rule-based rubric; weights and inputs are "
                      "printed in `report.md`.",
        'evidence': "### Data Quality Notes",
        'evidence_header': "| Evidence Level | Source Type | Confidence |",
        'evidence_rows': ["| Level 1 | Official policy pages | High |",
                          "| Level 2 | FAQ/Help center | High |",
                          "| Level 3 | Product/cart inference | Medium |"],
        'footer': "*Report generated by E-commerce Competitive Intelligence Tool*",
    },
    'zh': {
        'title': "# 竞争情报分析报告",
        'date': "**报告日期:** {date}",
        'date_fmt': "%Y年%m月%d日",
        'sites': "**分析站点数:** {n}",
        'not_seen_header': "**{status}:** {url}（未分析）",
        'summary': "## 执行摘要",
        'findings': "### 关键发现",
        'no_sites': "没有可分析的站点，因此没有任何发现。",
        'platform_one': "**平台:** {site} 使用 {platform}。",
        'pricing_one': "**定价:** 共{count}个有价格的商品，价格${lo:.0f}至${hi:.0f}，中位数${median:.2f}。",
        'pricing_note': "**定价:** {note}。",
        'discounts_one': "**折扣:** {m}个有价格的商品中有{k}个打折。",
        'no_discounts_one': "**折扣:** 未发现打折商品。",
        'ship_free_all': "全场免运费",
        'ship_over': "满${t:.0f}免运费",
        'ship_none': "未发现免运费政策",
        'shipping_one': "**运费:** {text}。",
        'returns_one': "**退货:** {days}天退货期{free}。",
        'returns_none_one': "**退货:** 未发现退货期限。",
        'free_suffix': "，免费退货",
        'loyalty_one': "**会员:** {text}。",
        'loyalty_yes': "有会员积分计划", 'loyalty_no': "未发现会员计划",
        'platforms_many': "**平台:** {dist}。",
        'pricing_many': "**定价:** {n}个站点的价格从${lo:.0f}到${hi:.0f}；各站点中位价的平均值为${avg:.2f}。",
        'shipping_many': "**运费:** {n}个站点中有{k}个提供免运费（{detail}）。",
        'returns_many': "**退货:** {n}个站点中有{k}个找到退货期限：{detail}。",
        'loyalty_many': "**会员:** {n}个站点中有{k}个有会员计划。",
        'changes_many': "**变化监测:** {n}个站点中有{k}个自上次扫描以来有变化。",
        'changes_one': "**变化监测:** 自上次扫描以来有变化，见下方档案。",
        'market': "## 市场概览",
        'platform_dist': "**平台分布:**",
        'price_tiers': "### 价格分布",
        'tiers': ("低价（中位价 < $50）", "中端 ($50-150)", "高端 ($150+)"),
        'profiles': "## 站点档案",
        'website': "**网站:** [{url}]({url}) | **平台:** {platform}",
        'history': "**扫描历史:** 共{count}次 (首次: {first}, 最近: {latest})",
        'metrics': "**关键指标:**",
        'm_price': "- **价格区间:** ${lo:.0f} - ${hi:.0f} (中位数: ${median:.2f})",
        'm_price_note': "- **价格区间:** {note}",
        'm_shipping': "- **运费:** {text}",
        'm_returns': "- **退货:** {days}天{free}",
        'free_short': "（免费）",
        'm_marketing': "- **营销:** {tactics}",
        'tactics': {'popup': "弹窗", 'email': "邮件订阅", 'loyalty': "会员计划", 'subscriptions': "订阅模式"},
        'list_sep': "、",
        'ai_insights': "**关键洞察（AI，Ollama 模型 {model}）:**",
        'changes': "**自上次扫描以来的变化:**",
        'comparison': "## 站点对比分析",
        'matrix': "### 功能对比矩阵",
        'matrix_header': "| 站点 | 价格区间 | 免运费 | 退货 | 会员 | 订阅 |",
        'all': "全场", 'na': "未知", 'days_short': "天",
        'notes': "### 数据显示",
        'same_platform': "{n}个站点都使用 {platform}。",
        'overlap': "{n}个站点的价格区间在${lo:.0f}到${hi:.0f}之间重叠。",
        'no_overlap': "{n}个站点的价格区间没有重叠。",
        'free_all_sites': "{n}个站点都提供免运费，最低门槛为${t:.0f}。",
        'free_no_sites': "{n}个站点都不提供免运费。",
        'subs_count': "{n}个站点中有{k}个提供订阅。",
        'recs': "## 建议",
        'recs_intro_one': "可与该站点对照的方面：",
        'recs_intro_many': "可与这{n}个站点对照的方面：",
        'r_price_one': "**定价:** 将您的价格与该站点的价格区间（${lo:.0f}-${hi:.0f}，中位数${median:.2f}）对比。",
        'r_price_many': "**定价:** 将您的价格与各站点的中位价（{detail}）对比。",
        'r_ship_one': "**运费:** 该站点{text}；请结合您的客单价检查自己的免运费门槛。",
        'r_ship_many': "**运费:** 各站点的免运费政策：{detail}；据此设定您的门槛。",
        'r_returns_one': "**退货:** 该站点提供{days}天退货{free}；与您的政策对比。",
        'r_returns_many': "**退货:** 各站点的退货期限：{detail}。",
        'r_loyalty_one': "**留存:** 该站点有会员积分计划；如果复购对您的品类重要，值得参考。",
        'r_loyalty_many': "**留存:** {n}个站点中有{k}个有会员计划。",
        'r_email_one': "**邮件收集:** 该站点{popup}收集邮件。",
        'r_popup': "通过弹窗", 'r_no_popup': "不使用弹窗",
        'r_none': "无建议：已分析站点提供的数据太少。",
        'appendix': "## 附录",
        'methodology': "### 方法论",
        'm_collection': "- **数据收集:** 从{n}个站点抓取了{pages}个页面；{robots}",
        'm_collection_one': "- **数据收集:** 抓取了{pages}个页面；{robots}",
        'robots_yes': "遵守了 robots.txt。",
        'robots_no': "忽略了 robots.txt（`--ignore-robots`）。",
        'robots_unknown': "本次运行未记录 robots.txt 的处理方式。",
        'm_site': "  - {site}: {pages}个页面，抓取方式 {branches}",
        'm_sample': "  - {site}: 产品样本：{text}",
        'responses': "{branch}（{n}次响应）",
        'm_site_not_seen': "  - {site}: {status}（{attempts}）",
        'm_js': "- **JavaScript 渲染:** {text}",
        'js_yes': "已使用（`--render-js`，由浏览器抓取页面）",
        'js_no': "未使用",
        'm_llm_none': "- **LLM 步骤:** 未运行（未指定 `--ai`）；所有文字均基于规则。",
        'm_llm_unavailable': "- **LLM 步骤:** 已请求（`--ai`，模型 {model}），但 Ollama 不可用；所有文字均基于规则。",
        'm_llm_one': "- **LLM 步骤:** 该站点的关键洞察由本地 LLM 生成（Ollama，{models}）；其余内容均基于规则。",
        'm_llm_many': "- **LLM 步骤:** {n}个站点中有{k}个的关键洞察由本地 LLM 生成（Ollama，{models}）；"
                      "其余内容均基于规则。",
        'm_pressure': "- **竞争压力评分:** 固定的规则评分，权重和输入见 `report.md`。",
        'evidence': "### 数据质量说明",
        'evidence_header': "| 证据级别 | 来源类型 | 置信度 |",
        'evidence_rows': ["| 级别1 | 官方政策页面 | 高 |",
                          "| 级别2 | FAQ/帮助中心 | 高 |",
                          "| 级别3 | 产品/购物车推断 | 中 |"],
        'footer': "*报告由电商竞争情报工具生成*",
    },
}


def site_label(intel: SiteIntelligence) -> str:
    """Host and port as typed in sites.txt (two local stores differ only by port)."""
    return urlparse(intel.url).netloc or intel.domain


def _threshold(intel: SiteIntelligence) -> Optional[float]:
    ship = intel.shipping_policy
    return getattr(ship, 'free_shipping_threshold', None) if ship else None


def _return_days(intel: SiteIntelligence) -> Optional[int]:
    return intel.return_policy.return_days if intel.return_policy else None


class BusinessReportGenerator:
    """Business summary of a scan; see the module docstring for the rules it follows."""

    def __init__(self, output_dir: str = "output", language: str = "en"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.language = language if language in T else 'en'
        self.is_en = self.language == 'en'
        self.t = T[self.language]

    def generate_report(
        self,
        intel_list: List[SiteIntelligence],
        changes: Dict[str, Optional[ChangeReport]],
        scan_history: Dict[str, List[Dict]] = None,
        report_name: str = "business_report",
        run_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Write <report_name>.md and return its path.

        run_info (from main): ignore_robots, render_js, ai_requested, ai_available, ai_model.
        Missing keys are reported as "not recorded" rather than guessed.
        """
        run_info = run_info or {}
        analyzed = [i for i in intel_list if i.is_analyzed]
        not_seen = [i for i in intel_list if not i.is_analyzed]

        lines = self._header(analyzed, not_seen)
        lines += self._summary(analyzed, changes)
        if len(analyzed) >= 2:
            lines += self._market_overview(analyzed)
        lines += self._profiles(analyzed, not_seen, changes, scan_history or {})
        if len(analyzed) >= 2:
            lines += self._comparison(analyzed)
        if analyzed:
            lines += self._recommendations(analyzed)
        lines += self._appendix(analyzed, not_seen, run_info)

        report_path = self.output_dir / f"{report_name}.md"
        report_path.write_text('\n'.join(lines), encoding='utf-8')
        logger.info(f"Generated business report: {report_path}")
        return str(report_path)

    # --- sections ------------------------------------------------------------------------------

    def _header(self, analyzed, not_seen) -> List[str]:
        t = self.t
        ns = NOT_SEEN_TEXT[self.language]
        lines = [t['title'], "", t['date'].format(date=datetime.now().strftime(t['date_fmt'])),
                 t['sites'].format(n=len(analyzed))]
        for intel in not_seen:
            lines.append(t['not_seen_header'].format(status=ns['short'][intel.status].capitalize(), url=intel.url))
        return lines + ["", "---", ""]

    def _summary(self, analyzed, changes) -> List[str]:
        t = self.t
        lines = [t['summary'], ""]
        if not analyzed:
            return lines + [t['no_sites'], ""]
        lines += [t['findings'], ""]
        findings = self._findings_one(analyzed[0]) if len(analyzed) == 1 else self._findings_many(analyzed)
        changed = [i for i in analyzed if (cr := changes.get(i.domain)) and cr.has_changes()]
        if changed:
            findings.append(t['changes_one'] if len(analyzed) == 1 else
                            t['changes_many'].format(k=len(changed), n=len(analyzed)))
        for finding in findings:
            lines += [finding, ""]
        return lines

    def _shipping_text(self, intel) -> str:
        threshold = _threshold(intel)
        if threshold == 0:
            return self.t['ship_free_all']
        if threshold:
            return self.t['ship_over'].format(t=threshold)
        return self.t['ship_none']

    def _findings_one(self, intel) -> List[str]:
        t = self.t
        out = [t['platform_one'].format(site=site_label(intel), platform=intel.platform.value)]
        priced = [p for p in intel.all_products if p.price and p.price.current_price]
        if intel.price_min and intel.price_max:
            out.append(t['pricing_one'].format(count=len(priced) or 1, lo=intel.price_min, hi=intel.price_max,
                                               median=intel.price_median or intel.price_min))
        elif intel.price_note:
            out.append(t['pricing_note'].format(note=price_note(intel.price_note, self.language)))
        if priced:
            on_sale = [p for p in priced if p.price.is_on_sale]
            out.append(t['discounts_one'].format(k=len(on_sale), m=len(priced)) if on_sale
                       else t['no_discounts_one'])
        out.append(t['shipping_one'].format(text=self._shipping_text(intel)))
        days = _return_days(intel)
        out.append(t['returns_one'].format(days=days, free=t['free_suffix'] if intel.return_policy.free_returns else "")
                   if days else t['returns_none_one'])
        out.append(t['loyalty_one'].format(text=t['loyalty_yes'] if intel.has_loyalty_program else t['loyalty_no']))
        return out

    def _findings_many(self, sites) -> List[str]:
        t, n, sep = self.t, len(sites), self.t['list_sep']
        out = []
        dist = Counter(i.platform.value for i in sites)
        out.append(t['platforms_many'].format(dist=sep.join(f"{p} ({c}/{n})" for p, c in dist.most_common())))
        priced = [i for i in sites if i.price_min and i.price_max]
        if priced:
            medians = [i.price_median or i.price_min for i in priced]
            out.append(t['pricing_many'].format(n=len(priced), lo=min(i.price_min for i in priced),
                                                hi=max(i.price_max for i in priced),
                                                avg=sum(medians) / len(medians)))
        free = [i for i in sites if _threshold(i) is not None]
        if free:
            detail = sep.join(f"{site_label(i)}: {self._shipping_text(i)}" for i in free)
            out.append(t['shipping_many'].format(k=len(free), n=n, detail=detail))
        with_days = [i for i in sites if _return_days(i)]
        if with_days:
            detail = sep.join(f"{site_label(i)} {_return_days(i)}{t['days_short']}" for i in with_days)
            out.append(t['returns_many'].format(k=len(with_days), n=n, detail=detail))
        out.append(t['loyalty_many'].format(k=sum(1 for i in sites if i.has_loyalty_program), n=n))
        return out

    def _market_overview(self, sites) -> List[str]:
        t, n = self.t, len(sites)
        lines = [t['market'], "", t['platform_dist'], ""]
        by_platform: Dict[str, List[str]] = {}
        for intel in sites:
            by_platform.setdefault(intel.platform.value, []).append(site_label(intel))
        for platform, labels in sorted(by_platform.items(), key=lambda x: -len(x[1])):
            lines.append(f"- **{platform}** ({len(labels)}/{n}): {', '.join(labels)}")
        lines += ["", t['price_tiers'], ""]
        tiers = {name: [] for name in t['tiers']}
        for intel in sites:
            if intel.price_median:
                idx = 0 if intel.price_median < 50 else 1 if intel.price_median < 150 else 2
                tiers[t['tiers'][idx]].append(site_label(intel))
        for name, labels in tiers.items():
            if labels:
                lines.append(f"- **{name}:** {', '.join(labels)}")
        return lines + [""]

    def _profiles(self, analyzed, not_seen, changes, scan_history) -> List[str]:
        t = self.t
        lines = [t['profiles'], ""]
        for intel in analyzed:
            lines += self._profile(intel, changes.get(intel.domain), scan_history)
        for intel in not_seen:
            lines += [f"### {site_label(intel)}", "", f"[{intel.url}]({intel.url})", ""]
            lines += [line + "  " for line in not_seen_lines(intel, self.language)]
            lines += ["", "---", ""]
        return lines

    def _profile(self, intel, change_report, scan_history) -> List[str]:
        t = self.t
        lines = [f"### {site_label(intel)}", "",
                 t['website'].format(url=intel.url, platform=intel.platform.value), ""]
        history = scan_history.get(intel.domain) or []
        if len(history) > 1:
            lines += [t['history'].format(count=len(history),
                                          first=history[-1].get('scan_timestamp', '')[:10],
                                          latest=history[0].get('scan_timestamp', '')[:10]), ""]
        lines += [t['metrics'], ""]
        if intel.price_min and intel.price_max:
            lines.append(t['m_price'].format(lo=intel.price_min, hi=intel.price_max,
                                             median=intel.price_median or intel.price_min))
        elif intel.price_note:
            lines.append(t['m_price_note'].format(note=price_note(intel.price_note, self.language)))
        lines.append(t['m_shipping'].format(text=self._shipping_text(intel)))
        if _return_days(intel):
            lines.append(t['m_returns'].format(days=_return_days(intel),
                                               free=t['free_short'] if intel.return_policy.free_returns else ""))
        tactics = [t['tactics'][key] for key, on in (('popup', intel.has_popup), ('email', intel.has_email_capture),
                                                     ('loyalty', intel.has_loyalty_program),
                                                     ('subscriptions', intel.has_subscriptions)) if on]
        if tactics:
            lines.append(t['m_marketing'].format(tactics=t['list_sep'].join(tactics)))
        lines.append("")

        if intel.ai_model and intel.ai_insights.get('key_insights'):
            lines += [t['ai_insights'].format(model=intel.ai_model), ""]
            lines += [f"- {insight}" for insight in intel.ai_insights['key_insights'][:5]] + [""]

        if change_report and change_report.has_changes():
            lines += [t['changes'], ""]
            for group in (change_report.price_changes, change_report.policy_changes, change_report.promo_changes):
                lines += [f"- {change}" for change in group[:3]]
            lines.append("")
        return lines + ["---", ""]

    def _comparison(self, sites) -> List[str]:
        t, n = self.t, len(sites)
        lines = [t['comparison'], "", t['matrix'], "", t['matrix_header'],
                 "|" + "---|" * t['matrix_header'].count(" | ") + "---|"]
        for intel in sites:
            price = f"${intel.price_min:.0f}-${intel.price_max:.0f}" if intel.price_min else t['na']
            threshold = _threshold(intel)
            free = f"✅ {t['all']}" if threshold == 0 else f"${threshold:.0f}+" if threshold else "❌"
            days = _return_days(intel)
            returns = f"{days}{t['days_short']}" + (" ✅" if intel.return_policy.free_returns else "") if days else t['na']
            lines.append(f"| {site_label(intel)} | {price} | {free} | {returns} | "
                         f"{'✅' if intel.has_loyalty_program else '❌'} | {'✅' if intel.has_subscriptions else '❌'} |")
        lines.append("")

        notes = []
        platforms = {i.platform.value for i in sites}
        if len(platforms) == 1:
            notes.append(t['same_platform'].format(n=n, platform=platforms.pop()))
        priced = [i for i in sites if i.price_min and i.price_max]
        if len(priced) >= 2:
            lo, hi = max(i.price_min for i in priced), min(i.price_max for i in priced)
            notes.append(t['overlap'].format(n=len(priced), lo=lo, hi=hi) if lo <= hi
                         else t['no_overlap'].format(n=len(priced)))
        thresholds = [_threshold(i) for i in sites]
        if all(x is not None for x in thresholds):
            notes.append(t['free_all_sites'].format(n=n, t=min(thresholds)))
        elif all(x is None for x in thresholds):
            notes.append(t['free_no_sites'].format(n=n))
        subs = sum(1 for i in sites if i.has_subscriptions)
        if subs:
            notes.append(t['subs_count'].format(k=subs, n=n))
        if notes:
            lines += [t['notes'], ""] + [f"- {note}" for note in notes] + [""]
        return lines

    def _recommendations(self, sites) -> List[str]:
        t, n, sep = self.t, len(sites), self.t['list_sep']
        recs = []
        if n == 1:
            intel = sites[0]
            if intel.price_min and intel.price_max:
                recs.append(t['r_price_one'].format(lo=intel.price_min, hi=intel.price_max,
                                                    median=intel.price_median or intel.price_min))
            if _threshold(intel) is not None:
                recs.append(t['r_ship_one'].format(text=self._shipping_text(intel)))
            if _return_days(intel):
                recs.append(t['r_returns_one'].format(
                    days=_return_days(intel), free=t['free_suffix'] if intel.return_policy.free_returns else ""))
            if intel.has_loyalty_program:
                recs.append(t['r_loyalty_one'])
            if intel.has_email_capture:
                recs.append(t['r_email_one'].format(popup=t['r_popup'] if intel.has_popup else t['r_no_popup']))
            intro = t['recs_intro_one']
        else:
            priced = [i for i in sites if i.price_median]
            if priced:
                recs.append(t['r_price_many'].format(detail=sep.join(
                    f"{site_label(i)} ${i.price_median:.2f}" for i in priced)))
            free = [i for i in sites if _threshold(i) is not None]
            if free:
                recs.append(t['r_ship_many'].format(detail=sep.join(
                    f"{site_label(i)} {self._shipping_text(i)}" for i in free)))
            with_days = [i for i in sites if _return_days(i)]
            if with_days:
                recs.append(t['r_returns_many'].format(detail=sep.join(
                    f"{site_label(i)} {_return_days(i)}{t['days_short']}" for i in with_days)))
            loyal = sum(1 for i in sites if i.has_loyalty_program)
            recs.append(t['r_loyalty_many'].format(k=loyal, n=n))
            intro = t['recs_intro_many'].format(n=n)
        lines = [t['recs'], ""]
        if not recs:
            return lines + [t['r_none'], ""]
        lines += [intro, ""]
        lines += [f"{idx}. {rec}" for idx, rec in enumerate(recs, 1)]
        return lines + [""]

    def _appendix(self, analyzed, not_seen, run_info) -> List[str]:
        t = self.t
        lines = [t['appendix'], "", t['methodology'], ""]
        pages = sum(len(i.pages_crawled) for i in analyzed)
        if 'ignore_robots' not in run_info:
            robots = t['robots_unknown']
        else:
            robots = t['robots_no'] if run_info['ignore_robots'] else t['robots_yes']
        if len(analyzed) + len(not_seen) == 1:
            lines.append(t['m_collection_one'].format(pages=pages, robots=robots))
        else:
            lines.append(t['m_collection'].format(pages=pages, n=len(analyzed) + len(not_seen), robots=robots))
        names = BRANCH_NAMES[self.language]
        ns = NOT_SEEN_TEXT[self.language]
        for intel in analyzed:
            branches = intel.fetch_branches or {}
            shown = self.t['list_sep'].join(t['responses'].format(branch=names.get(b, b), n=c)
                                            for b, c in branches.items()) or t['na']
            lines.append(t['m_site'].format(site=site_label(intel), pages=len(intel.pages_crawled), branches=shown))
            if intel.product_sample:
                lines.append(t['m_sample'].format(site=site_label(intel),
                                                  text=describe_sample(intel.product_sample, self.language)))
        for intel in not_seen:
            lines.append(t['m_site_not_seen'].format(site=site_label(intel), status=ns['short'][intel.status],
                                                     attempts=format_attempts(intel.fetch_attempts, self.language)))
        if 'render_js' in run_info:
            lines.append(t['m_js'].format(text=t['js_yes'] if run_info['render_js'] else t['js_no']))

        with_ai = [i for i in analyzed if i.ai_model]
        if with_ai:
            models = ", ".join(sorted({i.ai_model for i in with_ai}))
            lines.append(t['m_llm_one'].format(models=models) if len(analyzed) == 1 else
                         t['m_llm_many'].format(k=len(with_ai), n=len(analyzed), models=models))
        elif run_info.get('ai_requested'):
            lines.append(t['m_llm_unavailable'].format(model=run_info.get('ai_model', '?')))
        else:
            lines.append(t['m_llm_none'])
        if analyzed:
            lines.append(t['m_pressure'])
        lines += ["", t['evidence'], "", t['evidence_header'], "|" + "---|" * 3] + t['evidence_rows']
        return lines + ["", "---", "", t['footer']]
