"""
policy_extractor.py - Extract shipping and return policies from e-commerce pages.

Extracts structured information from policy pages:
- Shipping regions and delivery times
- Free shipping thresholds
- Return windows and conditions
- Refund policies
"""

import re
import logging
from typing import Optional, List, Tuple
from bs4 import BeautifulSoup

from .models import ShippingPolicy, ReturnPolicy
from . import obs

logger = logging.getLogger(__name__)


class PolicyExtractor:
    """
    Extracts structured policy information from e-commerce pages.
    """
    
    # Shipping time patterns
    SHIPPING_TIME_PATTERNS = [
        r'(\d+)\s*[-–to]+\s*(\d+)\s*(business\s+)?(days?|weeks?)',
        r'within\s+(\d+)\s*(business\s+)?(days?|weeks?)',
        r'(\d+)\s*(business\s+)?(days?|weeks?)\s+delivery',
        r'ships?\s+in\s+(\d+)\s*[-–to]*\s*(\d*)\s*(business\s+)?(days?)',
        r'delivery\s+time[:\s]+(\d+)\s*[-–to]*\s*(\d*)\s*(days?)',
    ]
    
    # Free shipping patterns
    FREE_SHIPPING_PATTERNS = [
        r'free\s+(standard\s+)?shipping\s+(on\s+)?orders?\s+(over\s+)?\$(\d+)',
        r'free\s+shipping\s+for\s+orders?\s+\$(\d+)\+',
        r'\$(\d+)\s+(or\s+more\s+)?for\s+free\s+shipping',
        r'spend\s+\$(\d+).*free\s+shipping',
        # "Free Fast(ish) Shipping (USPS Ground, 2-5 business days) on orders $75+"
        r'free\s+(?:[\w()\'-]+\s+){0,2}shipping\s*(?:\([^)]{0,80}\)\s*)?on\s+orders?\s+(?:over\s+|of\s+)?\$(\d+)',
        # "If you spend over $50 USD, we'll hook you up with free shipping"
        r'spend\s+(?:over\s+|more\s+than\s+)\$(\d+)[^.!?]{0,80}free\s+shipping',
        r'free\s+shipping\s+on\s+all\s+orders',
    ]
    
    # Return days patterns
    RETURN_DAYS_PATTERNS = [
        r'(\d+)\s*[-–]?\s*days?\s+(return|exchange|refund)',
        r'return\s+(within\s+)?(\d+)\s*days?',
        r'(\d+)\s*[-–]?\s*day\s+return\s+policy',
        r'returns?\s+accepted\s+(within\s+)?(\d+)\s*days?',
        r'(\d+)\s*[-–]?\s*day\s+money[- ]back',
        r'(?:return|refund)s?\b[^.]{0,40}?\b(?:lasts|is|of)\s+(\d+)\s*days?',
        r'within\s+(\d+)\s*days?\s+(?:of|from|after)\s+(?:your\s+)?(?:purchase|delivery|receipt)',
    ]
    
    # Region patterns
    REGION_PATTERNS = {
        'United States': [r'united\s+states', r'\bUS\b', r'\bUSA\b', r'domestic'],
        'Canada': [r'\bcanada\b', r'\bCA\b'],
        'International': [r'international', r'worldwide', r'global'],
        'Europe': [r'\beurope\b', r'\bEU\b', r'european'],
        'UK': [r'\buk\b', r'united\s+kingdom', r'britain'],
        'Australia': [r'\baustralia\b', r'\bAU\b'],
    }
    
    def extract_shipping_policy(
        self,
        soup: BeautifulSoup,
        page_text: str
    ) -> ShippingPolicy:
        """
        Extract shipping policy information.
        
        Args:
            soup: Parsed HTML of policy page
            page_text: Raw text content of the page
            
        Returns:
            ShippingPolicy object
        """
        policy = ShippingPolicy()
        text_lower = page_text.lower()
        
        # Extract shipping regions
        policy.regions = self._extract_regions(text_lower)
        
        # Extract free shipping threshold
        policy.free_shipping_threshold = self._extract_free_shipping_threshold(text_lower)
        
        # Extract delivery times
        min_days, max_days = self._extract_delivery_times(text_lower)
        policy.estimated_days_min = min_days
        policy.estimated_days_max = max_days
        
        # Check for international shipping
        policy.has_international = 'international' in text_lower or 'worldwide' in text_lower
        
        # Store raw text for reference
        policy.raw_text = page_text[:2000]  # First 2000 chars
        
        return policy
    
    def extract_return_policy(
        self,
        soup: BeautifulSoup,
        page_text: str
    ) -> ReturnPolicy:
        """
        Extract return policy information.
        
        Args:
            soup: Parsed HTML of policy page
            page_text: Raw text content of the page
            
        Returns:
            ReturnPolicy object
        """
        policy = ReturnPolicy()
        text_lower = page_text.lower()
        
        # Extract return window
        policy.return_days = self._extract_return_days(text_lower)
        
        # Check for free returns
        policy.free_returns = self._check_free_returns(text_lower)
        
        # Extract conditions
        policy.conditions = self._extract_return_conditions(text_lower)
        
        # Extract exclusions
        policy.exclusions = self._extract_exclusions(text_lower)
        
        # Store raw text
        policy.raw_text = page_text[:2000]
        
        return policy
    
    def _extract_regions(self, text: str) -> List[str]:
        """Extract shipping regions mentioned."""
        regions = []
        
        for region, patterns in self.REGION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    regions.append(region)
                    break

        if not regions:
            obs.note('shipping_regions', ['United States'], 'default', "no region pattern matched")
        return list(set(regions)) if regions else ['United States']
    
    def _extract_free_shipping_threshold(self, text: str) -> Optional[float]:
        """Extract free shipping threshold amount."""
        for pattern in self.FREE_SHIPPING_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Find the numeric group
                for group in match.groups():
                    if group and group.isdigit():
                        obs.note('free_shipping_threshold', float(group), 'regex',
                                 f"policy_extractor.FREE_SHIPPING_PATTERNS[{self.FREE_SHIPPING_PATTERNS.index(pattern)}] "
                                 f"matched {match.group(0)!r}")
                        return float(group)

        # Check for "free shipping on all orders"
        if re.search(r'free\s+shipping\s+on\s+all\s+orders', text, re.IGNORECASE):
            obs.note('free_shipping_threshold', 0.0, 'regex', "'free shipping on all orders' -> 0.0")
            return 0.0

        obs.note('free_shipping_threshold', None, 'default', "no FREE_SHIPPING_PATTERNS matched on this page")
        return None
    
    def _extract_delivery_times(self, text: str) -> Tuple[Optional[int], Optional[int]]:
        """Extract estimated delivery time range."""
        for pattern in self.SHIPPING_TIME_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = [g for g in match.groups() if g and g.isdigit()]
                
                if len(groups) >= 2:
                    return int(groups[0]), int(groups[1])
                elif len(groups) == 1:
                    days = int(groups[0])
                    return days, days
        
        return None, None
    
    def _extract_return_days(self, text: str) -> Optional[int]:
        """Extract return window in days."""
        for pattern in self.RETURN_DAYS_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                for group in match.groups():
                    if group and group.isdigit():
                        obs.note('return_days', int(group), 'regex',
                                 f"policy_extractor.RETURN_DAYS_PATTERNS[{self.RETURN_DAYS_PATTERNS.index(pattern)}] "
                                 f"matched {match.group(0)!r}")
                        return int(group)

        obs.note('return_days', None, 'default', "no RETURN_DAYS_PATTERNS matched on this page")
        return None
    
    # Returns are free: "free returns" (not "pain-free returns"), a complimentary label, ...
    FREE_RETURN_PATTERNS = [
        r'(?<![\w-])free\s+returns?',
        r'returns?\s+are\s+(?:always\s+)?free',
        r'no[\s-]+cost\s+returns?',
        r'complimentary\s+returns?',
        r'complimentary\s+return\s+(?:label|shipping)',
        r'free\s+return\s+(?:label|shipping)',
        r'we\s+(?:cover|pay\s+for)\s+(?:the\s+)?return\s+shipping',
    ]
    # The customer pays, or returns are not accepted. Checked per sentence; the first pattern needs
    # the sentence to be about a return as well ("responsible for shipping costs" alone is not).
    PAID_RETURN_PATTERNS = [
        r'\bresponsible\s+for\b[^.]{0,80}\b(?:shipping|postage|label)\b',
        r'\breturn\s+(?:shipping\s+)?fee\b',
        r'\brestocking\s+fee\b',
        r"\b(?:cannot|can't|can\s+not|do\s+not|don't|does\s+not|will\s+not|won't)\s+accept\s+return",
        r'\breturn\s+shipping\s+(?:costs?|charges?|fees?)\s+(?:are|is|will\s+be)\s+deducted',
    ]

    def _check_free_returns(self, text: str) -> Optional[bool]:
        """True: the page says returns are free. False: it says the customer pays for them, or that
        returns are not accepted. None: it says neither, or both (silence is not "not free")."""
        free = next(((p, m) for p in self.FREE_RETURN_PATTERNS for m in [re.search(p, text, re.IGNORECASE)] if m),
                    None)
        paid = None
        for sentence in re.split(r'(?<=[.!?])\s+', text):
            for i, pattern in enumerate(self.PAID_RETURN_PATTERNS):
                m = re.search(pattern, sentence, re.IGNORECASE)
                if m and (i != 0 or re.search(r'\breturn', sentence, re.IGNORECASE)):
                    paid = (pattern, m)
                    break
            if paid:
                break

        if free and paid:
            obs.note('free_returns', None, 'default',
                     f"both free ({free[1].group(0)!r}) and paid ({paid[1].group(0)!r}) return wording on this page")
            return None
        if free:
            obs.note('free_returns', True, 'regex', f"FREE_RETURN_PATTERNS {free[0]!r} matched {free[1].group(0)!r}")
            return True
        if paid:
            obs.note('free_returns', False, 'regex', f"PAID_RETURN_PATTERNS {paid[0]!r} matched {paid[1].group(0)!r}")
            return False
        obs.note('free_returns', None, 'default', "no free or paid return wording on this page")
        return None

    def _extract_return_conditions(self, text: str) -> List[str]:
        """Extract return conditions."""
        conditions = []
        
        condition_patterns = [
            (r'unworn', 'Items must be unworn'),
            (r'original\s+(packaging|tags)', 'Original packaging/tags required'),
            (r'unused', 'Items must be unused'),
            (r'unwashed', 'Items must be unwashed'),
            (r'receipt', 'Receipt required'),
            (r'proof\s+of\s+purchase', 'Proof of purchase required'),
            (r'original\s+condition', 'Items must be in original condition'),
        ]
        
        for pattern, condition in condition_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                conditions.append(condition)
        
        return conditions[:5]  # Limit to 5 conditions
    
    def _extract_exclusions(self, text: str) -> List[str]:
        """Extract items excluded from returns."""
        exclusions = []
        
        exclusion_patterns = [
            (r'final\s+sale', 'Final sale items'),
            (r'sale\s+items?\s+(are\s+)?not\s+returnable', 'Sale items'),
            (r'undergarments?', 'Undergarments'),
            (r'swimwear', 'Swimwear'),
            (r'intimate', 'Intimate items'),
            (r'personalized', 'Personalized items'),
            (r'customized', 'Customized items'),
            (r'gift\s+cards?', 'Gift cards'),
            (r'clearance', 'Clearance items'),
            (r'hygiene', 'Hygiene products'),
        ]
        
        for pattern, exclusion in exclusion_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                exclusions.append(exclusion)
        
        return list(set(exclusions))[:5]
    
    def extract_policy_links_from_footer(
        self,
        soup: BeautifulSoup,
        base_url: str
    ) -> dict:
        """
        Extract policy page links from footer.
        
        Many sites like Rastaclat have policy links in the footer:
        - /pages/return-policy
        - /policies/shipping-policy
        - /pages/faq
        
        Args:
            soup: Parsed HTML
            base_url: Base URL for making absolute URLs
            
        Returns:
            Dictionary with discovered policy URLs
        """
        from .url_utils import make_absolute_url
        
        policy_links = {
            'return_policy_url': None,
            'shipping_policy_url': None,
            'faq_url': None,
            'terms_url': None,
            'privacy_url': None,
        }
        
        # Look in footer first
        footer = soup.find('footer')
        search_area = footer if footer else soup
        
        # Find all links
        links = search_area.find_all('a', href=True)
        
        for link in links:
            href = link.get('href', '').lower()
            text = link.get_text(strip=True).lower()
            
            # Return/refund policy
            if any(kw in href or kw in text for kw in ['return', 'refund', 'exchange']):
                if 'policy' in href or 'policy' in text or '/pages/' in href:
                    policy_links['return_policy_url'] = make_absolute_url(base_url, link['href'])
            
            # Shipping policy
            if any(kw in href or kw in text for kw in ['shipping', 'delivery']):
                if 'policy' in href or 'policy' in text or '/pages/' in href or '/policies/' in href:
                    policy_links['shipping_policy_url'] = make_absolute_url(base_url, link['href'])
            
            # FAQ
            if 'faq' in href or 'faq' in text:
                policy_links['faq_url'] = make_absolute_url(base_url, link['href'])
            
            # Terms
            if 'terms' in href or 'terms' in text:
                policy_links['terms_url'] = make_absolute_url(base_url, link['href'])
            
            # Privacy
            if 'privacy' in href or 'privacy' in text:
                policy_links['privacy_url'] = make_absolute_url(base_url, link['href'])
        
        return policy_links


def extract_policies(
    soup: BeautifulSoup,
    page_text: str,
    page_type: str
) -> Tuple[Optional[ShippingPolicy], Optional[ReturnPolicy]]:
    """
    Extract policies from a page.
    
    Args:
        soup: Parsed HTML
        page_text: Raw text content
        page_type: Type of page ('shipping', 'return', 'policy', etc.)
        
    Returns:
        Tuple of (ShippingPolicy, ReturnPolicy) - either may be None
    """
    extractor = PolicyExtractor()
    
    shipping = None
    returns = None
    
    text_lower = page_text.lower()
    
    # Determine what to extract based on page type and content
    has_shipping_content = any(word in text_lower for word in [
        'shipping', 'delivery', 'ship', 'transit'
    ])
    has_return_content = any(word in text_lower for word in [
        'return', 'refund', 'exchange', 'money back'
    ])
    
    obs.event("policies", "success", kind="policy_page_classified", page_type=page_type,
              has_shipping_content=has_shipping_content, has_return_content=has_return_content)

    if has_shipping_content or page_type == 'shipping':
        shipping = extractor.extract_shipping_policy(soup, page_text)

    if has_return_content or page_type == 'return':
        returns = extractor.extract_return_policy(soup, page_text)

    return shipping, returns


def extract_policies_from_homepage_js(html_str: str) -> dict:
    """
    Extract shipping/return policies from embedded JavaScript on homepage.
    
    Many Shopify sites embed policy data in JS settings even when policy 
    pages are blocked by robots.txt. This function extracts that data.
    
    Args:
        html_str: Raw HTML string of homepage
        
    Returns:
        Dictionary with extracted policy data
    """
    result = {
        'free_shipping_threshold': None,
        'return_days': None,
        'free_returns': False,
        'has_free_shipping': False,
        'shipping_options': [],
    }
    
    html_lower = html_str.lower()
    
    # Pattern 1: "FREE SHIPPING & FREE RETURNS" in announcement bar
    if 'free shipping' in html_lower and 'free returns' in html_lower:
        result['free_returns'] = True
        result['has_free_shipping'] = True
        obs.note('free_returns', True, 'regex',
                 "homepage JS fallback pattern 1: 'free shipping' and 'free returns' both anywhere in raw html",
                 stage='policies')
        # If both are mentioned together without threshold, likely free on all orders
        if not re.search(r'free\s+shipping\s+(?:over|on\s+orders?\s+over)\s+\$?\d+', html_lower):
            result['free_shipping_threshold'] = 0
            obs.note('free_shipping_threshold', 0, 'regex',
                     "homepage JS fallback pattern 1: both phrases present and no 'over $N' -> 0 (free on all orders)",
                     stage='policies')
    
    # Pattern 2: Free shipping threshold from various patterns
    threshold_patterns = [
        r'free\s+shipping\s+(?:over|on\s+orders?\s+over)\s+\$?(\d+)',
        r'spend\s+\$(\d+).*?free\s+shipping',
        r'"freeShippingThreshold"\s*:\s*(\d+)',
        r'"free_shipping_threshold"\s*:\s*(\d+)',
    ]
    
    for pattern in threshold_patterns:
        match = re.search(pattern, html_str, re.I)
        if match:
            result['free_shipping_threshold'] = float(match.group(1))
            result['has_free_shipping'] = True
            obs.note('free_shipping_threshold', float(match.group(1)), 'regex',
                     f"homepage JS fallback threshold_patterns[{threshold_patterns.index(pattern)}] "
                     f"matched {match.group(0)[:80]!r} in raw html", stage='policies')
            break
    
    # Pattern 3: Return days from embedded text or JSON
    return_patterns = [
        r'(?:refund|return).*?within\s+(\d+)\s+days',
        r'(\d+)\s*[-–]?\s*day\s+return',
        r'"returnDays"\s*:\s*(\d+)',
        r'"return_window"\s*:\s*(\d+)',
        r'sddReturnsInfo.*?(\d+)\s+days',
    ]
    
    for pattern in return_patterns:
        match = re.search(pattern, html_str, re.I)
        if match:
            result['return_days'] = int(match.group(1))
            obs.note('return_days', int(match.group(1)), 'regex',
                     f"homepage JS fallback return_patterns[{return_patterns.index(pattern)}] "
                     f"matched {match.group(0)[:120]!r} in raw html", stage='policies')
            break
    
    # Pattern 4: Shipping options from Shopify JSON
    shipping_options_match = re.search(
        r'"sddShippingOptions"\s*:\s*(\{[^}]+(?:\{[^}]*\}[^}]*)*\})',
        html_str
    )
    if shipping_options_match:
        try:
            import json
            options_str = shipping_options_match.group(1)
            # Try to extract key info without full JSON parsing
            if 'FREE Standard Shipping' in options_str or 'free' in options_str.lower():
                result['has_free_shipping'] = True
                if result['free_shipping_threshold'] is None:
                    result['free_shipping_threshold'] = 0
                    obs.note('free_shipping_threshold', 0, 'regex',
                             "homepage JS fallback: sddShippingOptions mentions 'free' -> 0", stage='policies')
        except:
            obs.swallowed("policy_extractor.py:extract_policies_from_homepage_js", error_type="parse",
                          fallback="ignore sddShippingOptions", stage="policies")
    
    # Pattern 5: Returns info from Shopify settings
    returns_info_match = re.search(
        r'"sddReturnsInfo"\s*:\s*"([^"]+)"',
        html_str
    )
    if returns_info_match:
        returns_text = returns_info_match.group(1)
        if 'free' in returns_text.lower():
            result['free_returns'] = True
            obs.note('free_returns', True, 'regex', "homepage JS fallback: sddReturnsInfo mentions 'free'",
                     stage='policies')
        days_match = re.search(r'(\d+)\s+days', returns_text)
        if days_match and result['return_days'] is None:
            result['return_days'] = int(days_match.group(1))
            obs.note('return_days', int(days_match.group(1)), 'regex', "homepage JS fallback: sddReturnsInfo",
                     stage='policies')
    
    # Pattern 6: Check for messaging JSON (common in Shopify)
    messaging_match = re.search(
        r'"returnsMessaging"\s*:\s*\{[^}]*"(?:pdp|cart)"\s*:\s*"([^"]+)"',
        html_str
    )
    if messaging_match:
        msg = messaging_match.group(1).lower()
        if 'free return' in msg:
            result['free_returns'] = True
            obs.note('free_returns', True, 'regex', "homepage JS fallback: returnsMessaging mentions 'free return'",
                     stage='policies')
        if 'free shipping' in msg:
            result['has_free_shipping'] = True
    
    return result
