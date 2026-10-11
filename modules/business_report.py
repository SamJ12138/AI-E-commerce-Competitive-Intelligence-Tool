"""
business_report.py - Professional Business Intelligence Report Generator

Generates executive-level competitive intelligence reports following
McKinsey/BCG/Bain consulting frameworks.

Report Structure:
1. Executive Summary
2. Market Overview & Industry Context  
3. Competitor Profiles (deep-dive)
4. Comparative Analysis
5. SWOT Analysis
6. Strategic Recommendations
7. Historical Tracking & Changes

Based on: https://slideworks.io/resources/competitive-analysis-framework-and-template
"""

import logging
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from .models import SiteIntelligence, ChangeReport, Platform

logger = logging.getLogger(__name__)


class BusinessReportGenerator:
    """
    Generates professional business intelligence reports.
    Follows consulting best practices for competitive analysis.
    """
    
    def __init__(self, output_dir: str = "output", language: str = "en"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.language = language
        self.is_en = language == 'en'
    
    def generate_report(
        self,
        intel_list: List[SiteIntelligence],
        changes: Dict[str, Optional[ChangeReport]],
        scan_history: Dict[str, List[Dict]] = None,
        report_name: str = "business_report"
    ) -> str:
        """
        Generate comprehensive business intelligence report.
        
        Args:
            intel_list: List of SiteIntelligence objects
            changes: Dict mapping domain to ChangeReport
            scan_history: Dict mapping domain to list of historical scans
            report_name: Output filename (without extension)
            
        Returns:
            Path to generated report
        """
        report_path = self.output_dir / f"{report_name}.md"
        
        lines = []
        
        # 1. Executive Summary
        lines.extend(self._generate_executive_summary(intel_list, changes))
        
        # 2. Market Overview
        lines.extend(self._generate_market_overview(intel_list))
        
        # 3. Competitor Profiles
        lines.extend(self._generate_competitor_profiles(intel_list, changes, scan_history))
        
        # 4. Comparative Analysis
        lines.extend(self._generate_comparative_analysis(intel_list))
        
        # 5. SWOT Matrix
        lines.extend(self._generate_swot_analysis(intel_list))
        
        # 6. Strategic Recommendations
        lines.extend(self._generate_strategic_recommendations(intel_list))
        
        # 7. Appendix: Data Sources & Methodology
        lines.extend(self._generate_appendix(intel_list))
        
        # Write report
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        logger.info(f"Generated business report: {report_path}")
        return str(report_path)
    
    def _generate_executive_summary(
        self,
        intel_list: List[SiteIntelligence],
        changes: Dict[str, Optional[ChangeReport]]
    ) -> List[str]:
        """Generate executive summary section."""
        lines = []
        
        if self.is_en:
            lines.append("# Competitive Intelligence Report")
            lines.append("")
            lines.append(f"**Report Date:** {datetime.now().strftime('%B %d, %Y')}")
            lines.append(f"**Competitors Analyzed:** {len(intel_list)}")
            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append("## Executive Summary")
            lines.append("")
        else:
            lines.append("# 竞争情报分析报告")
            lines.append("")
            lines.append(f"**报告日期:** {datetime.now().strftime('%Y年%m月%d日')}")
            lines.append(f"**分析竞品数:** {len(intel_list)}")
            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append("## 执行摘要")
            lines.append("")
        
        # Key findings
        if self.is_en:
            lines.append("### Key Findings")
            lines.append("")
        else:
            lines.append("### 关键发现")
            lines.append("")
        
        # Calculate key metrics
        platforms = defaultdict(int)
        price_ranges = []
        has_free_shipping = 0
        has_loyalty = 0
        avg_return_days = []
        
        for intel in intel_list:
            platforms[intel.platform.value] += 1
            if intel.price_min and intel.price_max:
                price_ranges.append((intel.price_min, intel.price_max))
            if intel.shipping_policy and intel.shipping_policy.free_shipping_threshold == 0:
                has_free_shipping += 1
            if intel.has_loyalty_program:
                has_loyalty += 1
            if intel.return_policy and intel.return_policy.return_days:
                avg_return_days.append(intel.return_policy.return_days)
        
        # Platform distribution
        dominant_platform = max(platforms.items(), key=lambda x: x[1]) if platforms else ("Unknown", 0)
        
        if self.is_en:
            lines.append(f"**Platform Landscape:** {dominant_platform[1]} of {len(intel_list)} competitors ({dominant_platform[1]*100//len(intel_list)}%) use {dominant_platform[0]}.")
            lines.append("")
        else:
            lines.append(f"**平台分布:** {len(intel_list)}个竞品中有{dominant_platform[1]}个 ({dominant_platform[1]*100//len(intel_list)}%) 使用{dominant_platform[0]}平台。")
            lines.append("")
        
        # Pricing insights
        if price_ranges:
            all_prices = [p for pr in price_ranges for p in pr]
            avg_min = sum(pr[0] for pr in price_ranges) / len(price_ranges)
            avg_max = sum(pr[1] for pr in price_ranges) / len(price_ranges)
            if self.is_en:
                lines.append(f"**Pricing:** Average price range across competitors is ${avg_min:.0f}-${avg_max:.0f}. Market spans ${min(all_prices):.0f} to ${max(all_prices):.0f}.")
                lines.append("")
            else:
                lines.append(f"**定价分析:** 竞品平均价格区间为${avg_min:.0f}-${avg_max:.0f}，市场价格跨度为${min(all_prices):.0f}至${max(all_prices):.0f}。")
                lines.append("")
        
        # Shipping & returns
        if self.is_en:
            lines.append(f"**Shipping:** {has_free_shipping} of {len(intel_list)} competitors ({has_free_shipping*100//len(intel_list)}%) offer free shipping.")
            if avg_return_days:
                lines.append(f"**Returns:** Average return window is {sum(avg_return_days)//len(avg_return_days)} days.")
            lines.append("")
        else:
            lines.append(f"**运费策略:** {len(intel_list)}个竞品中有{has_free_shipping}个 ({has_free_shipping*100//len(intel_list)}%) 提供免运费。")
            if avg_return_days:
                lines.append(f"**退货政策:** 平均退货周期为{sum(avg_return_days)//len(avg_return_days)}天。")
            lines.append("")
        
        # Changes detected
        changes_detected = sum(1 for cr in changes.values() if cr and cr.has_changes())
        if changes_detected > 0:
            if self.is_en:
                lines.append(f"**Changes Since Last Scan:** {changes_detected} competitors have made changes to their offerings or policies.")
                lines.append("")
            else:
                lines.append(f"**变化监测:** 自上次扫描以来，有{changes_detected}个竞品进行了调整。")
                lines.append("")
        
        lines.append("")
        return lines
    
    def _generate_market_overview(self, intel_list: List[SiteIntelligence]) -> List[str]:
        """Generate market overview section."""
        lines = []
        
        if self.is_en:
            lines.append("## Market Overview")
            lines.append("")
            lines.append("### Industry Landscape")
            lines.append("")
        else:
            lines.append("## 市场概览")
            lines.append("")
            lines.append("### 行业格局")
            lines.append("")
        
        # Platform breakdown
        platforms = defaultdict(list)
        for intel in intel_list:
            platforms[intel.platform.value].append(intel.domain)
        
        if self.is_en:
            lines.append("**Platform Distribution:**")
            lines.append("")
            for platform, domains in sorted(platforms.items(), key=lambda x: -len(x[1])):
                pct = len(domains) * 100 // len(intel_list)
                lines.append(f"- **{platform}** ({pct}%): {', '.join(domains[:5])}" + ("..." if len(domains) > 5 else ""))
            lines.append("")
        else:
            lines.append("**平台分布:**")
            lines.append("")
            for platform, domains in sorted(platforms.items(), key=lambda x: -len(x[1])):
                pct = len(domains) * 100 // len(intel_list)
                lines.append(f"- **{platform}** ({pct}%): {', '.join(domains[:5])}" + ("..." if len(domains) > 5 else ""))
            lines.append("")
        
        # Pricing tiers
        if self.is_en:
            lines.append("### Pricing Landscape")
            lines.append("")
        else:
            lines.append("### 价格分布")
            lines.append("")
        
        price_tiers = {"Budget (<$50)": [], "Mid-range ($50-150)": [], "Premium ($150+)": []}
        for intel in intel_list:
            if intel.price_median:
                if intel.price_median < 50:
                    price_tiers["Budget (<$50)"].append(intel.domain)
                elif intel.price_median < 150:
                    price_tiers["Mid-range ($50-150)"].append(intel.domain)
                else:
                    price_tiers["Premium ($150+)"].append(intel.domain)
        
        for tier, domains in price_tiers.items():
            if domains:
                lines.append(f"- **{tier}:** {', '.join(domains)}")
        lines.append("")
        
        return lines
    
    def _generate_competitor_profiles(
        self,
        intel_list: List[SiteIntelligence],
        changes: Dict[str, Optional[ChangeReport]],
        scan_history: Dict[str, List[Dict]] = None
    ) -> List[str]:
        """Generate individual competitor profiles."""
        lines = []
        
        if self.is_en:
            lines.append("## Competitor Profiles")
            lines.append("")
        else:
            lines.append("## 竞品档案")
            lines.append("")
        
        for intel in intel_list:
            lines.extend(self._generate_single_profile(intel, changes.get(intel.domain), scan_history))
        
        return lines
    
    def _generate_single_profile(
        self,
        intel: SiteIntelligence,
        change_report: Optional[ChangeReport],
        scan_history: Dict[str, List[Dict]] = None
    ) -> List[str]:
        """Generate profile for a single competitor."""
        lines = []
        
        lines.append(f"### {intel.domain}")
        lines.append("")
        
        # Basic info - compact format
        lines.append(f"**Website:** [{intel.url}]({intel.url}) | **Platform:** {intel.platform.value}")
        lines.append("")
        
        # Scan history
        if scan_history and intel.domain in scan_history:
            history = scan_history[intel.domain]
            scan_count = len(history)
            if scan_count > 1:
                first_scan = history[-1].get('scan_timestamp', 'Unknown')[:10]
                latest_scan = history[0].get('scan_timestamp', 'Unknown')[:10]
                if self.is_en:
                    lines.append(f"**Scan History:** {scan_count} scans (First: {first_scan}, Latest: {latest_scan})")
                else:
                    lines.append(f"**扫描历史:** 共{scan_count}次 (首次: {first_scan}, 最近: {latest_scan})")
                lines.append("")
        
        # Key metrics in bullet format
        if self.is_en:
            lines.append("**Key Metrics:**")
        else:
            lines.append("**关键指标:**")
        lines.append("")
        
        # Pricing
        if intel.price_min and intel.price_max:
            if self.is_en:
                lines.append(f"- **Price Range:** ${intel.price_min:.0f} - ${intel.price_max:.0f} (Median: ${intel.price_median:.0f})")
            else:
                lines.append(f"- **价格区间:** ${intel.price_min:.0f} - ${intel.price_max:.0f} (中位数: ${intel.price_median:.0f})")
        
        # Shipping
        if intel.shipping_policy:
            ship = intel.shipping_policy
            if ship.free_shipping_threshold is not None:
                if ship.free_shipping_threshold == 0:
                    ship_str = "Free shipping on all orders" if self.is_en else "全场免运费"
                else:
                    ship_str = f"Free over ${ship.free_shipping_threshold:.0f}" if self.is_en else f"满${ship.free_shipping_threshold:.0f}免运费"
            else:
                ship_str = "Paid shipping" if self.is_en else "有运费"
            lines.append(f"- **Shipping:** {ship_str}")
        
        # Returns
        if intel.return_policy and intel.return_policy.return_days:
            ret = intel.return_policy
            ret_str = f"{ret.return_days} days"
            if ret.free_returns:
                ret_str += " (free)" if self.is_en else " (免费)"
            lines.append(f"- **Returns:** {ret_str}")
        
        # Marketing tactics
        tactics = []
        if intel.has_popup:
            tactics.append("Popup" if self.is_en else "弹窗")
        if intel.has_email_capture:
            tactics.append("Email Capture" if self.is_en else "邮件订阅")
        if intel.has_loyalty_program:
            tactics.append("Loyalty Program" if self.is_en else "会员计划")
        if intel.has_subscriptions:
            tactics.append("Subscriptions" if self.is_en else "订阅模式")
        if tactics:
            lines.append(f"- **Marketing:** {', '.join(tactics)}")
        
        lines.append("")
        
        # LLM insights (only when the Ollama step ran and produced them)
        if intel.ai_model and intel.ai_insights.get('key_insights'):
            if self.is_en:
                lines.append(f"**Key Insights (AI, Ollama model {intel.ai_model}):**")
            else:
                lines.append(f"**关键洞察（AI，Ollama 模型 {intel.ai_model}）:**")
            lines.append("")
            for insight in intel.ai_insights.get('key_insights', [])[:5]:
                lines.append(f"- {insight}")
            lines.append("")
        
        # Changes since last scan
        if change_report and change_report.has_changes():
            if self.is_en:
                lines.append("**Changes Since Last Scan:**")
            else:
                lines.append("**自上次扫描以来的变化:**")
            lines.append("")
            
            if change_report.price_changes:
                for change in change_report.price_changes[:3]:
                    lines.append(f"- {change}")
            if change_report.policy_changes:
                for change in change_report.policy_changes[:3]:
                    lines.append(f"- {change}")
            if change_report.promo_changes:
                for change in change_report.promo_changes[:3]:
                    lines.append(f"- {change}")
            lines.append("")
        
        lines.append("---")
        lines.append("")
        
        return lines
    
    def _generate_comparative_analysis(self, intel_list: List[SiteIntelligence]) -> List[str]:
        """Generate comparative analysis table."""
        lines = []
        
        if self.is_en:
            lines.append("## Comparative Analysis")
            lines.append("")
            lines.append("### Feature Comparison Matrix")
            lines.append("")
            
            # Compact comparison table
            lines.append("| Competitor | Price Range | Free Ship | Returns | Loyalty | Subscriptions |")
            lines.append("|------------|-------------|-----------|---------|---------|---------------|")
        else:
            lines.append("## 竞品对比分析")
            lines.append("")
            lines.append("### 功能对比矩阵")
            lines.append("")
            
            lines.append("| 竞品 | 价格区间 | 免运费 | 退货 | 会员 | 订阅 |")
            lines.append("|------|---------|--------|------|------|------|")
        
        for intel in intel_list:
            # Price
            price = f"${intel.price_min:.0f}-${intel.price_max:.0f}" if intel.price_min else "N/A"
            
            # Free shipping
            free_ship = "❌"
            if intel.shipping_policy:
                if intel.shipping_policy.free_shipping_threshold == 0:
                    free_ship = "✅ All"
                elif intel.shipping_policy.free_shipping_threshold:
                    free_ship = f"${intel.shipping_policy.free_shipping_threshold:.0f}+"
            
            # Returns
            returns = "N/A"
            if intel.return_policy and intel.return_policy.return_days:
                returns = f"{intel.return_policy.return_days}d"
                if intel.return_policy.free_returns:
                    returns += " ✅"
            
            # Loyalty
            loyalty = "✅" if intel.has_loyalty_program else "❌"
            
            # Subscriptions
            subs = "✅" if intel.has_subscriptions else "❌"
            
            lines.append(f"| {intel.domain} | {price} | {free_ship} | {returns} | {loyalty} | {subs} |")
        
        lines.append("")
        return lines
    
    def _generate_swot_analysis(self, intel_list: List[SiteIntelligence]) -> List[str]:
        """Generate SWOT analysis based on market data."""
        lines = []
        
        if self.is_en:
            lines.append("## Strategic SWOT Analysis")
            lines.append("")
            lines.append("Based on the competitive landscape analysis:")
            lines.append("")
        else:
            lines.append("## 战略SWOT分析")
            lines.append("")
            lines.append("基于竞争格局分析:")
            lines.append("")
        
        # Analyze market characteristics
        has_free_ship = sum(1 for i in intel_list if i.shipping_policy and i.shipping_policy.free_shipping_threshold == 0)
        has_loyalty = sum(1 for i in intel_list if i.has_loyalty_program)
        has_subs = sum(1 for i in intel_list if i.has_subscriptions)
        prices = [i.price_median for i in intel_list if i.price_median]
        
        if self.is_en:
            lines.append("### Opportunities")
            lines.append("")
            if has_free_ship < len(intel_list) * 0.5:
                lines.append("- **Free Shipping Gap:** Only {:.0%} of competitors offer free shipping - potential differentiator".format(has_free_ship/len(intel_list)))
            if has_loyalty < len(intel_list) * 0.4:
                lines.append("- **Loyalty Program Opportunity:** Low adoption ({:.0%}) suggests room for customer retention innovation".format(has_loyalty/len(intel_list)))
            if has_subs < len(intel_list) * 0.3:
                lines.append("- **Subscription Model:** Under-utilized by competitors ({:.0%}) - potential recurring revenue stream".format(has_subs/len(intel_list)))
            if prices:
                avg_price = sum(prices) / len(prices)
                lines.append(f"- **Pricing:** Market average at ${avg_price:.0f} - consider value positioning above or below")
            lines.append("")
            
            lines.append("### Threats")
            lines.append("")
            if has_free_ship > len(intel_list) * 0.5:
                lines.append("- **Free Shipping Expectation:** {:.0%} of competitors offer free shipping - becoming table stakes".format(has_free_ship/len(intel_list)))
            lines.append("- **Platform Concentration:** Heavy reliance on Shopify ecosystem may limit differentiation")
            lines.append("- **Price Competition:** Multiple players in similar price ranges may pressure margins")
            lines.append("")
        else:
            lines.append("### 机会")
            lines.append("")
            if has_free_ship < len(intel_list) * 0.5:
                lines.append("- **免运费差距:** 仅{:.0%}的竞品提供免运费 - 潜在差异化点".format(has_free_ship/len(intel_list)))
            if has_loyalty < len(intel_list) * 0.4:
                lines.append("- **会员计划机会:** 低采用率 ({:.0%}) 表明客户留存创新空间大".format(has_loyalty/len(intel_list)))
            if has_subs < len(intel_list) * 0.3:
                lines.append("- **订阅模式:** 竞品利用不足 ({:.0%}) - 潜在经常性收入来源".format(has_subs/len(intel_list)))
            lines.append("")
            
            lines.append("### 威胁")
            lines.append("")
            if has_free_ship > len(intel_list) * 0.5:
                lines.append("- **免运费预期:** {:.0%}的竞品提供免运费 - 正在成为行业标配".format(has_free_ship/len(intel_list)))
            lines.append("- **平台集中:** 对Shopify生态的依赖可能限制差异化")
            lines.append("- **价格竞争:** 相似价格区间的多个玩家可能压缩利润空间")
            lines.append("")
        
        return lines
    
    def _generate_strategic_recommendations(self, intel_list: List[SiteIntelligence]) -> List[str]:
        """Generate strategic recommendations."""
        lines = []
        
        if self.is_en:
            lines.append("## Strategic Recommendations")
            lines.append("")
            lines.append("Based on the competitive analysis, consider the following strategic initiatives:")
            lines.append("")
            
            lines.append("### Immediate Actions (0-3 months)")
            lines.append("")
            lines.append("1. **Benchmark Pricing:** Review your pricing against the competitive median to ensure market positioning")
            lines.append("2. **Shipping Policy Review:** Evaluate free shipping threshold against competitors")
            lines.append("3. **Return Policy Optimization:** Align with industry standard return windows")
            lines.append("")
            
            lines.append("### Short-term Initiatives (3-6 months)")
            lines.append("")
            lines.append("1. **Customer Retention:** Implement or enhance loyalty program if competitors lack this")
            lines.append("2. **Email Marketing:** Strengthen email capture and nurturing if competitive gap exists")
            lines.append("3. **Product Bundling:** Consider bundles/subscriptions if under-utilized in market")
            lines.append("")
            
            lines.append("### Long-term Strategy (6-12 months)")
            lines.append("")
            lines.append("1. **Differentiation:** Identify unique value propositions not offered by competitors")
            lines.append("2. **Market Expansion:** Consider underserved segments or price tiers")
            lines.append("3. **Technology Investment:** Evaluate platform capabilities vs. competitors")
            lines.append("")
        else:
            lines.append("## 战略建议")
            lines.append("")
            lines.append("基于竞争分析，建议考虑以下战略举措:")
            lines.append("")
            
            lines.append("### 立即行动 (0-3个月)")
            lines.append("")
            lines.append("1. **定价基准:** 对比竞品中位数审视定价，确保市场定位")
            lines.append("2. **运费政策审查:** 评估免运费门槛与竞品的对比")
            lines.append("3. **退货政策优化:** 与行业标准退货周期对齐")
            lines.append("")
            
            lines.append("### 短期举措 (3-6个月)")
            lines.append("")
            lines.append("1. **客户留存:** 如竞品缺乏会员计划，实施或加强会员体系")
            lines.append("2. **邮件营销:** 如存在竞争差距，加强邮件收集和培育")
            lines.append("3. **产品捆绑:** 如市场利用不足，考虑捆绑/订阅模式")
            lines.append("")
            
            lines.append("### 长期战略 (6-12个月)")
            lines.append("")
            lines.append("1. **差异化:** 识别竞品未提供的独特价值主张")
            lines.append("2. **市场扩展:** 考虑未充分服务的细分市场或价格区间")
            lines.append("3. **技术投资:** 评估平台能力与竞品的对比")
            lines.append("")
        
        return lines
    
    def _analysis_line(self, intel_list: List[SiteIntelligence]) -> str:
        """Name the LLM only for the sites where it produced text."""
        models = sorted({i.ai_model for i in intel_list if i.ai_model})
        with_ai = sum(1 for i in intel_list if i.ai_model)
        if not models:
            return ("- **Analysis:** Rule-based summaries and a rule-based pressure score"
                    if self.is_en else "- **分析:** 基于规则的摘要和规则计算的竞争压力评分")
        if self.is_en:
            return (f"- **Analysis:** Key insights for {with_ai} of {len(intel_list)} sites generated by a local "
                    f"LLM (Ollama, {', '.join(models)}); everything else is rule-based")
        return (f"- **分析:** {len(intel_list)}个站点中有{with_ai}个的关键洞察由本地 LLM 生成"
                f"（Ollama，{', '.join(models)}）；其余内容均基于规则")

    def _generate_appendix(self, intel_list: List[SiteIntelligence]) -> List[str]:
        """Generate appendix with methodology and data sources."""
        lines = []
        
        if self.is_en:
            lines.append("## Appendix")
            lines.append("")
            lines.append("### Methodology")
            lines.append("")
            lines.append("This report was generated using automated competitive intelligence gathering:")
            lines.append("")
            lines.append("- **Data Collection:** Automated web scraping respecting robots.txt")
            lines.append(self._analysis_line(intel_list))
            lines.append("- **Verification:** Data sources tracked with evidence levels")
            lines.append("")
            
            lines.append("### Data Quality Notes")
            lines.append("")
            lines.append("| Evidence Level | Source Type | Confidence |")
            lines.append("|----------------|-------------|------------|")
            lines.append("| Level 1 | Official policy pages | High |")
            lines.append("| Level 2 | FAQ/Help center | High |")
            lines.append("| Level 3 | Product/cart inference | Medium |")
            lines.append("| Level 4 | Blocked by robots.txt | Manual verification needed |")
            lines.append("")
        else:
            lines.append("## 附录")
            lines.append("")
            lines.append("### 方法论")
            lines.append("")
            lines.append("本报告使用自动化竞争情报收集生成:")
            lines.append("")
            lines.append("- **数据收集:** 遵守robots.txt的自动化网页抓取")
            lines.append(self._analysis_line(intel_list))
            lines.append("- **验证:** 数据来源按证据级别追踪")
            lines.append("")
            
            lines.append("### 数据质量说明")
            lines.append("")
            lines.append("| 证据级别 | 来源类型 | 置信度 |")
            lines.append("|---------|---------|--------|")
            lines.append("| 级别1 | 官方政策页面 | 高 |")
            lines.append("| 级别2 | FAQ/帮助中心 | 高 |")
            lines.append("| 级别3 | 产品/购物车推断 | 中 |")
            lines.append("| 级别4 | 被robots.txt阻止 | 需手动验证 |")
            lines.append("")
        
        lines.append("---")
        lines.append("")
        if self.is_en:
            lines.append("*Report generated by E-commerce Competitive Intelligence Tool*")
        else:
            lines.append("*报告由电商竞争情报工具生成*")
        
        return lines
