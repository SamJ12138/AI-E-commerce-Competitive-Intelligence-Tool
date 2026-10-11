"""
promo_extractor.py - Extract promotions and marketing tactics from e-commerce pages.

Detects:
- Announcement bars and sitewide sales
- Popup/email capture forms
- Free shipping offers
- Loyalty/referral programs
- Social media embeds
- Analytics pixels
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup

from .models import Promotion, AnalyticsPixel
from . import obs

logger = logging.getLogger(__name__)


class PromoExtractor:
    """
    Extracts promotional elements and marketing tactics from pages.
    """
    
    # Patterns for announcement bar detection - expanded for modern themes
    ANNOUNCEMENT_SELECTORS = [
        # Standard announcement bars
        '.announcement-bar',
        '.announcement',
        '#announcement',
        '.topbar',
        '.top-bar',
        '.promo-bar',
        '.promo-banner',
        '.site-header__announcement',
        '[data-section-type="announcement-bar"]',
        '.header-announcement',
        '.announcement-banner',
        '.marquee',
        '.ticker',
        # Shopify specific - including modern Impact/Dawn themes
        '#shopify-section-announcement-bar',
        '[id*="announcement"]',
        '[class*="announcement"]',
        '[class*="Announcement"]',
        '.utility-bar',
        '.header-bar',
        '.top-banner',
        '.site-banner',
        '.alert-bar',
        '.info-bar',
        '.notification-bar',
        # Common promo bar patterns
        '.free-shipping-bar',
        '.shipping-bar',
        '[class*="promo"]',
        '[class*="Promo"]',
        # Modern Shopify section patterns (like Rastaclat)
        '.shopify-section--announcement-bar',
        '[class*="shopify-section"][class*="announcement"]',
        'section[class*="announcement"]',
        # Marquee/ticker patterns for sliding announcements
        '.announcement-bar__content',
        '.announcement-bar__message',
        '.announcement__content',
    ]
    
    # Popup/modal selectors - expanded
    POPUP_SELECTORS = [
        '.popup',
        '.modal',
        '#popup',
        '#modal',
        '.email-popup',
        '.newsletter-popup',
        '.klaviyo-form',
        '.klaviyo-popup',
        '.privy-popup',
        '.omnisend-form',
        '.sumo-popup',
        '.wheelio',
        '[data-popup]',
        '.slide-in',
        '.exit-intent',
        # Additional modern patterns
        '[class*="popup"]',
        '[class*="Popup"]',
        '[class*="modal"]',
        '[class*="Modal"]',
        '.overlay-popup',
        '.lightbox',
        '.subscribe-popup',
        '[id*="popup"]',
        '[id*="modal"]',
    ]
    
    # Email capture selectors - expanded
    EMAIL_CAPTURE_SELECTORS = [
        '.newsletter',
        '.newsletter-form',
        '.email-signup',
        '.signup-form',
        'form[action*="subscribe"]',
        'input[name*="email"]',
        '.mailchimp',
        '.klaviyo',
        '.omnisend',
        # Additional patterns
        '[class*="newsletter"]',
        '[class*="Newsletter"]',
        '[class*="subscribe"]',
        '[class*="Subscribe"]',
        '[class*="signup"]',
        '[class*="SignUp"]',
        'form[class*="email"]',
        '.footer-newsletter',
        '.email-capture',
        '.mailing-list',
        'input[placeholder*="email"]',
        'input[placeholder*="Email"]',
    ]
    
    # Loyalty/referral indicators
    LOYALTY_KEYWORDS = [
        'rewards', 'loyalty', 'points', 'earn points',
        'vip', 'member', 'membership', 'loyalty program',
        'reward points', 'smile.io', 'yotpo loyalty'
    ]
    
    REFERRAL_KEYWORDS = [
        'refer a friend', 'referral', 'refer and earn',
        'give $', 'get $', 'refer & earn', 'share and earn'
    ]
    
    # Free shipping patterns - expanded with more variations
    FREE_SHIPPING_PATTERNS = [
        r'free\s+shipping\s+(on\s+)?orders?\s+over\s+\$?(\d+)',
        r'free\s+shipping\s+(on\s+)?all\s+orders',
        r'free\s+shipping\s+on\s+\$(\d+)\+',
        r'spend\s+\$(\d+).*free\s+shipping',
        r'free\s+standard\s+shipping',
        r'\$(\d+)\s+for\s+free\s+shipping',
        # Additional patterns found in sites like Rastaclat
        r'free\s+shipping\s+on\s+orders\s+\$(\d+)\+',
        r'free\s+shipping\s+\$(\d+)\+',
        r'orders\s+\$(\d+)\+?\s+(get\s+)?free\s+shipping',
        r'free\s+shipping\s+over\s+\$(\d+)',
        r'complimentary\s+shipping\s+(on\s+)?orders?\s+(over\s+)?\$?(\d+)',
    ]
    
    # Discount patterns
    DISCOUNT_PATTERNS = [
        r'(\d+)%\s*off',
        r'save\s+(\d+)%',
        r'up\s+to\s+(\d+)%\s+off',
        r'\$(\d+)\s+off',
        r'code:?\s*([A-Z0-9]+)',
        r'use\s+code\s+([A-Z0-9]+)',
    ]
    
    def extract_promotions(
        self,
        soup: BeautifulSoup,
        html_str: str
    ) -> Dict:
        """
        Extract all promotional elements from a page.
        
        Args:
            soup: Parsed HTML
            html_str: Raw HTML string for pattern matching
            
        Returns:
            Dictionary with promotional data
        """
        result = {
            'promotions': [],
            'announcement_bar_text': '',
            'has_popup': False,
            'has_email_capture': False,
            'has_loyalty_program': False,
            'has_referral_program': False,
            'free_shipping_threshold': None,
            'social_embeds': [],
            'pixels': [],
        }
        
        # Extract announcement bar
        announcement = self._extract_announcement_bar(soup)
        if announcement:
            result['announcement_bar_text'] = announcement
            result['promotions'].append(Promotion(
                promo_type='announcement_bar',
                description=announcement
            ))
        
        # Detect popups
        result['has_popup'] = self._detect_popup(soup, html_str)
        
        # Detect email capture
        result['has_email_capture'] = self._detect_email_capture(soup)
        
        # Detect loyalty program
        result['has_loyalty_program'] = self._detect_loyalty(soup, html_str)
        
        # Detect referral program
        result['has_referral_program'] = self._detect_referral(soup, html_str)
        
        # Extract free shipping info
        threshold, promo = self._extract_free_shipping(soup, html_str)
        result['free_shipping_threshold'] = threshold
        if promo:
            result['promotions'].append(promo)
        
        # Extract discount codes/offers
        discounts = self._extract_discounts(soup, html_str)
        result['promotions'].extend(discounts)
        
        # Detect social embeds
        result['social_embeds'] = self._detect_social_embeds(soup, html_str)
        
        # Detect analytics pixels
        result['pixels'] = self._detect_pixels(html_str)
        
        return result
    
    def _extract_announcement_bar(self, soup: BeautifulSoup) -> str:
        """Extract announcement bar text."""
        promo_indicators = [
            'free', 'ship', 'off', 'sale', 'save', 'code', 
            'discount', 'buy', 'get', '%', '$'
        ]
        
        # First, try the selectors in order of specificity
        for selector in self.ANNOUNCEMENT_SELECTORS:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                if text and len(text) > 5:
                    obs.note('announcement_bar', text[:500], 'selector',
                             f"ANNOUNCEMENT_SELECTORS {selector!r} -> <{elem.name} class={elem.get('class')}>")
                    return text[:500]  # Limit length
        
        # Try to find Shopify promo slider elements (like Rastaclat)
        # Pattern: class="promo-slide-xxx" containing promotional text
        promo_slides = soup.find_all(
            lambda tag: tag.get('class') and any('promo' in c.lower() for c in tag.get('class', []))
        )
        for slide in promo_slides:
            # Look for text content in p, strong, span tags
            content_tags = slide.find_all(['p', 'strong', 'span', 'a'])
            for tag in content_tags:
                text = tag.get_text(strip=True)
                if text and len(text) > 5 and len(text) < 300:
                    if any(indicator in text.lower() for indicator in promo_indicators):
                        obs.note('announcement_bar', text[:500], 'selector',
                                 f"element whose class contains 'promo': <{slide.name} class={slide.get('class')}>")
                        return text[:500]
        
        # Try to find Shopify section containers with announcement in the ID
        # Pattern like: id="shopify-section-sections--19748372152519__announcement-bar"
        announcement_sections = soup.find_all(
            lambda tag: tag.get('id') and 'announcement' in tag.get('id', '').lower()
        )
        for section in announcement_sections:
            # Look for the actual content - often in a <p> or <a> tag
            content_tags = section.find_all(['p', 'a', 'span', 'div'])
            for tag in content_tags:
                text = tag.get_text(strip=True)
                if text and len(text) > 5 and len(text) < 300:
                    # Check if it looks like promotional content
                    if any(indicator in text.lower() for indicator in promo_indicators):
                        obs.note('announcement_bar', text[:500], 'selector',
                                 f"element whose id contains 'announcement': id={section.get('id')!r}")
                        return text[:500]
        
        # Also check for fixed top elements
        header = soup.find('header')
        if header:
            first_child = header.find()
            if first_child and first_child.name in ('div', 'p', 'span'):
                text = first_child.get_text(strip=True)
                if text and len(text) > 10 and len(text) < 200:
                    # Check if it looks like a promo
                    if any(word in text.lower() for word in promo_indicators):
                        obs.note('announcement_bar', text, 'selector', "first child element of <header>")
                        return text
        
        # Check for marquee/ticker elements which often contain promotions
        marquee_selectors = ['.marquee', '.ticker', '.scrolling-text', '[class*="marquee"]']
        for selector in marquee_selectors:
            marquee = soup.select_one(selector)
            if marquee:
                text = marquee.get_text(strip=True)
                if text and len(text) > 5:
                    obs.note('announcement_bar', text[:500], 'selector', f"marquee selector {selector!r}")
                    return text[:500]

        obs.note('announcement_bar', '', 'default', "no announcement selector matched")
        return ''
    
    def _detect_popup(self, soup: BeautifulSoup, html_str: str) -> bool:
        """Detect if page has popup/modal elements."""
        # Check for popup elements
        for selector in self.POPUP_SELECTORS:
            if soup.select_one(selector):
                elem = soup.select_one(selector)
                obs.note('has_popup', True, 'selector',
                         f"POPUP_SELECTORS {selector!r} -> <{elem.name} class={elem.get('class')} id={elem.get('id')}>")
                return True

        # Check for common popup libraries in scripts
        popup_libs = [
            'klaviyo', 'privy', 'justuno', 'wheelio', 'optinmonster',
            'sumo', 'wisepops', 'sleeknote', 'omniconvert'
        ]
        for lib in popup_libs:
            if lib in html_str.lower():
                obs.note('has_popup', True, 'regex', f"popup library substring {lib!r} in raw html",
                         snippet=obs.snippet(html_str, lib))
                return True

        obs.note('has_popup', False, 'default', "no POPUP_SELECTORS or popup library substring matched")
        return False
    
    def _detect_email_capture(self, soup: BeautifulSoup) -> bool:
        """Detect email capture forms."""
        for selector in self.EMAIL_CAPTURE_SELECTORS:
            if soup.select_one(selector):
                elem = soup.select_one(selector)
                obs.note('has_email_capture', True, 'selector',
                         f"EMAIL_CAPTURE_SELECTORS {selector!r} -> <{elem.name} class={elem.get('class')} id={elem.get('id')}>")
                return True

        # Check for email input fields
        email_inputs = soup.find_all('input', {'type': 'email'})
        if email_inputs:
            obs.note('has_email_capture', True, 'selector', "input[type=email]")
            return True

        # Check for newsletter-related text near forms
        forms = soup.find_all('form')
        for form in forms:
            text = form.get_text().lower()
            if any(word in text for word in ['newsletter', 'subscribe', 'signup', 'join']):
                obs.note('has_email_capture', True, 'regex', "form text contains newsletter/subscribe/signup/join")
                return True

        obs.note('has_email_capture', False, 'default', "no email capture selector, email input or form keyword")
        return False
    
    def _detect_loyalty(self, soup: BeautifulSoup, html_str: str) -> bool:
        """Detect loyalty program indicators."""
        text_lower = soup.get_text().lower()

        for keyword in self.LOYALTY_KEYWORDS:
            if keyword in text_lower:
                obs.note('has_loyalty', True, 'regex', f"LOYALTY_KEYWORDS substring {keyword!r} in page text",
                         snippet=obs.snippet(text_lower, keyword))
                return True

        # Check for loyalty platform scripts
        loyalty_platforms = ['smile.io', 'yotpo', 'loyaltylion', 'stamped.io/widget/loyalty']
        for platform in loyalty_platforms:
            if platform in html_str.lower():
                obs.note('has_loyalty', True, 'regex', f"loyalty platform substring {platform!r} in raw html",
                         snippet=obs.snippet(html_str, platform))
                return True

        obs.note('has_loyalty', False, 'default', "no LOYALTY_KEYWORDS or loyalty platform substring")
        return False
    
    def _detect_referral(self, soup: BeautifulSoup, html_str: str) -> bool:
        """Detect referral program indicators."""
        text_lower = soup.get_text().lower()

        for keyword in self.REFERRAL_KEYWORDS:
            if keyword in text_lower:
                obs.note('has_referral', True, 'regex', f"REFERRAL_KEYWORDS substring {keyword!r} in page text",
                         snippet=obs.snippet(text_lower, keyword))
                return True

        # Check for referral platform scripts
        referral_platforms = ['referralcandy', 'friendbuy', 'talkable', 'extole']
        for platform in referral_platforms:
            if platform in html_str.lower():
                obs.note('has_referral', True, 'regex', f"referral platform substring {platform!r} in raw html",
                         snippet=obs.snippet(html_str, platform))
                return True

        obs.note('has_referral', False, 'default', "no REFERRAL_KEYWORDS or referral platform substring")
        return False
    
    def _extract_free_shipping(
        self,
        soup: BeautifulSoup,
        html_str: str
    ) -> Tuple[Optional[float], Optional[Promotion]]:
        """Extract free shipping threshold and create promotion."""
        text = soup.get_text().lower()
        
        for pattern in self.FREE_SHIPPING_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                threshold = None
                
                # Try to extract threshold amount from groups
                for group in groups:
                    if group:
                        # Remove commas and check if it's a number
                        cleaned = group.replace(',', '')
                        if cleaned.isdigit():
                            threshold = float(cleaned)
                            break
                
                # If no threshold found in groups, try to find number in full match
                if threshold is None:
                    full_match = match.group(0)
                    num_match = re.search(r'\$?([\d,]+)', full_match)
                    if num_match:
                        cleaned = num_match.group(1).replace(',', '')
                        if cleaned.isdigit():
                            threshold = float(cleaned)
                
                promo = Promotion(
                    promo_type='free_shipping',
                    description=match.group(0),
                    value=f"${threshold}" if threshold else "All orders"
                )

                obs.note('free_shipping_threshold', threshold, 'regex',
                         f"promo_extractor.FREE_SHIPPING_PATTERNS[{self.FREE_SHIPPING_PATTERNS.index(pattern)}] "
                         f"matched {match.group(0)!r} in page text")
                return threshold, promo
        
        return None, None
    
    def _extract_discounts(
        self,
        soup: BeautifulSoup,
        html_str: str
    ) -> List[Promotion]:
        """Extract discount offers and codes."""
        promotions: List[Promotion] = []
        text = soup.get_text()
        seen = set()
        
        for pattern in self.DISCOUNT_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                full_match = match.group(0)
                if full_match not in seen:
                    seen.add(full_match)
                    
                    # Determine type
                    if 'code' in full_match.lower():
                        promo_type = 'discount_code'
                    elif '%' in full_match:
                        promo_type = 'percentage_discount'
                    else:
                        promo_type = 'dollar_discount'
                    
                    promotions.append(Promotion(
                        promo_type=promo_type,
                        description=full_match,
                        value=match.group(1) if match.groups() else None
                    ))
        
        return promotions[:5]  # Limit to top 5
    
    def _detect_social_embeds(
        self,
        soup: BeautifulSoup,
        html_str: str
    ) -> List[str]:
        """Detect social media embeds and UGC."""
        embeds = []
        
        # Instagram
        if 'instagram' in html_str.lower() or soup.select_one('[data-instgrm-permalink]'):
            embeds.append('Instagram')
        
        # TikTok
        if 'tiktok' in html_str.lower():
            embeds.append('TikTok')
        
        # Facebook
        if 'facebook.com/plugins' in html_str or soup.select_one('.fb-page, .fb-like'):
            embeds.append('Facebook')
        
        # YouTube
        if 'youtube.com/embed' in html_str or soup.select_one('iframe[src*="youtube"]'):
            embeds.append('YouTube')
        
        # Pinterest
        if 'pinterest' in html_str.lower():
            embeds.append('Pinterest')
        
        # UGC platforms
        ugc_platforms = {
            'loox': 'Loox UGC',
            'stamped.io': 'Stamped UGC',
            'yotpo': 'Yotpo UGC',
            'okendo': 'Okendo UGC',
            'pixlee': 'Pixlee UGC',
            'bazaarvoice': 'Bazaarvoice',
        }
        
        for platform, name in ugc_platforms.items():
            if platform in html_str.lower():
                embeds.append(name)
        
        return list(set(embeds))
    
    def _detect_pixels(self, html_str: str) -> List[AnalyticsPixel]:
        """Detect analytics and tracking pixels."""
        pixels = []
        html_lower = html_str.lower()
        
        # Google Analytics
        ga_patterns = [
            r'google-analytics\.com/analytics',
            r'googletagmanager\.com',
            r'gtag\s*\(',
            r'ga\s*\(\s*[\'"]create',
            r'UA-\d+-\d+',
            r'G-[A-Z0-9]+',
        ]
        ga_detected = any(re.search(p, html_str, re.IGNORECASE) for p in ga_patterns)
        pixel_evidence = {}
        if ga_detected:
            ga_hit = next(p for p in ga_patterns if re.search(p, html_str, re.IGNORECASE))
            ga_text = re.search(ga_hit, html_str, re.IGNORECASE).group(0)
            pixel_evidence['Google Analytics'] = f"pattern {ga_hit!r} (IGNORECASE) matched {ga_text!r}: " \
                f"{obs.snippet(html_str, ga_text, 30)!r}"
        
        # Try to extract GA ID
        ga_id = None
        ga_match = re.search(r'(UA-\d+-\d+|G-[A-Z0-9]+)', html_str)
        if ga_match:
            ga_id = ga_match.group(1)
        
        pixels.append(AnalyticsPixel(
            name='Google Analytics',
            detected=ga_detected,
            identifier=ga_id
        ))
        
        # Meta (Facebook) Pixel
        meta_patterns = [
            r'facebook\.com/tr',
            r'fbq\s*\(',
            r'connect\.facebook\.net',
            r'pixel_id',
        ]
        meta_detected = any(re.search(p, html_str, re.IGNORECASE) for p in meta_patterns)
        if meta_detected:
            meta_hit = next(p for p in meta_patterns if re.search(p, html_str, re.IGNORECASE))
            pixel_evidence['Meta Pixel'] = f"pattern {meta_hit!r} matched {re.search(meta_hit, html_str, re.IGNORECASE).group(0)!r}"
        
        meta_id = None
        meta_match = re.search(r'fbq\s*\(\s*[\'"]init[\'"]\s*,\s*[\'"](\d+)[\'"]', html_str)
        if meta_match:
            meta_id = meta_match.group(1)
        
        pixels.append(AnalyticsPixel(
            name='Meta Pixel',
            detected=meta_detected,
            identifier=meta_id
        ))
        
        # TikTok Pixel
        tiktok_patterns = [
            r'analytics\.tiktok\.com',
            r'ttq\.',
            r'tiktok.*pixel',
        ]
        tiktok_detected = any(re.search(p, html_str, re.IGNORECASE) for p in tiktok_patterns)
        if tiktok_detected:
            tt_hit = next(p for p in tiktok_patterns if re.search(p, html_str, re.IGNORECASE))
            pixel_evidence['TikTok Pixel'] = f"pattern {tt_hit!r} matched {re.search(tt_hit, html_str, re.IGNORECASE).group(0)!r}"
        pixels.append(AnalyticsPixel(
            name='TikTok Pixel',
            detected=tiktok_detected
        ))
        
        # Pinterest Tag
        pinterest_detected = 'pintrk' in html_lower or 'pinterest.com/v3' in html_lower
        pixels.append(AnalyticsPixel(
            name='Pinterest Tag',
            detected=pinterest_detected
        ))
        
        # Snapchat Pixel
        snap_detected = 'sc-static.net/scevent' in html_lower or 'snaptr' in html_lower
        pixels.append(AnalyticsPixel(
            name='Snapchat Pixel',
            detected=snap_detected
        ))
        
        # Microsoft/Bing
        bing_detected = 'bat.bing.com' in html_lower or 'uetq' in html_lower
        pixels.append(AnalyticsPixel(
            name='Microsoft Ads',
            detected=bing_detected
        ))
        
        # Klaviyo
        klaviyo_detected = 'klaviyo' in html_lower
        pixels.append(AnalyticsPixel(
            name='Klaviyo',
            detected=klaviyo_detected
        ))

        for flag, name, needle in ((pinterest_detected, 'Pinterest Tag', 'pintrk|pinterest.com/v3'),
                                   (snap_detected, 'Snapchat Pixel', 'sc-static.net/scevent|snaptr'),
                                   (bing_detected, 'Microsoft Ads', 'bat.bing.com|uetq'),
                                   (klaviyo_detected, 'Klaviyo', 'klaviyo')):
            if flag:
                pixel_evidence[name] = f"substring {needle!r} in raw html"
        detected_names = [p.name for p in pixels if p.detected]
        obs.note('pixels_detected', detected_names, 'regex' if detected_names else 'default',
                 '; '.join(f"{k}: {v}" for k, v in pixel_evidence.items()) or "no pixel pattern matched")
        return pixels


def extract_promotions(
    soup: BeautifulSoup,
    html_str: str
) -> Dict:
    """
    Convenience function for promotion extraction.
    
    Args:
        soup: Parsed HTML
        html_str: Raw HTML string
        
    Returns:
        Dictionary with promotional data
    """
    extractor = PromoExtractor()
    return extractor.extract_promotions(soup, html_str)
