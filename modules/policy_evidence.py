"""
policy_evidence.py - Policy Evidence Ladder System

Implements a legally-safe approach to policy extraction by:
1. Tracking where each piece of data comes from
2. Falling back gracefully when pages are blocked
3. Recommending manual verification when needed

EVIDENCE LADDER (highest to lowest confidence):
Level 1: ✅ Official policy page (e.g., /policies/shipping-policy)
Level 2: ✅ FAQ/Help Center page (e.g., /pages/faq, /help)
Level 3: ⚠️ Product/Cart page inference (less authoritative)
Level 4: ❌ Blocked by robots.txt - manual verification recommended

This approach ensures legal compliance by:
- Respecting robots.txt by default
- Clearly marking data source and confidence level
- Flagging items that need human verification
"""

import re
import logging
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup

from .models import ShippingPolicy, ReturnPolicy

logger = logging.getLogger(__name__)


class EvidenceLevel(Enum):
    """Evidence confidence levels for policy data."""
    OFFICIAL_POLICY = 1  # /policies/*, /legal/*, dedicated policy pages
    FAQ_HELP_CENTER = 2  # /faq, /help, /pages/shipping-info
    PRODUCT_CART = 3     # Inferred from product pages, cart, checkout
    BLOCKED = 4          # robots.txt blocked - needs manual verification
    NOT_FOUND = 5        # No data found anywhere


@dataclass
class PolicyEvidence:
    """Tracks evidence source for extracted policy data."""
    level: EvidenceLevel
    source_url: str = ""
    source_type: str = ""  # 'policy_page', 'faq', 'product_page', 'cart', 'homepage'
    extracted_text: str = ""
    confidence_score: float = 0.0  # 0.0-1.0
    requires_verification: bool = False
    blocked_urls: List[str] = field(default_factory=list)
    
    def get_status_emoji(self) -> str:
        """Return status emoji for reports."""
        if self.level == EvidenceLevel.OFFICIAL_POLICY:
            return "✅"
        elif self.level == EvidenceLevel.FAQ_HELP_CENTER:
            return "✅"
        elif self.level == EvidenceLevel.PRODUCT_CART:
            return "⚠️"
        elif self.level == EvidenceLevel.BLOCKED:
            return "❌"
        else:
            return "❓"
    
    def get_status_text(self, language: str = 'en') -> str:
        """Return human-readable status text."""
        if language == 'zh':
            statuses = {
                EvidenceLevel.OFFICIAL_POLICY: "从官方政策页面提取",
                EvidenceLevel.FAQ_HELP_CENTER: "从FAQ/帮助中心提取",
                EvidenceLevel.PRODUCT_CART: "从产品/购物车页面推断",
                EvidenceLevel.BLOCKED: "被robots.txt阻止 - 建议手动验证",
                EvidenceLevel.NOT_FOUND: "未找到相关信息"
            }
        else:
            statuses = {
                EvidenceLevel.OFFICIAL_POLICY: "Extracted from official policy page",
                EvidenceLevel.FAQ_HELP_CENTER: "Extracted from FAQ/Help Center",
                EvidenceLevel.PRODUCT_CART: "Inferred from product/cart pages",
                EvidenceLevel.BLOCKED: "Blocked by robots.txt - manual verification recommended",
                EvidenceLevel.NOT_FOUND: "No information found"
            }
        return statuses.get(self.level, "Unknown")


class PolicyEvidenceLadder:
    """
    Implements the Policy Evidence Ladder for safe, legal policy extraction.
    
    Tries sources in order of authority:
    1. Official policy pages (if allowed)
    2. FAQ/Help center pages (if allowed)
    3. Product/cart page inference
    4. Mark as blocked with manual verification flag
    """
    
    # URL patterns for different evidence levels
    OFFICIAL_POLICY_PATTERNS = [
        r'/policies?/shipping',
        r'/policies?/refund',
        r'/policies?/return',
        r'/policies?/delivery',
        r'/legal/shipping',
        r'/legal/returns?',
        r'/terms.*shipping',
        r'/shipping-policy',
        r'/return-policy',
        r'/refund-policy',
    ]
    
    FAQ_HELP_PATTERNS = [
        r'/faq',
        r'/help',
        r'/support',
        r'/pages?/faq',
        r'/pages?/shipping',
        r'/pages?/returns?',
        r'/pages?/delivery',
        r'/customer-service',
        r'/contact',
        r'/about.*shipping',
    ]
    
    PRODUCT_CART_PATTERNS = [
        r'/products?/',
        r'/collections?/',
        r'/cart',
        r'/checkout',
    ]
    
    def __init__(self, robots_checker=None):
        """
        Initialize with optional robots checker.
        
        Args:
            robots_checker: RobotsChecker instance for checking URL access
        """
        self.robots_checker = robots_checker
        self.blocked_urls: List[str] = []
    
    def classify_url(self, url: str) -> EvidenceLevel:
        """
        Classify a URL into an evidence level based on its path.
        
        Args:
            url: Full URL to classify
            
        Returns:
            EvidenceLevel enum value
        """
        path = urlparse(url).path.lower()
        
        # Check official policy patterns
        for pattern in self.OFFICIAL_POLICY_PATTERNS:
            if re.search(pattern, path):
                return EvidenceLevel.OFFICIAL_POLICY
        
        # Check FAQ/help patterns
        for pattern in self.FAQ_HELP_PATTERNS:
            if re.search(pattern, path):
                return EvidenceLevel.FAQ_HELP_CENTER
        
        # Check product/cart patterns
        for pattern in self.PRODUCT_CART_PATTERNS:
            if re.search(pattern, path):
                return EvidenceLevel.PRODUCT_CART
        
        # Default to product/cart level for unknown pages
        return EvidenceLevel.PRODUCT_CART
    
    def is_url_allowed(self, url: str) -> Tuple[bool, str]:
        """
        Check if URL is allowed by robots.txt.
        
        Args:
            url: URL to check
            
        Returns:
            Tuple of (is_allowed, reason)
        """
        if self.robots_checker is None:
            return True, "No robots checker configured"
        
        is_allowed = self.robots_checker.is_allowed(url)
        if not is_allowed:
            self.blocked_urls.append(url)
            return False, f"Blocked by robots.txt"
        
        return True, "Allowed"
    
    def extract_shipping_with_evidence(
        self,
        pages: Dict[str, Tuple[BeautifulSoup, str]],
        base_url: str
    ) -> Tuple[ShippingPolicy, PolicyEvidence]:
        """
        Extract shipping policy using the evidence ladder.
        
        Args:
            pages: Dict mapping URL to (soup, text) tuples
            base_url: Base URL of the site
            
        Returns:
            Tuple of (ShippingPolicy, PolicyEvidence)
        """
        from .policy_extractor import PolicyExtractor
        extractor = PolicyExtractor()
        
        # Sort pages by evidence level (official first)
        sorted_pages = sorted(
            pages.items(),
            key=lambda x: self.classify_url(x[0]).value
        )
        
        best_policy = ShippingPolicy()
        best_evidence = PolicyEvidence(
            level=EvidenceLevel.NOT_FOUND,
            requires_verification=True
        )
        
        for url, (soup, text) in sorted_pages:
            level = self.classify_url(url)
            
            # Check if URL was blocked
            if url in self.blocked_urls:
                if best_evidence.level.value > EvidenceLevel.BLOCKED.value:
                    best_evidence = PolicyEvidence(
                        level=EvidenceLevel.BLOCKED,
                        source_url=url,
                        source_type='blocked',
                        requires_verification=True,
                        blocked_urls=self.blocked_urls.copy()
                    )
                continue
            
            # Try to extract policy from this page
            policy = extractor.extract_shipping_policy(soup, text)
            
            # Check if we got useful data
            has_useful_data = (
                policy.free_shipping_threshold is not None or
                policy.estimated_days_min is not None or
                policy.regions
            )
            
            if has_useful_data and level.value < best_evidence.level.value:
                best_policy = policy
                best_policy.evidence_source = level.name.lower()
                best_policy.evidence_url = url
                best_policy.evidence_level = level.value
                best_policy.requires_manual_verification = (level.value >= 3)
                
                best_evidence = PolicyEvidence(
                    level=level,
                    source_url=url,
                    source_type=self._get_source_type(level),
                    extracted_text=policy.raw_text[:200],
                    confidence_score=self._calculate_confidence(level, policy),
                    requires_verification=(level.value >= 3)
                )
                
                # If we got official policy data, we can stop
                if level == EvidenceLevel.OFFICIAL_POLICY:
                    break
        
        return best_policy, best_evidence
    
    def extract_returns_with_evidence(
        self,
        pages: Dict[str, Tuple[BeautifulSoup, str]],
        base_url: str
    ) -> Tuple[ReturnPolicy, PolicyEvidence]:
        """
        Extract return policy using the evidence ladder.
        
        Args:
            pages: Dict mapping URL to (soup, text) tuples
            base_url: Base URL of the site
            
        Returns:
            Tuple of (ReturnPolicy, PolicyEvidence)
        """
        from .policy_extractor import PolicyExtractor
        extractor = PolicyExtractor()
        
        # Sort pages by evidence level (official first)
        sorted_pages = sorted(
            pages.items(),
            key=lambda x: self.classify_url(x[0]).value
        )
        
        best_policy = ReturnPolicy()
        best_evidence = PolicyEvidence(
            level=EvidenceLevel.NOT_FOUND,
            requires_verification=True
        )
        
        for url, (soup, text) in sorted_pages:
            level = self.classify_url(url)
            
            # Check if URL was blocked
            if url in self.blocked_urls:
                if best_evidence.level.value > EvidenceLevel.BLOCKED.value:
                    best_evidence = PolicyEvidence(
                        level=EvidenceLevel.BLOCKED,
                        source_url=url,
                        source_type='blocked',
                        requires_verification=True,
                        blocked_urls=self.blocked_urls.copy()
                    )
                continue
            
            # Try to extract policy from this page
            policy = extractor.extract_return_policy(soup, text)
            
            # Check if we got useful data
            has_useful_data = (
                policy.return_days is not None or
                policy.free_returns or
                policy.conditions
            )
            
            if has_useful_data and level.value < best_evidence.level.value:
                best_policy = policy
                best_policy.evidence_source = level.name.lower()
                best_policy.evidence_url = url
                best_policy.evidence_level = level.value
                best_policy.requires_manual_verification = (level.value >= 3)
                
                best_evidence = PolicyEvidence(
                    level=level,
                    source_url=url,
                    source_type=self._get_source_type(level),
                    extracted_text=policy.raw_text[:200],
                    confidence_score=self._calculate_confidence(level, policy),
                    requires_verification=(level.value >= 3)
                )
                
                # If we got official policy data, we can stop
                if level == EvidenceLevel.OFFICIAL_POLICY:
                    break
        
        return best_policy, best_evidence
    
    def _get_source_type(self, level: EvidenceLevel) -> str:
        """Convert evidence level to source type string."""
        mapping = {
            EvidenceLevel.OFFICIAL_POLICY: 'policy_page',
            EvidenceLevel.FAQ_HELP_CENTER: 'faq',
            EvidenceLevel.PRODUCT_CART: 'product_page',
            EvidenceLevel.BLOCKED: 'blocked',
            EvidenceLevel.NOT_FOUND: 'not_found'
        }
        return mapping.get(level, 'unknown')
    
    def _calculate_confidence(self, level: EvidenceLevel, policy: Any) -> float:
        """Calculate confidence score based on evidence level and data quality."""
        # Base confidence from evidence level
        level_confidence = {
            EvidenceLevel.OFFICIAL_POLICY: 0.95,
            EvidenceLevel.FAQ_HELP_CENTER: 0.85,
            EvidenceLevel.PRODUCT_CART: 0.60,
            EvidenceLevel.BLOCKED: 0.10,
            EvidenceLevel.NOT_FOUND: 0.0
        }
        
        base = level_confidence.get(level, 0.5)
        
        # Adjust based on data completeness
        if hasattr(policy, 'raw_text') and policy.raw_text:
            base = min(1.0, base + 0.05)
        
        return round(base, 2)
    
    def generate_evidence_summary(
        self,
        shipping_evidence: PolicyEvidence,
        returns_evidence: PolicyEvidence,
        language: str = 'en'
    ) -> List[str]:
        """
        Generate human-readable evidence summary for reports.
        
        Args:
            shipping_evidence: Evidence for shipping policy
            returns_evidence: Evidence for return policy
            language: 'en' or 'zh'
            
        Returns:
            List of summary strings
        """
        lines = []
        
        if language == 'zh':
            lines.append("### 📋 数据来源证据")
            lines.append("")
            lines.append("| 政策类型 | 状态 | 来源 | 需要验证 |")
            lines.append("|---------|------|------|---------|")
            
            ship_status = shipping_evidence.get_status_emoji()
            ship_text = shipping_evidence.get_status_text('zh')
            ship_verify = "是" if shipping_evidence.requires_verification else "否"
            lines.append(f"| 运费政策 | {ship_status} | {ship_text} | {ship_verify} |")
            
            ret_status = returns_evidence.get_status_emoji()
            ret_text = returns_evidence.get_status_text('zh')
            ret_verify = "是" if returns_evidence.requires_verification else "否"
            lines.append(f"| 退货政策 | {ret_status} | {ret_text} | {ret_verify} |")
            
            if shipping_evidence.blocked_urls or returns_evidence.blocked_urls:
                lines.append("")
                lines.append("**⚠️ 被阻止的URL (建议手动验证):**")
                all_blocked = set(shipping_evidence.blocked_urls + returns_evidence.blocked_urls)
                for url in list(all_blocked)[:5]:
                    lines.append(f"- {url}")
        else:
            lines.append("### 📋 Data Source Evidence")
            lines.append("")
            lines.append("| Policy Type | Status | Source | Needs Verification |")
            lines.append("|-------------|--------|--------|-------------------|")
            
            ship_status = shipping_evidence.get_status_emoji()
            ship_text = shipping_evidence.get_status_text('en')
            ship_verify = "Yes" if shipping_evidence.requires_verification else "No"
            lines.append(f"| Shipping | {ship_status} | {ship_text} | {ship_verify} |")
            
            ret_status = returns_evidence.get_status_emoji()
            ret_text = returns_evidence.get_status_text('en')
            ret_verify = "Yes" if returns_evidence.requires_verification else "No"
            lines.append(f"| Returns | {ret_status} | {ret_text} | {ret_verify} |")
            
            if shipping_evidence.blocked_urls or returns_evidence.blocked_urls:
                lines.append("")
                lines.append("**⚠️ Blocked URLs (manual verification recommended):**")
                all_blocked = set(shipping_evidence.blocked_urls + returns_evidence.blocked_urls)
                for url in list(all_blocked)[:5]:
                    lines.append(f"- {url}")
        
        return lines


def create_blocked_policy_note(blocked_urls: List[str], policy_type: str, language: str = 'en') -> str:
    """
    Create a note for reports when policy URLs are blocked.
    
    Args:
        blocked_urls: List of blocked URL paths
        policy_type: 'shipping' or 'returns'
        language: 'en' or 'zh'
        
    Returns:
        Formatted note string
    """
    if language == 'zh':
        return f"⚠️ {policy_type}政策页面被robots.txt阻止。建议手动访问官网验证。"
    else:
        return f"⚠️ {policy_type.title()} policy page blocked by robots.txt. Manual verification recommended."
