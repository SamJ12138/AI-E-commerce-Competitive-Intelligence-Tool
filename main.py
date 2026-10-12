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
from typing import List, Dict, NamedTuple, Optional, Tuple

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
from modules import obs
from modules.pressure_score import score_pressure

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
    obs.event("load", "success", kind="sites_loaded", sites_file=str(sites_file), lines=len(urls),
              unique=len(unique), duplicates_dropped=len(urls) - len(unique), urls=unique)
    
    console.print(f"[green]Loaded {len(unique)} unique URLs from {sites_file}[/green]")
    return unique


class BrandInfo(NamedTuple):
    brand_name: str
    positioning: Optional[str]          # verbatim text from the page, or None
    positioning_source: Optional[str]   # 'meta description' / 'title' / 'headline'
    meta_description: str
    hero_text: str


TITLE_SEPARATORS = (' | ', ' \u2013 ', ' \u2014 ', ' - ', ' : ', ': ', ' \u2022 ')


def extract_brand_info(soup, html_str: str) -> BrandInfo:
    """
    Brand name and positioning, both taken from the page itself.

    Positioning is the first of: meta description (name=description, og:, twitter:),
    the tagline part of <title>, the hero headline (3+ words). It is quoted verbatim in
    the page's own language; when none exists it is None. Nothing is inferred.
    """
    brand_name = ""
    meta_description = ""
    hero_text = ""

    for attrs in ({'name': 'description'}, {'property': 'og:description'}, {'name': 'twitter:description'}):
        meta_tag = soup.find('meta', attrs=attrs)
        if meta_tag and meta_tag.get('content', '').strip():
            meta_description = ' '.join(meta_tag['content'].split())[:300]
            break

    og_title = soup.find('meta', property='og:site_name')
    if og_title and og_title.get('content'):
        brand_name = og_title.get('content', '')[:50]
        obs.note('brand_name', brand_name, 'selector', "meta[property=og:site_name]")

    title = ""
    title_tag = soup.find('title')
    if title_tag:
        title = ' '.join(title_tag.get_text(strip=True).split())
    title_parts = [title]
    for sep in TITLE_SEPARATORS:
        if sep in title:
            title_parts = [part.strip() for part in title.split(sep) if part.strip()]
            break
    if not brand_name and title:
        brand_name = title_parts[0][:50]
        obs.note('brand_name', brand_name, 'selector', "<title> first part")

    hero_selectors = [
        '.hero__title', '.hero-title', '.hero h1', '.banner__heading',
        'h1.title', '.headline', 'section h1', '.hero-banner h1',
        '[data-section-type="slideshow"] h1', '.slideshow h1',
        '.slideshow__heading', '.hero__heading',
        '.image-with-text__heading', '.rich-text__heading',
        'main h1', '[class*="hero"] h1', '[class*="banner"] h1',
    ]
    for selector in hero_selectors:
        try:
            elem = soup.select_one(selector)
        except Exception:
            obs.swallowed("main.py:extract_brand_info", error_type="parse", fallback="next hero selector",
                          stage="brand", selector=selector)
            continue
        if elem:
            text = ' '.join(elem.get_text(' ', strip=True).split())
            if 3 < len(text) < 300:
                hero_text = text
                break

    tagline = next((part for part in title_parts[1:] if part.lower() != brand_name.lower()), None)
    candidates = [(meta_description, 'meta description'), (tagline, 'title'),
                  (hero_text if len(hero_text.split()) >= 3 else None, 'headline')]
    positioning, source = next(((text, src) for text, src in candidates if text), (None, None))
    obs.note('brand_positioning', positioning, 'selector' if positioning else 'default',
             f"quoted from the page's {source}" if positioning else
             "no meta description, title tagline or headline: left empty", stage='brand')

    return BrandInfo(brand_name, positioning, source, meta_description, hero_text)


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
                obs.note('categories', result['categories'][:15], 'selector',
                         "category_extractor: nav selectors, /collections/ links, footer shop sections",
                         stage='categories')
                return result['categories'][:15]  # Return up to 15 categories
            obs.degraded("main.py:extract_categories", "parse", "category_extractor found nothing",
                         fallback="legacy nav selectors", stage="categories")
        except Exception:
            obs.swallowed("main.py:extract_categories", error_type="parse", fallback="legacy nav selectors",
                          stage="categories")
    
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
            obs.swallowed("main.py:extract_categories", error_type="parse", fallback="next nav selector",
                          stage="categories", selector=selector)
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

    obs.note('categories', categories[:15], 'selector' if categories else 'default',
             "legacy nav selectors in main.extract_categories (+ breadcrumbs when < 3)", stage='categories')
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
    obs.set_page(url)
    t = obs.begin("fetch_homepage", url=url)
    soup, status, error = client.fetch_and_parse(url)

    if error:
        obs.event("fetch_homepage", "fail", duration_ms=t.ms(), error_type=obs.classify_fetch(status, error),
                  error_message=error, url=url, status=status)
        obs.degraded("main.py:analyze_site", obs.classify_fetch(status, error) or "http",
                     "homepage fetch failed; analysis stops here",
                     fallback="SiteIntelligence with defaults is still saved and reported (and AI-scored with --ai)",
                     stage="fetch_homepage", event_name="fail")
        intel.errors.append(f"Homepage fetch failed: {error}")
        logger.warning(f"Failed to fetch {url}: {error}")
        return intel

    intel.pages_crawled.append(url)
    html_str = str(soup)
    obs.end("fetch_homepage", t, url=url, status=status, chars=len(html_str))

    # Check if this is a protected site placeholder
    is_protected_site = 'Bot protection detected' in html_str or 'strong bot protection' in html_str
    if is_protected_site:
        obs.degraded("main.py:analyze_site", "blocked", "homepage is the PROTECTED_SITES placeholder",
                     fallback="continue extracting from placeholder HTML", stage="fetch_homepage", event_name="fail")
        logger.info(f"Site {domain} has bot protection - providing limited analysis")
        intel.errors.append("Site has bot protection - limited automated data available. Manual analysis recommended.")
        intel.platform = Platform.CUSTOM
        intel.platform_confidence = 0
        # Still continue to provide what we can from public knowledge
    
    # Step 2: Detect platform
    update_progress("Detecting platform...")
    t = obs.begin("platform", note="homepage fetched a second time only to read response headers")
    html_content, _, headers, _ = client.fetch(url)
    platform, confidence, signals = detect_platform(soup, headers or {}, url)
    intel.platform = platform
    intel.platform_confidence = confidence
    intel.platform_signals = signals
    obs.end("platform", t, platform=platform.value, confidence=confidence, signals=signals)

    # Step 3: Extract brand info
    update_progress("Extracting brand info...")
    t = obs.begin("brand")
    brand = extract_brand_info(soup, html_str)
    intel.brand_name = brand.brand_name
    intel.brand_positioning = brand.positioning
    intel.brand_positioning_source = brand.positioning_source
    intel.meta_description = brand.meta_description
    intel.hero_text = brand.hero_text
    obs.end("brand", t, brand_name=brand.brand_name, positioning_source=brand.positioning_source,
            hero_text=brand.hero_text[:120])

    # Step 4: Extract categories from navigation
    update_progress("Extracting categories...")
    t = obs.begin("categories")
    intel.categories = extract_categories(soup, url)
    obs.end("categories", t, count=len(intel.categories))

    # Step 5: Extract promotions from homepage
    update_progress("Analyzing promotions...")
    t = obs.begin("promos", page=url)
    promo_data = extract_promotions(soup, html_str)
    intel.promotions = promo_data['promotions']
    intel.announcement_bar_text = promo_data['announcement_bar_text']
    intel.has_popup = promo_data['has_popup']
    intel.has_email_capture = promo_data['has_email_capture']
    intel.has_loyalty_program = promo_data['has_loyalty_program']
    intel.has_referral_program = promo_data['has_referral_program']
    intel.social_embeds = promo_data['social_embeds']
    intel.pixels = promo_data['pixels']
    obs.end("promos", t, promotions=len(intel.promotions),
            homepage_only=True)

    # Step 6: Extract trust signals
    update_progress("Analyzing trust signals...")
    t = obs.begin("trust", page=url)
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
            obs.note('review_platform', 'Judge.me', 'regex', "main.py Shopify supplement: 'jdgm'/'judge.me' in html")
            jdgm_match = re.search(r'window\.jdgmSettings\s*=\s*({[^;]+});', html_str)
            if jdgm_match:
                try:
                    settings = json_module.loads(jdgm_match.group(1))
                    title = settings.get('widget_title', '')
                    count_match = re.search(r'([\d,]+)\+?\s*(others|reviews|customers)', title, re.I)
                    if count_match and not intel.total_reviews:
                        intel.total_reviews = int(count_match.group(1).replace(',', ''))
                        obs.note('review_count', intel.total_reviews, 'json',
                                 "main.py Shopify supplement: jdgmSettings.widget_title")
                except:
                    obs.swallowed("main.py:analyze_site", error_type="parse",
                                  fallback="review count unchanged", stage="trust")
        
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
                    obs.note('payment_methods', intel.payment_methods, 'json',
                             "main.py Shopify supplement: script#apple-pay-shop-capabilities")
                except:
                    obs.swallowed("main.py:analyze_site", error_type="parse",
                                  fallback="payment methods unchanged", stage="trust")

            # Check PayPal meta
            paypal_meta = soup.select_one('meta#in-context-paypal-metadata')
            if paypal_meta and 'PayPal' not in (intel.payment_methods or []):
                if not intel.payment_methods:
                    intel.payment_methods = []
                intel.payment_methods.append('PayPal')
                obs.note('payment_methods', list(intel.payment_methods), 'selector',
                         "main.py Shopify supplement: meta#in-context-paypal-metadata")
        
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
                    obs.note('free_shipping_threshold', float(match.group(1)), 'regex',
                             f"main.py Shopify supplement shipping_patterns[{shipping_patterns.index(pattern)}] "
                             f"matched {match.group(0)!r}")
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
                        obs.note('announcement_bar', intel.announcement_bar_text, 'selector',
                                 "main.py Shopify supplement: class contains 'promo'")
                        break
    obs.end("trust", t, review_platform=intel.review_platform, payment_methods=intel.payment_methods)

    # Step 7: Discover and analyze additional pages
    update_progress("Discovering pages...")
    t = obs.begin("discovery")
    pages = discover_pages(url, client, robots_checker, config, platform=intel.platform, homepage_soup=soup)
    obs.end("discovery", t, pages=len(pages))

    all_products = []
    t_products = obs.begin("products")
    
    # For Shopify sites, try the /products.json API (every product with its compare-at price)
    if intel.platform == Platform.SHOPIFY:
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
                                _log_product(p, products_json_url)
                        logger.info(f"Extracted {len(data['products'])} products from products.json")
                except json.JSONDecodeError:
                    obs.swallowed("main.py:analyze_site", error_type="parse", fallback="no products.json products",
                                  stage="products", url=products_json_url)
            else:
                obs.degraded("main.py:analyze_site", obs.classify_fetch(status, error) or "http",
                             f"products.json unavailable: {error}", fallback="HTML pages only",
                             stage="products", url=products_json_url)
        except Exception as e:
            obs.swallowed("main.py:analyze_site", fallback="HTML pages only", stage="products",
                          url=products_json_url)
            logger.debug(f"Could not fetch products.json: {e}")
        
    # Analyze discovered pages
    for page_url, page_type in pages[:config.max_pages]:
        if page_url == url:  # Skip homepage, already processed
            continue
        
        update_progress(f"Analyzing {page_type} page...")

        obs.set_page(page_url)
        page_soup, page_status, page_error = client.fetch_and_parse(page_url)

        if page_error:
            obs.event("products" if page_type in ('collection', 'product', 'home') else "policies", "fail",
                      error_type=obs.classify_fetch(page_status, page_error), error_message=page_error,
                      kind="page_fetch_failed", url=page_url, page_type=page_type, status=page_status)
            intel.pages_failed.append(page_url)
            intel.errors.append(f"Failed to fetch {page_url}: {page_error}")
            continue

        intel.pages_crawled.append(page_url)
        page_html = str(page_soup)

        # Extract products from collection/product pages
        if page_type in ('collection', 'product', 'home'):
            products = extract_products(page_soup, page_url, intel.platform, page_type)
            all_products.extend(products)
            for p in products:
                _log_product(p, page_url)
            
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
                obs.event("policies", "success", kind="shipping_policy_accepted", url=page_url,
                          evidence_level=evidence_level, threshold=shipping.free_shipping_threshold)
                obs.apply('free_shipping_threshold', shipping.free_shipping_threshold,
                          f"shipping policy accepted from {page_url} (evidence level {evidence_level})",
                          stage="policies")
            elif shipping:
                obs.event("policies", "skip", kind="shipping_policy_ignored", url=page_url,
                          threshold=shipping.free_shipping_threshold,
                          reason="a policy is already set and this page has no threshold")

            if returns and (not intel.return_policy or returns.return_days is not None):
                returns.evidence_level = evidence_level
                returns.evidence_source = evidence_source
                returns.evidence_url = page_url
                returns.requires_manual_verification = (evidence_level >= 3)
                intel.return_policy = returns
                obs.event("policies", "success", kind="return_policy_accepted", url=page_url,
                          evidence_level=evidence_level, return_days=returns.return_days,
                          free_returns=returns.free_returns)
                for _f, _v in (('return_days', returns.return_days), ('free_returns', returns.free_returns)):
                    obs.apply(_f, _v, f"return policy accepted from {page_url} (evidence level {evidence_level})",
                              stage="policies")
            elif returns:
                obs.event("policies", "skip", kind="return_policy_ignored", url=page_url,
                          return_days=returns.return_days, reason="a policy is already set and this page has no days")
        
        # Stop if we have enough products
        if len(all_products) >= config.max_products:
            obs.event("products", "skip", kind="page_loop_stopped", reason="max_products reached",
                      products=len(all_products))
            break

    obs.set_page(None)

    # Step 8: Process products and calculate stats
    update_progress("Processing products...")
    
    # Deduplicate products by URL path (a card links '/product/x/', the page itself is '/product/x')
    from modules.product_extractor import product_key
    seen_urls = set()
    unique_products = []
    for p in all_products:
        key = product_key(p.url)
        if key not in seen_urls:
            seen_urls.add(key)
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
        _note_price_stats(unique_products, intel)
    else:
        obs.degraded("main.py:analyze_site", "parse", "no products extracted from any page",
                     fallback="homepage JS price fallback", stage="products", event_name="fail")
        
    # FALLBACK: If no prices found from product extraction, try JavaScript extraction
    # This is critical for sites like Alo Yoga where prices are in searchSettings.suggestedProducts
    if not intel.price_min and html_str:
        logger.info("No prices from product extraction, trying JavaScript fallback...")
        obs.event("products", "skip", kind="js_price_fallback", reason="no product price; scanning homepage html")
        js_price_min, js_price_max, js_price_median, js_currency = extract_price_stats_from_html(html_str)
        if js_price_min is not None:
            intel.price_min = js_price_min
            intel.price_max = js_price_max
            intel.price_median = js_price_median
            if js_currency:
                intel.currency = js_currency
            logger.info(f"Extracted prices from JavaScript: ${js_price_min} - ${js_price_max}")
    
    obs.end("products", t_products, products=len(unique_products), price_min=intel.price_min,
            price_max=intel.price_max)
    t = obs.begin("policies")

    # Set free shipping threshold from promotions if not found in policies
    if not intel.shipping_policy:
        obs.degraded("main.py:analyze_site", "parse", "no shipping policy parsed from any page",
                     fallback="ad-hoc ShippingPolicy from homepage promo threshold, regions=['United States']",
                     stage="policies", promo_threshold=promo_data.get('free_shipping_threshold'))
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
        obs.apply('free_shipping_threshold', intel.shipping_policy.free_shipping_threshold,
                  "ad-hoc ShippingPolicy built from the homepage promo threshold", stage="policies")
    elif promo_data.get('free_shipping_threshold') and not intel.shipping_policy.free_shipping_threshold:
        intel.shipping_policy.free_shipping_threshold = promo_data['free_shipping_threshold']
        obs.event("policies", "success", kind="threshold_from_homepage_promo",
                  threshold=promo_data['free_shipping_threshold'],
                  reason="policy page had no threshold (or 0)")
        obs.apply('free_shipping_threshold', promo_data['free_shipping_threshold'],
                  "homepage promo threshold applied because the policy page had none", stage="policies")
    
    # Fallback: Try to extract policies from homepage JavaScript
    # This helps when policy pages are blocked by robots.txt (common on Shopify)
    if html_str:
        js_policies = extract_policies_from_homepage_js(html_str)
        obs.event("policies", "success", kind="homepage_js_policies", result=js_policies)
        
        # Apply JS-extracted shipping data if not already found
        if js_policies.get('free_shipping_threshold') is not None:
            if not intel.shipping_policy or not intel.shipping_policy.free_shipping_threshold:
                if not intel.shipping_policy:
                    from modules.models import ShippingPolicy
                    intel.shipping_policy = ShippingPolicy()
                intel.shipping_policy.free_shipping_threshold = js_policies['free_shipping_threshold']
                obs.apply('free_shipping_threshold', js_policies['free_shipping_threshold'],
                          "homepage JS fallback applied", stage="policies")
        
        # Apply JS-extracted return data if not already found
        if js_policies.get('return_days'):
            if not intel.return_policy or not intel.return_policy.return_days:
                if not intel.return_policy:
                    from modules.models import ReturnPolicy
                    intel.return_policy = ReturnPolicy()
                intel.return_policy.return_days = js_policies['return_days']
                obs.apply('return_days', js_policies['return_days'], "homepage JS fallback applied",
                          stage="policies")
        
        if js_policies.get('free_returns'):
            if not intel.return_policy:
                from modules.models import ReturnPolicy
                intel.return_policy = ReturnPolicy()
            intel.return_policy.free_returns = True
            obs.apply('free_returns', True, "homepage JS fallback applied", stage="policies")
    
    obs.end("policies", t, free_shipping_threshold=getattr(intel.shipping_policy, 'free_shipping_threshold', None),
            return_days=getattr(intel.return_policy, 'return_days', None))
    update_progress("Complete!")
    return intel


def _log_product(p, page_url: str) -> None:
    """One obs event per extracted product with the rule that produced its price."""
    info = getattr(p, '_obs', {}) or {}
    obs.event("products", "success", kind="product", page=page_url, title=p.title, url=p.url,
              price=p.price.current_price if p.price else None,
              compare_at=p.price.compare_at_price if p.price else None,
              on_sale=p.price.is_on_sale if p.price else None,
              source=info.get('source', 'default'), detail=info.get('detail', ''))


def _note_price_stats(products, intel) -> None:
    """Provenance for price_min / price_max / price_median / currency / has_discounts."""
    priced = [p for p in products if p.price and p.price.current_price]
    def who(p):
        info = getattr(p, '_obs', {}) or {}
        return f"{p.title!r} {p.url} via {info.get('source', '?')}: {info.get('detail', '')}"
    if priced:
        lo = min(priced, key=lambda p: p.price.current_price)
        hi = max(priced, key=lambda p: p.price.current_price)
        obs.note('price_min', intel.price_min, 'derived', f"min over {len(priced)} priced products; {who(lo)}")
        obs.note('price_max', intel.price_max, 'derived', f"max over {len(priced)} priced products; {who(hi)}")
        obs.note('price_median', intel.price_median, 'derived',
                 f"median of {sorted(p.price.current_price for p in priced)}")
        obs.note('currency', intel.currency, 'derived', "currency of the last priced product")
    sale = [p for p in products if p.price and p.price.is_on_sale]
    if sale:
        obs.note('has_discounts', True, 'derived', "is_on_sale on: " + "; ".join(who(p) for p in sale))
    else:
        obs.note('has_discounts', False, 'default',
                 f"no product had is_on_sale ({len(products)} products, {len(priced)} priced)")


def _log_final_fields(intel) -> None:
    """The value each report field ends up with, and the rule that set it."""
    ship, ret = intel.shipping_policy, intel.return_policy
    values = {
        'platform': intel.platform.value,
        'brand_name': intel.brand_name,
        'brand_positioning': intel.brand_positioning,
        'categories': intel.categories,
        'price_min': intel.price_min,
        'price_max': intel.price_max,
        'price_median': intel.price_median,
        'currency': intel.currency,
        'has_discounts': intel.has_discounts,
        'announcement_bar': intel.announcement_bar_text,
        'has_popup': intel.has_popup,
        'has_email_capture': intel.has_email_capture,
        'has_loyalty': intel.has_loyalty_program,
        'has_referral': intel.has_referral_program,
        'free_shipping_threshold': getattr(ship, 'free_shipping_threshold', None) if ship else None,
        'return_days': ret.return_days if ret else None,
        'free_returns': ret.free_returns if ret else None,
        'review_platform': intel.review_platform,
        'review_count': intel.total_reviews,
        'payment_methods': intel.payment_methods,
        'pixels_detected': [p.name for p in intel.pixels if p.detected],
    }
    for name, value in values.items():
        obs.field("fields", name, value)


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
@click.option('--ai', is_flag=True, default=False, help='Run the LLM step: insights from a local Ollama model')
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
    obs.init_run()
    console.print(f"[dim]Run log: {obs.log_path()}[/dim]")

    console.print("\n[bold blue]🔍 E-commerce Competitive Intelligence Tool[/bold blue]\n")

    # Load configuration
    t_load = obs.begin("load", sites_file=sites, outdir=outdir, render_js=render_js,
                       ignore_robots=ignore_robots, timeout=timeout, max_products=max_products,
                       max_pages=max_pages, monitor=monitor, config=config, ai=ai, ai_model=ai_model,
                       lang=lang)
    import modules as modules_pkg
    if not modules_pkg.AI_AVAILABLE:
        obs.degraded("modules/__init__.py:<import>", "unknown", "ai_analyzer import failed",
                     fallback="AI_AVAILABLE=False", stage="load")
    if config and not Path(config).exists():
        obs.degraded("main.py:load_config", "input_invalid", f"config file {config!r} not found",
                     fallback="built-in defaults", stage="load")
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
    
    obs.event("load", "success", kind="config_resolved", config_keys=sorted(config_data),
              render_js=app_config.render_js, ignore_robots=app_config.ignore_robots,
              timeout=app_config.timeout, max_products=app_config.max_products,
              max_pages=app_config.max_pages, db_path=app_config.db_path,
              rate_limit_delay=app_config.rate_limit_delay,
              config_keys_ignored=sorted(set(config_data) - {'render_js', 'ignore_robots', 'timeout',
                                                             'max_products', 'max_pages', 'db_path'}))

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
                obs.degraded("main.py:main", "external_api", "--ai given but Ollama/model unavailable",
                             fallback="AI stage skipped for every site", stage="ai")
                console.print(f"[yellow]⚠ AI requested but Ollama not available[/yellow]")
                console.print("  Start Ollama: ollama serve")
                console.print(f"  Pull model: ollama pull {ai_model}")
                ai_analyzer = None
        except ImportError as e:
            obs.swallowed("main.py:main", error_type="unknown", fallback="AI stage skipped", stage="ai")
            console.print(f"[yellow]⚠ AI modules not available: {e}[/yellow]")
            console.print("  Install with: pip install ollama")
            ai_analyzer = None

    # Load sites
    try:
        site_urls = load_sites(sites)
    except (FileNotFoundError, ValueError) as e:
        obs.event("load", "fail", duration_ms=t_load.ms(), error_type="input_invalid",
                  error_message=f"{type(e).__name__}: {e}")
        obs.close_run()
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    obs.end("load", t_load, sites=len(site_urls))
    
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
                obs.set_site(url)
                t_site = obs.Timer()
                obs.event("site", "start", url=url, domain=domain)

                # Check robots.txt
                if app_config.ignore_robots:
                    obs.skip("robots", "--ignore-robots / ignore_robots: robots.txt not consulted")
                t = obs.begin("robots", url=url)
                if not app_config.ignore_robots and not robots_checker.is_allowed(url):
                    obs.skip("robots", "robots.txt disallows the homepage; site skipped", url=url)
                    obs.event("site", "skip", duration_ms=t_site.ms(), error_message="robots.txt disallow")
                    console.print(f"[yellow]Skipping {domain} - blocked by robots.txt[/yellow]")
                    progress.advance(main_task)
                    continue
                obs.end("robots", t, url=url, allowed=True)

                try:
                    # Analyze site
                    intel = analyze_site(
                        url, client, robots_checker, app_config,
                        progress, main_task
                    )
                    _log_final_fields(intel)
                    pressure = score_pressure(intel)
                    obs.field("fields", "pressure_score", pressure['score'], source="derived",
                              detail="rule-based: round(sum(weight * factor)) = "
                                     f"{pressure['weighted_sum']}; " + "; ".join(
                                         f"{f['key']} {f['weight']}x{f['score']} {f['inputs']}"
                                         for f in pressure['factors']))

                    # Handle monitor mode
                    if app_config.monitor_mode:
                        t = obs.begin("change_diff")
                        change_report = snapshot_store.compute_changes(intel, language=lang)
                        change_reports[domain] = change_report
                        obs.end("change_diff", t, has_changes=bool(change_report and change_report.has_changes()),
                                compared_with="second-newest stored snapshot (OFFSET 1), before this scan is saved")

                        if change_report and change_report.has_changes():
                            console.print(f"[yellow]Changes detected for {domain}[/yellow]")
                    else:
                        obs.skip("change_diff", "--monitor not set")

                    # Save snapshot
                    t = obs.begin("snapshot", db_path=app_config.db_path)
                    row_id = snapshot_store.save_snapshot(intel)
                    obs.end("snapshot", t, row_id=row_id, domain_key=intel.domain,
                            errors_recorded=len(intel.errors))

                    # AI-powered analysis (if enabled)
                    if not ai_analyzer:
                        obs.skip("ai", "--ai not set" if not ai else "AI requested but unavailable")
                    if ai_analyzer:
                        try:
                            t = obs.begin("ai", model=ai_model)
                            console.print(f"  [cyan]Running AI analysis for {domain}...[/cyan]")
                            ai_results = ai_analyzer.analyze_site(intel.to_dict())

                            # Keep only text the LLM produced; template fallbacks are not AI output
                            if ai_results.get('insights_from_llm'):
                                intel.ai_insights = ai_results.get('insights', {})
                            if ai_results.get('positioning_from_llm'):
                                intel.ai_positioning = ai_results.get('positioning', '')
                            if intel.ai_insights or intel.ai_positioning:
                                intel.ai_model = ai_results.get('model_used')
                            obs.end("ai", t, ai_available=ai_results.get('ai_available'), model=intel.ai_model)
                            for name, value in (('ai_insights', intel.ai_insights.get('key_insights')),
                                                ('ai_positioning', intel.ai_positioning)):
                                obs.field("fields", name, value)

                            if ai_results.get('ai_available'):
                                console.print(f"  [green]✓ AI analysis complete[/green]")
                        except Exception as e:
                            obs.swallowed("main.py:main", fallback="report without AI sections", stage="ai")
                            logger.warning(f"AI analysis failed for {domain}: {e}")
                    
                    # Show scan history for this domain
                    scan_count = snapshot_store.get_scan_count(domain)
                    if scan_count > 1:
                        console.print(f"  [dim]📊 Scan #{scan_count} for {domain}[/dim]")
                    
                    intel_results.append(intel)
                    obs.event("site", "success", duration_ms=t_site.ms(), errors=intel.errors,
                              pages_crawled=len(intel.pages_crawled), pages_failed=len(intel.pages_failed),
                              note="appended to the report even when errors is non-empty")
                    console.print(f"[green]✓ Completed: {domain}[/green]")

                except Exception as e:
                    obs.swallowed("main.py:main", fallback="site dropped from the report",
                                  stage=obs.current_stage() or "site")
                    obs.event("site", "fail", duration_ms=t_site.ms(), error_type=obs.classify_exception(e),
                              error_message=f"{type(e).__name__}: {e}")
                    logger.exception(f"Error analyzing {url}")
                    console.print(f"[red]✗ Failed: {domain} - {str(e)[:50]}[/red]")

                progress.advance(main_task)
        
        obs.set_site(None)
        # Generate reports
        if intel_results:
            console.print("\n[blue]Generating reports...[/blue]")
            t_report = obs.begin("report", sites=len(intel_results), lang=lang)

            # Get scan history for all domains
            scan_history = snapshot_store.get_all_domains_history()

            # Generate standard report
            md_path, csv_path = report_writer.write_full_report(
                intel_results,
                change_reports,
                "report"
            )
            obs.event("report", "success", kind="written", files=[md_path, csv_path],
                      insights_source="InsightGenerator rule templates (language argument unused: Chinese text)")
            
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
                obs.event("report", "success", kind="written", files=[business_path],
                          sites=len(intel_results), domains=sorted({i.domain for i in intel_results}),
                          ai_ran=ai_analyzer is not None)
            except Exception as e:
                obs.swallowed("main.py:main", fallback="no business_report.md", stage="report")
                logger.warning(f"Business report generation failed: {e}")
            obs.end("report", t_report)
            
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
            obs.skip("report", "no site produced a SiteIntelligence")
            console.print("[yellow]No sites were successfully analyzed.[/yellow]")

    finally:
        # Cleanup
        client.close()
        obs.event("run", "success", sites=len(site_urls), analyzed=len(intel_results))
        obs.close_run()

    console.print("\n[bold green]Done![/bold green]\n")


if __name__ == '__main__':
    main()
