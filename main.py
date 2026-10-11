#!/usr/bin/env python3
"""
main.py - E-commerce Competitive Intelligence Tool

A production-quality tool for analyzing independent e-commerce sites (Shopify, DTC)
to generate actionable intelligence for Chinese merchants selling cross-border.

Usage:
    python main.py --sites sites.txt
    python main.py --sites sites.txt --monitor
    python main.py --sites sites.txt --render-js --ignore-robots

Example sites:
    https://rastaclat.com
    https://pfrankmd.com
    https://allbirds.com
"""

import sys
import re
import logging
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

import click
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.logging import RichHandler

# Import our modules
from modules import (
    Config, Platform, SiteIntelligence, ChangeReport,
    HttpClient, RobotsChecker, SnapshotStore, ReportWriter,
    normalize_url, extract_domain, deduplicate_urls,
    detect_platform, discover_pages,
    extract_products, calculate_price_stats,
    extract_prices_from_js, extract_price_stats_from_html,
    extract_promotions, extract_policies, extract_policies_from_homepage_js,
    extract_trust_signals,
    extract_categories as extract_categories_module,
    PolicyExtractor,
)

# Setup rich console for pretty output
console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)]
    )


def load_config(config_path: Optional[str]) -> Dict:
    """Load configuration from YAML file if provided."""
    if config_path and Path(config_path).exists():
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}


def load_sites(sites_file: str) -> List[str]:
    """
    Load and validate site URLs from file.
    
    Args:
        sites_file: Path to text file with URLs
        
    Returns:
        List of normalized, deduplicated URLs
    """
    path = Path(sites_file)
    if not path.exists():
        raise FileNotFoundError(f"Sites file not found: {sites_file}")
    
    urls = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)
    
    if not urls:
        raise ValueError(f"No URLs found in {sites_file}")
    
    # Normalize and deduplicate
    normalized = [normalize_url(url) for url in urls]
    unique = deduplicate_urls(normalized)
    
    console.print(f"[green]Loaded {len(unique)} unique URLs from {sites_file}[/green]")
    return unique


def extract_brand_info(soup, html_str: str) -> Tuple[str, str, str, str]:
    """
    Extract brand positioning information.
    
    Returns:
        Tuple of (brand_name, description_zh, meta_description, hero_text)
    """
    brand_name = ""
    description_zh = ""
    meta_description = ""
    hero_text = ""
    
    # Get meta description - try multiple approaches
    meta_selectors = [
        ('meta', {'name': 'description'}),
        ('meta', {'property': 'og:description'}),
        ('meta', {'name': 'twitter:description'}),
    ]
    
    for tag, attrs in meta_selectors:
        meta_tag = soup.find(tag, attrs=attrs)
        if meta_tag and meta_tag.get('content'):
            meta_description = meta_tag.get('content', '')[:300]
            break
    
    # Get OG title or site title as brand name
    og_title = soup.find('meta', property='og:site_name')
    if og_title and og_title.get('content'):
        brand_name = og_title.get('content', '')[:50]
    
    if not brand_name:
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
            # Take first part before | or - separator
            for sep in ['|', '-', '–', '—', ':', '•']:
                if sep in title:
                    brand_name = title.split(sep)[0].strip()
                    break
            if not brand_name:
                brand_name = title[:50]
    
    # Get hero text from common hero section selectors - expanded
    hero_selectors = [
        # Standard hero elements
        '.hero__title', '.hero-title', '.hero h1', '.banner__heading',
        'h1.title', '.headline', 'section h1', '.hero-banner h1',
        '[data-section-type="slideshow"] h1', '.slideshow h1',
        # Modern Shopify themes
        '.banner__heading', '.slideshow__heading', '.hero__heading',
        '.image-with-text__heading', '.rich-text__heading',
        '.section-header__title', '.featured-collection__title',
        # Generic prominent text
        '.jumbotron h1', '.masthead h1', '.intro h1',
        'main h1', 'article h1', '.content h1',
        '[class*="Hero"] h1', '[class*="hero"] h1',
        '[class*="Banner"] h1', '[class*="banner"] h1',
    ]
    
    for selector in hero_selectors:
        try:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                if text and len(text) > 3 and len(text) < 300:
                    hero_text = text
                    break
        except Exception:
            continue
    
    # If no hero text, try first significant h1
    if not hero_text:
        for h1 in soup.find_all('h1'):
            text = h1.get_text(strip=True)
            if text and len(text) > 5 and len(text) < 200:
                # Skip if it looks like a product title on a product page
                parent_classes = ' '.join(h1.parent.get('class', []) if h1.parent else [])
                if 'product' not in parent_classes.lower():
                    hero_text = text
                    break
    
    # Also try to extract tagline/slogan
    tagline_selectors = [
        '.tagline', '.slogan', '.subtitle', '.hero__subtitle',
        '.banner__subheading', '.hero-description', '.hero__description',
        '[class*="tagline"]', '[class*="slogan"]'
    ]
    
    tagline = ""
    for selector in tagline_selectors:
        try:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                if text and len(text) > 5:
                    tagline = text[:150]
                    break
        except Exception:
            continue
    
    # Combine hero and tagline for better context
    combined_context = f"{hero_text} {tagline} {meta_description}"
    
    # Generate Chinese brand description based on content
    description_zh = generate_brand_description_zh(
        brand_name, meta_description, combined_context, html_str
    )
    
    return brand_name, description_zh, meta_description, hero_text


def generate_brand_description_zh(
    brand_name: str,
    meta_description: str,
    hero_text: str,
    html_str: str
) -> str:
    """Generate Chinese brand positioning description."""
    
    combined_text = f"{meta_description} {hero_text} {html_str[:5000]}".lower()
    
    # Keywords to detect brand type
    category_keywords = {
        '时尚服饰': ['fashion', 'clothing', 'apparel', 'wear', 'dress', 'style', 'outfit'],
        '配饰珠宝': ['accessory', 'accessories', 'bracelet', 'jewelry', 'watch', 'necklace', 'ring'],
        '美妆护肤': ['beauty', 'skincare', 'cosmetics', 'makeup', 'skin', 'serum', 'cream'],
        '运动户外': ['sport', 'fitness', 'athletic', 'outdoor', 'gym', 'workout', 'active'],
        '家居生活': ['home', 'decor', 'furniture', 'living', 'kitchen', 'bedroom'],
        '电子科技': ['tech', 'electronic', 'gadget', 'device', 'smart', 'digital'],
        '食品饮料': ['food', 'drink', 'snack', 'organic', 'coffee', 'tea', 'healthy'],
        '母婴用品': ['baby', 'kids', 'children', 'maternity', 'toddler', 'infant'],
        '宠物用品': ['pet', 'dog', 'cat', 'animal', 'puppy', 'kitten'],
    }
    
    # Audience keywords
    audience_keywords = {
        '年轻消费者': ['young', 'millennial', 'gen z', 'trendy', 'hip', 'cool'],
        '女性': ['women', 'woman', 'her', 'female', 'ladies', 'feminine'],
        '男性': ['men', 'man', 'him', 'male', 'masculine', 'gentleman'],
        '高端客群': ['luxury', 'premium', 'exclusive', 'elite', 'sophisticated'],
        '注重环保': ['sustainable', 'eco', 'green', 'organic', 'natural', 'vegan'],
        '礼品场景': ['gift', 'present', 'gifting', 'birthday', 'holiday'],
    }
    
    # Detect category
    category = "综合品类"
    for cat, keywords in category_keywords.items():
        if any(kw in combined_text for kw in keywords):
            category = cat
            break
    
    # Detect audience
    audiences = []
    for aud, keywords in audience_keywords.items():
        if any(kw in combined_text for kw in keywords):
            audiences.append(aud)
    
    audience_str = "、".join(audiences[:2]) if audiences else "大众消费者"
    
    # Build description
    description = f"{category}品牌，面向{audience_str}"
    
    return description


def extract_categories(soup, base_url: str = "") -> List[str]:
    """
    Extract product categories from navigation.
    
    Uses the new category_extractor module for better extraction,
    with fallback to the legacy method.
    """
    # Try using the new module-based extractor first
    if base_url:
        try:
            result = extract_categories_module(soup, base_url)
            if result.get('categories'):
                return result['categories'][:15]  # Return up to 15 categories
        except Exception:
            pass
    
    # Fallback to legacy extraction method
    categories = []
    
    # Common navigation selectors - expanded for modern themes
    nav_selectors = [
        # Standard nav elements
        'nav a', '.nav a', '.navigation a', '.menu a',
        '.site-nav a', '.main-nav a', '.header-menu a',
        '[data-section-type="header"] a',
        # Modern Shopify themes (like Rastaclat)
        '.header__menu a', '.header__nav a', '.header__primary-nav a',
        '.header__primary-nav-item a', '.header-sidebar__linklist a',
        'header nav a', '.site-header a',
        '.mega-menu a', '.dropdown-menu a',
        # Menu items with specific classes
        '.menu-item a', '.nav-item a', '.nav-link',
        '.header-menu-item a', '.main-menu a',
        # Mobile menu (often has full navigation)
        '.mobile-nav a', '.mobile-menu a',
        '[class*="MobileMenu"] a', '[class*="mobile-nav"] a',
        # List-based navigation
        '.nav-list a', '.menu-list a',
        'ul.nav a', 'ul.menu a',
    ]
    
    skip_words = [
        'home', 'about', 'contact', 'faq', 'blog', 'account', 'cart',
        'login', 'search', 'help', 'support', 'privacy', 'terms',
        'shipping', 'returns', 'track', 'gift card', 'rewards',
        'sign in', 'register', 'log in', 'my account', 'wishlist',
        'stores', 'locations', 'careers', 'press', 'wholesale',
        'instagram', 'facebook', 'twitter', 'pinterest', 'tiktok',
        'youtube', 'email', 'subscribe', 'newsletter'
    ]
    
    # Category indicator words (positive signals)
    category_indicators = [
        'collection', 'shop', 'product', 'category', 'catalog',
        'men', 'women', 'kids', 'sale', 'new', 'best', 'all',
        'accessories', 'clothing', 'shoes', 'bags', 'jewelry'
    ]
    
    seen_texts = set()
    
    for selector in nav_selectors:
        try:
            links = soup.select(selector)
            for link in links:
                href = link.get('href', '').lower()
                text = link.get_text(strip=True)
                
                if not text or len(text) < 2 or len(text) > 40:
                    continue
                
                text_lower = text.lower()
                
                # Skip if contains skip words
                if any(skip in text_lower for skip in skip_words):
                    continue
                
                # Skip external links
                if href.startswith('http') and 'collection' not in href and 'shop' not in href:
                    if not any(ind in href for ind in category_indicators):
                        continue
                
                # Check if it's likely a category/collection link
                is_category = (
                    '/collections/' in href or 
                    '/collection/' in href or
                    '/category/' in href or 
                    '/shop/' in href or
                    '/products' in href or
                    '/catalog/' in href or
                    any(ind in href for ind in category_indicators) or
                    any(ind in text_lower for ind in category_indicators)
                )
                
                # Also accept navigation items that look like categories
                if not is_category:
                    # Check if it's a simple nav item that could be a category
                    if href.startswith('/') and len(href.split('/')) <= 3:
                        if not any(skip in href for skip in skip_words):
                            is_category = True
                
                if is_category:
                    # Normalize text
                    clean_text = text.strip()
                    if clean_text.lower() not in seen_texts:
                        seen_texts.add(clean_text.lower())
                        categories.append(clean_text)
        except Exception:
            continue
    
    # If we still don't have categories, try to extract from any prominent links
    if len(categories) < 3:
        # Try schema.org breadcrumbs
        breadcrumbs = soup.select('[itemtype*="BreadcrumbList"] a, .breadcrumb a, .breadcrumbs a')
        for link in breadcrumbs:
            text = link.get_text(strip=True)
            if text and text.lower() not in seen_texts and text.lower() not in skip_words:
                if len(text) > 2 and len(text) < 40:
                    seen_texts.add(text.lower())
                    categories.append(text)
    
    return categories[:15]  # Limit to 15


def analyze_site(
    url: str,
    client: HttpClient,
    robots_checker: RobotsChecker,
    config: Config,
    progress: Optional[Progress] = None,
    task_id: Optional[int] = None
) -> SiteIntelligence:
    """
    Perform complete analysis of a single site.
    
    Args:
        url: Site URL to analyze
        client: HTTP client instance
        robots_checker: Robots.txt checker
        config: Application configuration
        progress: Optional progress tracker
        task_id: Optional task ID for progress updates
        
    Returns:
        SiteIntelligence object with all extracted data
    """
    domain = extract_domain(url)
    logger = logging.getLogger(__name__)
    
    # Initialize intelligence object
    intel = SiteIntelligence(
        domain=domain,
        url=url,
        scan_timestamp=datetime.now()
    )
    
    def update_progress(msg: str):
        if progress and task_id is not None:
            progress.update(task_id, description=f"[cyan]{domain}[/cyan]: {msg}")
    
    # Step 1: Fetch homepage
    update_progress("Fetching homepage...")
    soup, status, error = client.fetch_and_parse(url)
    
    if error:
        intel.errors.append(f"Homepage fetch failed: {error}")
        logger.warning(f"Failed to fetch {url}: {error}")
        return intel
    
    intel.pages_crawled.append(url)
    html_str = str(soup)
    
    # Check if this is a protected site placeholder
    is_protected_site = 'Bot protection detected' in html_str or 'strong bot protection' in html_str
    if is_protected_site:
        logger.info(f"Site {domain} has bot protection - providing limited analysis")
        intel.errors.append("Site has bot protection - limited automated data available. Manual analysis recommended.")
        intel.platform = Platform.CUSTOM
        intel.platform_confidence = 0
        # Still continue to provide what we can from public knowledge
    
    # Step 2: Detect platform
    update_progress("Detecting platform...")
    html_content, _, headers, _ = client.fetch(url)
    platform, confidence, signals = detect_platform(soup, headers or {}, url)
    intel.platform = platform
    intel.platform_confidence = confidence
    intel.platform_signals = signals
    
    # Step 3: Extract brand info
    update_progress("Extracting brand info...")
    brand_name, desc_zh, meta_desc, hero = extract_brand_info(soup, html_str)
    intel.brand_name = brand_name
    intel.brand_description_zh = desc_zh
    intel.meta_description = meta_desc
    intel.hero_text = hero
    
    # Step 4: Extract categories from navigation
    update_progress("Extracting categories...")
    intel.categories = extract_categories(soup, url)
    
    # Step 5: Extract promotions from homepage
    update_progress("Analyzing promotions...")
    promo_data = extract_promotions(soup, html_str)
    intel.promotions = promo_data['promotions']
    intel.announcement_bar_text = promo_data['announcement_bar_text']
    intel.has_popup = promo_data['has_popup']
    intel.has_email_capture = promo_data['has_email_capture']
    intel.has_loyalty_program = promo_data['has_loyalty_program']
    intel.has_referral_program = promo_data['has_referral_program']
    intel.social_embeds = promo_data['social_embeds']
    intel.pixels = promo_data['pixels']
    
    # Step 6: Extract trust signals
    update_progress("Analyzing trust signals...")
    trust_data = extract_trust_signals(soup, html_str)
    intel.trust_signals = trust_data['trust_signals']
    intel.review_platform = trust_data['review_platform']
    intel.total_reviews = trust_data['total_reviews']
    intel.payment_methods = trust_data['payment_methods']
    
    # Step 6.5: Supplement extraction from raw HTML for Shopify sites
    # This catches data that may not be found by standard extractors
    if intel.platform == Platform.SHOPIFY or 'shopify' in html_str.lower():
        import json as json_module
        
        # Extract from Judge.me settings if present
        if not intel.review_platform and ('jdgm' in html_str.lower() or 'judge.me' in html_str.lower()):
            intel.review_platform = 'Judge.me'
            jdgm_match = re.search(r'window\.jdgmSettings\s*=\s*({[^;]+});', html_str)
            if jdgm_match:
                try:
                    settings = json_module.loads(jdgm_match.group(1))
                    title = settings.get('widget_title', '')
                    count_match = re.search(r'([\d,]+)\+?\s*(others|reviews|customers)', title, re.I)
                    if count_match and not intel.total_reviews:
                        intel.total_reviews = int(count_match.group(1).replace(',', ''))
                except:
                    pass
        
        # Extract payment methods from Apple Pay JSON
        if not intel.payment_methods:
            apple_pay_script = soup.select_one('script#apple-pay-shop-capabilities')
            if apple_pay_script and apple_pay_script.string:
                try:
                    data = json_module.loads(apple_pay_script.string)
                    methods = []
                    for network in data.get('supportedNetworks', []):
                        network_map = {'visa': 'Visa', 'mastercard': 'Mastercard', 'masterCard': 'Mastercard',
                                      'amex': 'American Express', 'discover': 'Discover'}
                        if network.lower() in network_map or network in network_map:
                            methods.append(network_map.get(network.lower(), network_map.get(network, network)))
                    if data.get('shopifyPaymentsEnabled'):
                        methods.append('Shop Pay')
                    intel.payment_methods = list(set(methods))
                except:
                    pass
            
            # Check PayPal meta
            paypal_meta = soup.select_one('meta#in-context-paypal-metadata')
            if paypal_meta and 'PayPal' not in (intel.payment_methods or []):
                if not intel.payment_methods:
                    intel.payment_methods = []
                intel.payment_methods.append('PayPal')
        
        # Extract free shipping from page text
        if not promo_data.get('free_shipping_threshold'):
            text = soup.get_text().lower()
            shipping_patterns = [
                r'free\s+shipping\s+on\s+orders\s+\$?(\d+)\+?',
                r'free\s+shipping\s+over\s+\$?(\d+)',
                r'\$(\d+)\+?\s+free\s+shipping',
            ]
            for pattern in shipping_patterns:
                match = re.search(pattern, text, re.I)
                if match:
                    promo_data['free_shipping_threshold'] = float(match.group(1))
                    break
        
        # Update announcement bar if not found
        if not intel.announcement_bar_text:
            # Look for promo-slide elements
            promo_slides = soup.find_all(
                lambda tag: tag.get('class') and any('promo' in c.lower() for c in tag.get('class', []))
            )
            for slide in promo_slides:
                text = slide.get_text(strip=True)
                if text and len(text) > 5 and len(text) < 300:
                    promo_indicators = ['free', 'ship', 'off', 'sale', 'save', 'buy', 'get', '%', '$']
                    if any(ind in text.lower() for ind in promo_indicators):
                        intel.announcement_bar_text = text[:200]
                        break
    
    # Step 7: Discover and analyze additional pages
    update_progress("Discovering pages...")
    pages = discover_pages(url, client, robots_checker, config)
    
    all_products = []
    
    # For Shopify sites, ensure we try /collections/all and /products.json
    if intel.platform == Platform.SHOPIFY:
        from modules.url_utils import normalize_url
        from urllib.parse import urljoin
        
        # Try to fetch products.json API endpoint
        products_json_url = urljoin(url, '/products.json')
        update_progress("Fetching Shopify products API...")
        
        try:
            html_content, status, headers, error = client.fetch(products_json_url)
            if not error and html_content:
                try:
                    import json
                    data = json.loads(html_content)
                    if 'products' in data:
                        for prod_data in data['products'][:config.max_products]:
                            from modules.product_extractor import ProductExtractor
                            extractor = ProductExtractor(Platform.SHOPIFY)
                            p = extractor._parse_shopify_product(prod_data, url)
                            if p:
                                all_products.append(p)
                        logger.info(f"Extracted {len(data['products'])} products from products.json")
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            logger.debug(f"Could not fetch products.json: {e}")
        
        # Ensure /collections/all is in the pages list
        collections_all = normalize_url(urljoin(url, '/collections/all'))
        if not any(p[0] == collections_all for p in pages):
            pages.insert(1, (collections_all, 'collection'))
    
    # Analyze discovered pages
    for page_url, page_type in pages[:config.max_pages]:
        if page_url == url:  # Skip homepage, already processed
            continue
        
        update_progress(f"Analyzing {page_type} page...")
        
        page_soup, page_status, page_error = client.fetch_and_parse(page_url)
        
        if page_error:
            intel.pages_failed.append(page_url)
            intel.errors.append(f"Failed to fetch {page_url}: {page_error}")
            continue
        
        intel.pages_crawled.append(page_url)
        page_html = str(page_soup)
        
        # Extract products from collection/product pages
        if page_type in ('collection', 'product', 'home'):
            products = extract_products(page_soup, page_url, intel.platform, page_type)
            all_products.extend(products)
            
            # Check for bundles/subscriptions
            for p in products:
                if p.is_bundle:
                    intel.has_bundles = True
                if p.is_subscription:
                    intel.has_subscriptions = True
        
        # Extract policies with evidence tracking
        if page_type == 'policy' or 'shipping' in page_url.lower() or 'return' in page_url.lower():
            page_text = page_soup.get_text()
            shipping, returns = extract_policies(page_soup, page_text, page_type)
            
            # Determine evidence level based on URL pattern
            evidence_level = 3  # Default: product/cart level
            evidence_source = 'product_page'
            
            if '/policies/' in page_url.lower() or '/policy/' in page_url.lower():
                evidence_level = 1
                evidence_source = 'policy_page'
            elif '/faq' in page_url.lower() or '/help' in page_url.lower() or '/pages/shipping' in page_url.lower():
                evidence_level = 2
                evidence_source = 'faq'
            
            if shipping and (not intel.shipping_policy or shipping.free_shipping_threshold is not None):
                shipping.evidence_level = evidence_level
                shipping.evidence_source = evidence_source
                shipping.evidence_url = page_url
                shipping.requires_manual_verification = (evidence_level >= 3)
                intel.shipping_policy = shipping
            
            if returns and (not intel.return_policy or returns.return_days is not None):
                returns.evidence_level = evidence_level
                returns.evidence_source = evidence_source
                returns.evidence_url = page_url
                returns.requires_manual_verification = (evidence_level >= 3)
                intel.return_policy = returns
        
        # Stop if we have enough products
        if len(all_products) >= config.max_products:
            break
    
    # Step 8: Process products and calculate stats
    update_progress("Processing products...")
    
    # Deduplicate products by URL
    seen_urls = set()
    unique_products = []
    for p in all_products:
        if p.url not in seen_urls:
            seen_urls.add(p.url)
            unique_products.append(p)
    
    intel.all_products = unique_products[:config.max_products]
    intel.hero_products = unique_products[:3]
    
    # Calculate price statistics
    if unique_products:
        price_min, price_max, price_median, currency = calculate_price_stats(unique_products)
        intel.price_min = price_min
        intel.price_max = price_max
        intel.price_median = price_median
        intel.currency = currency
        
        # Check for discounts
        intel.has_discounts = any(
            p.price and p.price.is_on_sale 
            for p in unique_products
        )
        
        if intel.has_discounts:
            discount_products = [
                p for p in unique_products 
                if p.price and p.price.discount_percent
            ]
            if discount_products:
                avg_discount = sum(p.price.discount_percent for p in discount_products) / len(discount_products)
                intel.discount_summary = f"平均折扣约{avg_discount:.0f}%"
    
    # FALLBACK: If no prices found from product extraction, try JavaScript extraction
    # This is critical for sites like Alo Yoga where prices are in searchSettings.suggestedProducts
    if not intel.price_min and html_str:
        logger.info("No prices from product extraction, trying JavaScript fallback...")
        js_price_min, js_price_max, js_price_median, js_currency = extract_price_stats_from_html(html_str)
        if js_price_min is not None:
            intel.price_min = js_price_min
            intel.price_max = js_price_max
            intel.price_median = js_price_median
            if js_currency:
                intel.currency = js_currency
            logger.info(f"Extracted prices from JavaScript: ${js_price_min} - ${js_price_max}")
    
    # Set free shipping threshold from promotions if not found in policies
    if not intel.shipping_policy:
        intel.shipping_policy = type('ShippingPolicy', (), {
            'free_shipping_threshold': promo_data.get('free_shipping_threshold'),
            'regions': ['United States'],
            'estimated_days_min': None,
            'estimated_days_max': None,
            'has_international': False,
            'raw_text': '',
            'to_dict': lambda self: {
                'free_shipping_threshold': self.free_shipping_threshold,
                'regions': self.regions,
                'estimated_days_min': self.estimated_days_min,
                'estimated_days_max': self.estimated_days_max,
                'has_international': self.has_international,
                'raw_text': self.raw_text
            }
        })()
    elif promo_data.get('free_shipping_threshold') and not intel.shipping_policy.free_shipping_threshold:
        intel.shipping_policy.free_shipping_threshold = promo_data['free_shipping_threshold']
    
    # Fallback: Try to extract policies from homepage JavaScript
    # This helps when policy pages are blocked by robots.txt (common on Shopify)
    if html_str:
        js_policies = extract_policies_from_homepage_js(html_str)
        
        # Apply JS-extracted shipping data if not already found
        if js_policies.get('free_shipping_threshold') is not None:
            if not intel.shipping_policy or not intel.shipping_policy.free_shipping_threshold:
                if not intel.shipping_policy:
                    from modules.models import ShippingPolicy
                    intel.shipping_policy = ShippingPolicy()
                intel.shipping_policy.free_shipping_threshold = js_policies['free_shipping_threshold']
        
        # Apply JS-extracted return data if not already found
        if js_policies.get('return_days'):
            if not intel.return_policy or not intel.return_policy.return_days:
                if not intel.return_policy:
                    from modules.models import ReturnPolicy
                    intel.return_policy = ReturnPolicy()
                intel.return_policy.return_days = js_policies['return_days']
        
        if js_policies.get('free_returns'):
            if not intel.return_policy:
                from modules.models import ReturnPolicy
                intel.return_policy = ReturnPolicy()
            intel.return_policy.free_returns = True
    
    update_progress("Complete!")
    return intel


@click.command()
@click.option('--sites', '-s', required=True, help='Path to sites.txt file with URLs')
@click.option('--outdir', '-o', default='output', help='Output directory for reports')
@click.option('--render-js', is_flag=True, default=False, help='Use Playwright for JS rendering')
@click.option('--ignore-robots', is_flag=True, default=False, help='Ignore robots.txt restrictions')
@click.option('--timeout', '-t', default=30, help='Request timeout in seconds')
@click.option('--max-products', default=50, help='Max products to extract per site')
@click.option('--max-pages', default=20, help='Max pages to crawl per site')
@click.option('--monitor', '-m', is_flag=True, default=False, help='Enable monitor mode for change detection')
@click.option('--config', '-c', default=None, help='Path to config.yaml file')
@click.option('--verbose', '-v', is_flag=True, default=False, help='Enable verbose logging')
@click.option('--ai', is_flag=True, default=False, help='Enable AI-powered analysis with Ollama/Qwen2.5')
@click.option('--ai-model', default='qwen2.5:7b', help='Ollama model to use (default: qwen2.5:7b)')
@click.option('--lang', '-l', type=click.Choice(['en', 'zh']), default='zh', help='Report language: en=English, zh=Chinese (default)')
def main(
    sites: str,
    outdir: str,
    render_js: bool,
    ignore_robots: bool,
    timeout: int,
    max_products: int,
    max_pages: int,
    monitor: bool,
    config: Optional[str],
    verbose: bool,
    ai: bool,
    ai_model: str,
    lang: str
):
    """
    E-commerce Competitive Intelligence Tool
    
    Analyzes e-commerce sites and generates Chinese merchant-ready intelligence reports.
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)
    
    console.print("\n[bold blue]🔍 E-commerce Competitive Intelligence Tool[/bold blue]\n")
    
    # Load configuration
    config_data = load_config(config)
    
    # Build config object
    app_config = Config(
        sites_file=sites,
        output_dir=outdir,
        render_js=render_js or config_data.get('render_js', False),
        ignore_robots=ignore_robots or config_data.get('ignore_robots', False),
        timeout=timeout or config_data.get('timeout', 30),
        max_products=max_products or config_data.get('max_products', 50),
        max_pages=max_pages or config_data.get('max_pages', 20),
        monitor_mode=monitor,
        db_path=config_data.get('db_path', 'data/intel_cache.db')
    )
    
    # Initialize AI analyzer if enabled
    ai_analyzer = None
    if ai:
        try:
            from modules.ai_analyzer import AIAnalyzer, AIConfig
            ai_config = AIConfig(ollama_model=ai_model)
            ai_analyzer = AIAnalyzer(ai_config)
            
            if ai_analyzer.is_ai_available():
                console.print(f"[green]✓ AI Analysis enabled ({ai_model})[/green]")
            else:
                console.print(f"[yellow]⚠ AI requested but Ollama not available[/yellow]")
                console.print("  Start Ollama: ollama serve")
                console.print(f"  Pull model: ollama pull {ai_model}")
                ai_analyzer = None
        except ImportError as e:
            console.print(f"[yellow]⚠ AI modules not available: {e}[/yellow]")
            console.print("  Install with: pip install ollama scikit-learn xgboost")
            ai_analyzer = None
    
    # Load sites
    try:
        site_urls = load_sites(sites)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    
    # Initialize components
    client = HttpClient(app_config)
    robots_checker = RobotsChecker(app_config)
    snapshot_store = SnapshotStore(app_config.db_path)
    report_writer = ReportWriter(outdir, language=lang)
    
    # Log language setting
    lang_name = "English" if lang == 'en' else "Chinese (中文)"
    console.print(f"[blue]📝 Report language: {lang_name}[/blue]")
    
    # Track results
    intel_results: List[SiteIntelligence] = []
    change_reports: Dict[str, Optional[ChangeReport]] = {}
    
    try:
        # Process each site
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            
            main_task = progress.add_task(
                "[green]Analyzing sites...", 
                total=len(site_urls)
            )
            
            for url in site_urls:
                domain = extract_domain(url)
                
                # Check robots.txt
                if not app_config.ignore_robots and not robots_checker.is_allowed(url):
                    console.print(f"[yellow]Skipping {domain} - blocked by robots.txt[/yellow]")
                    progress.advance(main_task)
                    continue
                
                try:
                    # Analyze site
                    intel = analyze_site(
                        url, client, robots_checker, app_config,
                        progress, main_task
                    )
                    
                    # Handle monitor mode
                    if app_config.monitor_mode:
                        change_report = snapshot_store.compute_changes(intel)
                        change_reports[domain] = change_report
                        
                        if change_report and change_report.has_changes():
                            console.print(f"[yellow]Changes detected for {domain}[/yellow]")
                    
                    # Save snapshot
                    snapshot_store.save_snapshot(intel)
                    
                    # AI-powered analysis (if enabled)
                    if ai_analyzer:
                        try:
                            console.print(f"  [cyan]Running AI analysis for {domain}...[/cyan]")
                            ai_results = ai_analyzer.analyze_site(intel.to_dict())
                            
                            # Store AI results in intel object for report generation
                            intel.ai_insights = ai_results.get('insights', {})
                            intel.ai_positioning = ai_results.get('positioning', '')
                            intel.ai_pricing = ai_results.get('pricing', {})
                            intel.ai_threat = ai_results.get('threat', {})
                            
                            if ai_results.get('ai_available'):
                                console.print(f"  [green]✓ AI analysis complete[/green]")
                        except Exception as e:
                            logger.warning(f"AI analysis failed for {domain}: {e}")
                    
                    # Show scan history for this domain
                    scan_count = snapshot_store.get_scan_count(domain)
                    if scan_count > 1:
                        console.print(f"  [dim]📊 Scan #{scan_count} for {domain}[/dim]")
                    
                    intel_results.append(intel)
                    console.print(f"[green]✓ Completed: {domain}[/green]")
                    
                except Exception as e:
                    logger.exception(f"Error analyzing {url}")
                    console.print(f"[red]✗ Failed: {domain} - {str(e)[:50]}[/red]")
                
                progress.advance(main_task)
        
        # Generate reports
        if intel_results:
            console.print("\n[blue]Generating reports...[/blue]")
            
            # Get scan history for all domains
            scan_history = snapshot_store.get_all_domains_history()
            
            # Generate standard report
            md_path, csv_path = report_writer.write_full_report(
                intel_results, 
                change_reports,
                "report"
            )
            
            # Generate business report
            try:
                from modules.business_report import BusinessReportGenerator
                business_gen = BusinessReportGenerator(outdir, language=lang)
                business_path = business_gen.generate_report(
                    intel_results,
                    change_reports,
                    scan_history,
                    "business_report"
                )
                console.print(f"  📈 Business Report: {business_path}")
            except Exception as e:
                logger.warning(f"Business report generation failed: {e}")
            
            console.print(f"\n[green]✓ Reports generated:[/green]")
            console.print(f"  📄 Markdown: {md_path}")
            console.print(f"  📊 CSV: {csv_path}")
            
            # Print summary statistics
            console.print(f"\n[blue]Summary:[/blue]")
            console.print(f"  Sites analyzed: {len(intel_results)}")
            
            shopify_count = sum(1 for i in intel_results if i.platform == Platform.SHOPIFY)
            console.print(f"  Shopify sites: {shopify_count}")
            
            if any(cr and cr.has_changes() for cr in change_reports.values()):
                changes_count = sum(1 for cr in change_reports.values() if cr and cr.has_changes())
                console.print(f"  Sites with changes: {changes_count}")
            
            # Show storage stats
            stats = snapshot_store.get_stats()
            console.print(f"  Total snapshots stored: {stats['total_snapshots']}")
        else:
            console.print("[yellow]No sites were successfully analyzed.[/yellow]")
    
    finally:
        # Cleanup
        client.close()
    
    console.print("\n[bold green]Done![/bold green]\n")


if __name__ == '__main__':
    main()
