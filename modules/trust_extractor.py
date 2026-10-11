"""
trust_extractor.py - Extract trust and conversion signals from e-commerce pages.

Detects:
- Review platforms and counts
- Trust badges and security seals
- Payment methods
- Guarantees and warranties
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup

from .models import TrustSignal

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
    
    # Payment method patterns
    PAYMENT_METHODS = {
        'Shop Pay': ['shop pay', 'shopify pay', 'shop-pay'],
        'PayPal': ['paypal'],
        'Apple Pay': ['apple pay', 'applepay'],
        'Google Pay': ['google pay', 'googlepay', 'gpay'],
        'Amazon Pay': ['amazon pay', 'amazonpay'],
        'Klarna': ['klarna'],
        'Afterpay': ['afterpay'],
        'Affirm': ['affirm'],
        'Sezzle': ['sezzle'],
        'Zip': ['zip pay', 'quadpay'],
        'Credit Card': ['visa', 'mastercard', 'amex', 'american express', 'discover'],
        'Venmo': ['venmo'],
        'Clearpay': ['clearpay'],
    }
    
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
                    break
            if platform:
                break
        
        # Method 1: Parse Judge.me settings JSON (like Rastaclat)
        # Pattern: window.jdgmSettings = {...}
        # Contains: "widget_title":"Join 1,000,000+ Others With Bracelets on Wrist!"
        if 'judge.me' in html_lower or 'jdgm' in html_lower:
            platform = 'Judge.me'
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
                except:
                    pass
        
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
                        break
        
        # Method 3: Check for data attributes
        review_elements = soup.select('[data-review-count], [data-reviews], [data-number-of-reviews]')
        for elem in review_elements:
            for attr in ['data-review-count', 'data-reviews', 'data-number-of-reviews']:
                val = elem.get(attr)
                if val and val.replace(',', '').isdigit():
                    review_count = int(val.replace(',', ''))
                    break
        
        # Method 4: Check script tags for jdgmSettings class
        for script in soup.select('script.jdgm-settings-script, script[class*="jdgm"]'):
            if script.string:
                platform = 'Judge.me'
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
        
        # Check both HTML and visible text
        combined = html_lower + ' ' + text
        
        for method, patterns in self.PAYMENT_METHODS.items():
            for pattern in patterns:
                if pattern in combined:
                    methods.append(method)
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
                    }
                    for network in supported:
                        mapped = network_map.get(network.lower(), network_map.get(network))
                        if mapped and mapped not in methods:
                            methods.append(mapped)
                if data.get('shopifyPaymentsEnabled'):
                    if 'Shop Pay' not in methods:
                        methods.append('Shop Pay')
            except:
                pass
        
        # Method 2: Detect PayPal from meta tag (like Rastaclat)
        # Pattern: <meta id="in-context-paypal-metadata" ...>
        paypal_meta = soup.select_one('meta#in-context-paypal-metadata, meta[id*="paypal"]')
        if paypal_meta:
            if 'PayPal' not in methods:
                methods.append('PayPal')
            # Check for Venmo support
            if paypal_meta.get('data-venmo-supported') == 'true':
                if 'Venmo' not in methods:
                    methods.append('Venmo')
        
        # Method 3: Also check for payment icons
        payment_icons = soup.select('img[alt*="pay"], img[src*="payment"], .payment-icons img')
        for icon in payment_icons:
            alt = icon.get('alt', '').lower()
            src = icon.get('src', '').lower()
            
            for method, patterns in self.PAYMENT_METHODS.items():
                if method not in methods:
                    for pattern in patterns:
                        if pattern in alt or pattern in src:
                            methods.append(method)
                            break
        
        # Method 4: Check for Shopify dynamic checkout scripts
        if 'shopify.paymentbutton' in html_lower or 'portable-wallets' in html_lower:
            if 'Shop Pay' not in methods:
                methods.append('Shop Pay')
        
        return list(set(methods))
    
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
