"""
trust_extractor.py - Extract trust and conversion signals from e-commerce pages.

Detects:
- Review platforms and counts
- Trust badges and security seals
- Payment methods
- Guarantees and warranties
"""

import copy
import re
import logging
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup

from .models import TrustSignal
from . import obs

logger = logging.getLogger(__name__)


class TrustExtractor:
    """
    Extracts trust signals and social proof elements from pages.
    """
    
    # Review platform patterns - expanded
    REVIEW_PLATFORMS = {
        'Judge.me': ['judge.me', 'jdgm-', 'jdgm.', 'judgeme'],
        'Yotpo': ['yotpo', 'yotpo-', 'staticw2.yotpo'],
        'Stamped.io': ['stamped.io', 'stamped-', 'stamped.'],
        'Loox': ['loox.io', 'loox-', 'loox.'],
        'Okendo': ['okendo.io', 'okendo-', 'okendo.'],
        'Shopify Reviews': ['spr-', 'shopify-product-reviews', 'spr.'],
        'Trustpilot': ['trustpilot', 'trustpilot.com'],
        'Reviews.io': ['reviews.io', 'reviewsio'],
        'Bazaarvoice': ['bazaarvoice', 'bv-', 'bazaarvoice.com'],
        'PowerReviews': ['powerreviews', 'power-reviews'],
        'Google Reviews': ['google-reviews', 'g-reviews', 'google.com/reviews'],
        'Fera': ['fera.ai', 'fera-', 'ferareviews'],
        'Junip': ['junip.co', 'junip-'],
        'Ali Reviews': ['alireviews', 'ali-reviews'],
        'Ryviu': ['ryviu', 'ryviu.com'],
        'Opinew': ['opinew', 'opinew.com'],
        'Rivyo': ['rivyo', 'rivyo.com'],
    }
    
    # Payment method patterns (regexes, matched as whole words against html + visible text).
    # Card brands are reported by name; 'Discover' only from payment icons, since the word
    # is common page copy ("Discover our collection").
    PAYMENT_METHODS = {
        'Shop Pay': [r'\bshop[ -]?pay\b', r'\bshopify pay\b'],
        'PayPal': [r'\bpaypal\b'],
        'Apple Pay': [r'\bapple[ -]?pay\b'],
        'Google Pay': [r'\bgoogle[ -]?pay\b', r'\bgpay\b'],
        'Amazon Pay': [r'\bamazon[ -]?pay\b'],
        'Klarna': [r'\bklarna\b'],
        'Afterpay': [r'\bafterpay\b'],
        'Affirm': [r'\baffirm\b'],
        'Sezzle': [r'\bsezzle\b'],
        'Zip': [r'\bzip[ -]?pay\b', r'\bquadpay\b'],
        'Visa': [r'\bvisa\b'],
        'Mastercard': [r'\bmaster[ -]?card\b', r'\bpi-master\b'],
        'American Express': [r'\bamerican[ _-]?express\b', r'\bamex\b'],
        'Discover': [r'\bpi-discover\b'],
        'Venmo': [r'\bvenmo\b'],
        'Clearpay': [r'\bclearpay\b'],
    }
    CARD_BRANDS = ('Visa', 'Mastercard', 'American Express', 'Discover')
    GENERIC_CARD_PATTERNS = [r'\bcredit cards?\b', r'\bdebit cards?\b', r'\bcard payments?\b']
    
    # Trust badge patterns
    TRUST_BADGES = {
        'Secure Checkout': ['secure checkout', 'ssl', 'https', '256-bit', 'encrypted'],
        'Money Back Guarantee': ['money back', 'satisfaction guarantee', 'guaranteed'],
        'Free Shipping': ['free shipping'],
        'Easy Returns': ['easy returns', 'hassle-free returns', 'free returns'],
        'Verified Reviews': ['verified reviews', 'verified buyer', 'verified purchase'],
        'BBB Accredited': ['bbb', 'better business bureau'],
        'McAfee Secure': ['mcafee', 'mcafee secure'],
        'Norton Secured': ['norton', 'symantec'],
        'Trustwave': ['trustwave'],
        'TrustedSite': ['trustedsite', 'mcafee secure'],
    }
    
    def extract_trust_signals(
        self,
        soup: BeautifulSoup,
        html_str: str
    ) -> Dict:
        """
        Extract all trust signals from a page.
        
        Args:
            soup: Parsed HTML
            html_str: Raw HTML string
            
        Returns:
            Dictionary with trust signal data
        """
        result = {
            'trust_signals': [],
            'review_platform': '',
            'total_reviews': None,
            'payment_methods': [],
        }
        
        # Detect review platform
        platform, reviews = self._detect_review_platform(soup, html_str)
        result['review_platform'] = platform
        result['total_reviews'] = reviews
        
        if platform:
            result['trust_signals'].append(TrustSignal(
                signal_type='reviews',
                name=platform,
                details=f"{reviews} reviews" if reviews else "Reviews present"
            ))
        
        # Detect payment methods
        result['payment_methods'] = self._detect_payment_methods(soup, html_str)
        
        for method in result['payment_methods']:
            result['trust_signals'].append(TrustSignal(
                signal_type='payment_method',
                name=method
            ))
        
        # Detect trust badges
        badges = self._detect_trust_badges(soup, html_str)
        result['trust_signals'].extend(badges)
        
        # Detect guarantees
        guarantees = self._detect_guarantees(soup)
        result['trust_signals'].extend(guarantees)
        
        return result
    
    def _detect_review_platform(
        self,
        soup: BeautifulSoup,
        html_str: str
    ) -> Tuple[str, Optional[int]]:
        """Detect review platform and extract review count."""
        import json
        
        html_lower = html_str.lower()
        
        platform = ''
        review_count = None
        
        for name, patterns in self.REVIEW_PLATFORMS.items():
            for pattern in patterns:
                if pattern in html_lower:
                    platform = name
                    obs.note('review_platform', name, 'regex',
                             f"REVIEW_PLATFORMS[{name!r}] substring {pattern!r} in raw html",
                             snippet=obs.snippet(html_str, pattern))
                    break
            if platform:
                break
        
        # Method 1: Parse Judge.me settings JSON (like Rastaclat)
        # Pattern: window.jdgmSettings = {...}
        # Contains: "widget_title":"Join 1,000,000+ Others With Bracelets on Wrist!"
        if 'judge.me' in html_lower or 'jdgm' in html_lower:
            platform = 'Judge.me'
            obs.note('review_platform', 'Judge.me', 'regex', "substring 'judge.me' or 'jdgm' in raw html (overrides)")
            # Try to extract review count from jdgm settings
            jdgm_match = re.search(r'window\.jdgmSettings\s*=\s*({[^;]+});', html_str)
            if jdgm_match:
                try:
                    settings = json.loads(jdgm_match.group(1))
                    # Look for widget_title with review count
                    title = settings.get('widget_title', '')
                    count_match = re.search(r'([\d,]+)\+?\s*(others|reviews|customers)', title, re.I)
                    if count_match:
                        review_count = int(count_match.group(1).replace(',', ''))
                        obs.note('review_count', review_count, 'json',
                                 f"window.jdgmSettings.widget_title {title!r}")
                except:
                    obs.swallowed("trust_extractor.py:_detect_review_platform", error_type="parse",
                                  fallback="review_count unchanged", stage="trust")
        
        # Method 2: Standard count patterns in text
        count_patterns = [
            r'(\d{1,3}(?:,\d{3})*)\+?\s*reviews?',
            r'reviews?\s*\((\d{1,3}(?:,\d{3})*)\)',
            r'based\s+on\s+(\d{1,3}(?:,\d{3})*)\s+reviews?',
            r'(\d{1,3}(?:,\d{3})*)\s+verified\s+reviews?',
            r'rating[^<]*(\d{1,3}(?:,\d{3})*)\s+reviews?',
            r'join\s+(\d{1,3}(?:,\d{3})*)\+?\s*(others|customers)',
        ]
        
        if not review_count:
            text = soup.get_text().lower()
            for pattern in count_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    count_str = match.group(1).replace(',', '')
                    count = int(count_str)
                    if count > 0 and count < 10000000:  # Sanity check
                        review_count = count
                        obs.note('review_count', count, 'regex',
                                 f"count_patterns[{count_patterns.index(pattern)}] matched {match.group(0)!r} in page text")
                        break
        
        # Method 3: Check for data attributes
        review_elements = soup.select('[data-review-count], [data-reviews], [data-number-of-reviews]')
        for elem in review_elements:
            for attr in ['data-review-count', 'data-reviews', 'data-number-of-reviews']:
                val = elem.get(attr)
                if val and val.replace(',', '').isdigit():
                    review_count = int(val.replace(',', ''))
                    obs.note('review_count', review_count, 'selector', f"[{attr}] on <{elem.name}>")
                    break
        
        # Method 4: Check script tags for jdgmSettings class
        for script in soup.select('script.jdgm-settings-script, script[class*="jdgm"]'):
            if script.string:
                platform = 'Judge.me'
                obs.note('review_platform', 'Judge.me', 'selector', "script.jdgm-settings-script / script[class*=jdgm]")
                break
        
        return platform, review_count
    
    def _detect_payment_methods(
        self,
        soup: BeautifulSoup,
        html_str: str
    ) -> List[str]:
        """Detect accepted payment methods."""
        import json
        
        methods = []
        html_lower = html_str.lower()
        text = soup.get_text().lower()
        
        # Check both HTML and visible text. The PayPal metadata's Venmo flag is read below as a flag;
        # its attribute name alone ('data-venmo-supported="false"') does not name Venmo as accepted.
        # Brand words are matched in tags, attributes and visible text, not inside <script> / <style>
        # bodies (CSS for card icons, analytics referrer lists); the Apple Pay JSON and the PayPal
        # metadata are read by their own rules below.
        markup = copy.copy(soup)
        for tag in markup(['script', 'style', 'noscript', 'template']):
            tag.decompose()
        combined = re.sub(r'data-venmo-supported\s*=\s*["\'][^"\']*["\']', ' ', str(markup).lower() + ' ' + text)
        
        payment_evidence = {}
        for method, patterns in self.PAYMENT_METHODS.items():
            for pattern in patterns:
                match = re.search(pattern, combined)
                if match:
                    methods.append(method)
                    payment_evidence[method] = f"PAYMENT_METHODS {pattern!r} matched {match.group(0)!r} " \
                        f"({obs.snippet(combined, match.group(0), 25)!r})"
                    break
        
        # Method 1: Parse Shopify Apple Pay capabilities JSON (like Rastaclat)
        # Pattern: <script id="apple-pay-shop-capabilities" type="application/json">
        # Contains: "supportedNetworks":["visa","masterCard","amex","discover","elo","jcb"]
        apple_pay_script = soup.select_one('script#apple-pay-shop-capabilities')
        if apple_pay_script and apple_pay_script.string:
            try:
                data = json.loads(apple_pay_script.string)
                supported = data.get('supportedNetworks', [])
                if supported:
                    if 'Apple Pay' not in methods:
                        methods.append('Apple Pay')
                    # Map network names to payment methods
                    network_map = {
                        'visa': 'Visa',
                        'mastercard': 'Mastercard',
                        'masterCard': 'Mastercard',
                        'amex': 'American Express',
                        'discover': 'Discover',
                        'jcb': 'JCB',
                        'elo': 'Elo',
                    }
                    for network in supported:
                        mapped = network_map.get(network.lower(), network_map.get(network))
                        if mapped and mapped not in methods:
                            methods.append(mapped)
                            payment_evidence[mapped] = "script#apple-pay-shop-capabilities supportedNetworks"
                if data.get('shopifyPaymentsEnabled'):
                    if 'Shop Pay' not in methods:
                        methods.append('Shop Pay')
                        payment_evidence['Shop Pay'] = "apple-pay-shop-capabilities shopifyPaymentsEnabled"
            except:
                obs.swallowed("trust_extractor.py:_detect_payment_methods", error_type="parse",
                              fallback="apple pay JSON ignored", stage="trust")
        
        # Method 2: Detect PayPal from meta tag (like Rastaclat)
        # Pattern: <meta id="in-context-paypal-metadata" ...>
        paypal_meta = soup.select_one('meta#in-context-paypal-metadata, meta[id*="paypal"]')
        if paypal_meta:
            if 'PayPal' not in methods:
                methods.append('PayPal')
                payment_evidence['PayPal'] = "meta#in-context-paypal-metadata / meta[id*=paypal]"
            # Check for Venmo support
            if paypal_meta.get('data-venmo-supported') == 'true':
                if 'Venmo' not in methods:
                    methods.append('Venmo')
                    payment_evidence['Venmo'] = 'meta#in-context-paypal-metadata data-venmo-supported="true"'

        # Wallets declared in <link rel="buy" payment="dev.shopify.shop_pay com.google.pay ...">
        wallet_tokens = {'com.google.pay': 'Google Pay', 'dev.shopify.shop_pay': 'Shop Pay',
                         'com.apple.pay': 'Apple Pay'}
        for link in soup.select('link[rel~="buy"][payment]'):
            for token in link.get('payment', '').split():
                mapped = wallet_tokens.get(token.lower())
                if mapped and mapped not in methods:
                    methods.append(mapped)
                    payment_evidence[mapped] = f'<link rel="buy" payment> token {token!r}'
        
        # Method 3: payment icons (alt text or file name); here a bare 'discover' is a card brand
        payment_icons = soup.select('img[alt*="pay" i], img[src*="payment"], .payment-icons img, '
                                    '.list-payment img, [class*="payment"] img')
        icon_patterns = dict(self.PAYMENT_METHODS, Discover=[r'\bdiscover\b'])
        for icon in payment_icons:
            label = f"{icon.get('alt', '')} {icon.get('src', '').rsplit('/', 1)[-1]}".lower()
            for method, patterns in icon_patterns.items():
                if method not in methods and any(re.search(pt, label) for pt in patterns):
                    methods.append(method)
                    payment_evidence[method] = f"payment icon img alt/src {label[:60]!r}"

        # Method 4: Check for Shopify dynamic checkout scripts
        if 'shopify.paymentbutton' in html_lower or 'portable-wallets' in html_lower:
            if 'Shop Pay' not in methods:
                methods.append('Shop Pay')
                payment_evidence['Shop Pay'] = "substring 'shopify.paymentbutton' or 'portable-wallets'"

        # Generic 'Credit Card' only when cards are mentioned and no brand is named
        if not any(m in self.CARD_BRANDS for m in methods):
            for pattern in self.GENERIC_CARD_PATTERNS:
                match = re.search(pattern, combined)
                if match:
                    methods.append('Credit Card')
                    payment_evidence['Credit Card'] = f"no card brand named; {pattern!r} matched {match.group(0)!r}"
                    break

        methods_out = sorted(set(methods))
        obs.note('payment_methods', methods_out, 'regex' if methods_out else 'default',
                 '; '.join(f"{k}: {v}" for k, v in payment_evidence.items()) or "no payment pattern matched")
        return methods_out
    
    def _detect_trust_badges(
        self,
        soup: BeautifulSoup,
        html_str: str
    ) -> List[TrustSignal]:
        """Detect trust badges and security seals."""
        badges = []
        html_lower = html_str.lower()
        text = soup.get_text().lower()
        
        for badge, patterns in self.TRUST_BADGES.items():
            for pattern in patterns:
                if pattern in html_lower or pattern in text:
                    badges.append(TrustSignal(
                        signal_type='badge',
                        name=badge
                    ))
                    break
        
        # Check for badge images
        badge_images = soup.select(
            'img[alt*="secure"], img[alt*="trust"], img[alt*="verified"], '
            'img[alt*="guarantee"], img[src*="badge"], img[src*="trust"]'
        )
        
        for img in badge_images:
            alt = img.get('alt', '')
            if alt and len(alt) > 3:
                # Check if we already have this
                if not any(s.name.lower() == alt.lower() for s in badges):
                    badges.append(TrustSignal(
                        signal_type='badge',
                        name=alt[:50]
                    ))
        
        return badges[:10]  # Limit to 10 badges
    
    def _detect_guarantees(self, soup: BeautifulSoup) -> List[TrustSignal]:
        """Detect guarantee and warranty mentions."""
        guarantees = []
        text = soup.get_text().lower()
        
        guarantee_patterns = [
            (r'(\d+)[- ]?(year|month|day)\s+warranty', 'Warranty'),
            (r'lifetime\s+warranty', 'Lifetime Warranty'),
            (r'(\d+)[- ]?day\s+money[- ]?back\s+guarantee', 'Money Back Guarantee'),
            (r'satisfaction\s+guarantee', 'Satisfaction Guarantee'),
            (r'price\s+match\s+guarantee', 'Price Match Guarantee'),
            (r'lowest\s+price\s+guarantee', 'Lowest Price Guarantee'),
            (r'authenticity\s+guarantee', 'Authenticity Guarantee'),
        ]
        
        for pattern, name in guarantee_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                detail = match.group(0)
                guarantees.append(TrustSignal(
                    signal_type='guarantee',
                    name=name,
                    details=detail
                ))
        
        return guarantees


def detect_payment_methods(soup: BeautifulSoup, html_str: str) -> List[str]:
    """Payment methods named or declared on one page (used for product pages)."""
    return TrustExtractor()._detect_payment_methods(soup, html_str)


def extract_trust_signals(
    soup: BeautifulSoup,
    html_str: str
) -> Dict:
    """
    Convenience function for trust signal extraction.
    
    Args:
        soup: Parsed HTML
        html_str: Raw HTML string
        
    Returns:
        Dictionary with trust signal data
    """
    extractor = TrustExtractor()
    return extractor.extract_trust_signals(soup, html_str)
