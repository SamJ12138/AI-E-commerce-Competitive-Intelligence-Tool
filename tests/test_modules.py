"""
tests/test_modules.py - Unit tests for e-commerce intelligence modules.

Run with: python -m pytest tests/ -v
"""

import pytest
from bs4 import BeautifulSoup
from datetime import datetime

import sys
sys.path.insert(0, '.')

from modules.models import (
    Platform, Config, SiteIntelligence, Product, PriceInfo,
    ShippingPolicy, ReturnPolicy, Promotion, TrustSignal, ChangeReport
)
from modules.url_utils import (
    normalize_url, extract_domain, is_same_domain,
    is_internal_link, make_absolute_url, categorize_page_type
)
from modules.platform_detector import detect_platform


class TestUrlUtils:
    """Tests for URL utility functions."""
    
    def test_normalize_url_adds_scheme(self):
        assert normalize_url("example.com").startswith("https://")
    
    def test_normalize_url_removes_trailing_slash(self):
        url = normalize_url("https://example.com/path/")
        assert not url.endswith("/")
    
    def test_normalize_url_removes_tracking_params(self):
        url = normalize_url("https://example.com?utm_source=test&id=123")
        assert "utm_source" not in url
        assert "id=123" in url
    
    def test_extract_domain(self):
        assert extract_domain("https://www.example.com/path") == "example.com"
        assert extract_domain("https://shop.example.co.uk/path") == "example.co.uk"
    
    def test_is_same_domain(self):
        assert is_same_domain(
            "https://example.com/page1",
            "https://example.com/page2"
        )
        assert not is_same_domain(
            "https://example.com",
            "https://other.com"
        )
    
    def test_is_internal_link(self):
        base = "https://example.com"
        assert is_internal_link(base, "/products")
        assert is_internal_link(base, "https://example.com/about")
        assert not is_internal_link(base, "https://other.com")
        assert not is_internal_link(base, "#anchor")
    
    def test_make_absolute_url(self):
        base = "https://example.com/page"
        assert make_absolute_url(base, "/products") == "https://example.com/products"
        assert make_absolute_url(base, "https://other.com") == "https://other.com"
        assert make_absolute_url(base, "//cdn.example.com/img.jpg") == "https://cdn.example.com/img.jpg"
    
    def test_categorize_page_type(self):
        assert categorize_page_type("https://example.com/") == "home"
        assert categorize_page_type("https://example.com/products/item") == "product"
        assert categorize_page_type("https://example.com/collections/all") == "collection"
        assert categorize_page_type("https://example.com/policies/shipping") == "policy"
        assert categorize_page_type("https://example.com/pages/about") == "about"


class TestPlatformDetector:
    """Tests for platform detection."""
    
    def test_detect_shopify(self):
        html = """
        <html>
        <head>
            <script src="https://cdn.shopify.com/s/files/1/theme.js"></script>
            <meta name="generator" content="Shopify">
        </head>
        <body>
            <div data-shopify="true">Content</div>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        platform, confidence, signals = detect_platform(soup, {}, "https://example.com")
        
        assert platform == Platform.SHOPIFY
        assert confidence >= 0.8
        assert len(signals) >= 2
    
    def test_detect_woocommerce(self):
        html = """
        <html>
        <head>
            <link rel="stylesheet" href="/wp-content/plugins/woocommerce/style.css">
        </head>
        <body class="woocommerce">
            <button class="add_to_cart_button">Add</button>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        platform, confidence, signals = detect_platform(soup, {}, "https://example.com")
        
        assert platform == Platform.WOOCOMMERCE
    
    def test_detect_custom_unknown(self):
        html = """
        <html>
        <body><p>Simple page</p></body>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        platform, confidence, signals = detect_platform(soup, {}, "https://example.com")
        
        assert platform == Platform.CUSTOM
        assert confidence == 0.0


class TestModels:
    """Tests for data models."""
    
    def test_price_info_to_dict(self):
        price = PriceInfo(
            currency="USD",
            current_price=29.99,
            compare_at_price=39.99,
            is_on_sale=True,
            discount_percent=25
        )
        d = price.to_dict()
        
        assert d['currency'] == 'USD'
        assert d['current_price'] == 29.99
        assert d['is_on_sale'] is True
    
    def test_product_to_dict(self):
        product = Product(
            title="Test Product",
            url="https://example.com/products/test",
            price=PriceInfo(currency="USD", current_price=19.99),
            is_bundle=True
        )
        d = product.to_dict()
        
        assert d['title'] == "Test Product"
        assert d['is_bundle'] is True
        assert d['price']['current_price'] == 19.99
    
    def test_site_intelligence_to_dict(self):
        intel = SiteIntelligence(
            domain="example.com",
            url="https://example.com",
            scan_timestamp=datetime.now(),
            platform=Platform.SHOPIFY
        )
        d = intel.to_dict()
        
        assert d['domain'] == 'example.com'
        assert d['platform'] == 'Shopify'
    
    def test_change_report_has_changes(self):
        report = ChangeReport(
            domain="example.com",
            previous_scan=datetime.now(),
            current_scan=datetime.now()
        )
        
        assert not report.has_changes()
        
        report.price_changes.append("Price changed")
        assert report.has_changes()
    
    def test_shipping_policy_to_dict(self):
        policy = ShippingPolicy(
            regions=['United States', 'Canada'],
            free_shipping_threshold=50.0,
            estimated_days_min=3,
            estimated_days_max=7
        )
        d = policy.to_dict()
        
        assert len(d['regions']) == 2
        assert d['free_shipping_threshold'] == 50.0
    
    def test_return_policy_to_dict(self):
        policy = ReturnPolicy(
            return_days=30,
            free_returns=True,
            conditions=['Unworn', 'Original tags']
        )
        d = policy.to_dict()
        
        assert d['return_days'] == 30
        assert d['free_returns'] is True


class TestPromoExtraction:
    """Tests for promotion extraction."""
    
    def test_detect_announcement_bar(self):
        from modules.promo_extractor import extract_promotions
        
        html = """
        <html>
        <body>
            <div class="announcement-bar">Free shipping on orders over $50!</div>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_promotions(soup, html)
        
        assert "Free shipping" in result['announcement_bar_text']
    
    def test_detect_email_capture(self):
        from modules.promo_extractor import extract_promotions
        
        html = """
        <html>
        <body>
            <form class="newsletter-form">
                <input type="email" name="email">
                <button>Subscribe</button>
            </form>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_promotions(soup, html)
        
        assert result['has_email_capture'] is True
    
    def test_detect_pixels(self):
        from modules.promo_extractor import extract_promotions
        
        html = """
        <html>
        <head>
            <script>
                gtag('config', 'G-12345678');
                fbq('init', '123456789');
            </script>
        </head>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_promotions(soup, html)
        
        ga_pixel = next((p for p in result['pixels'] if p.name == 'Google Analytics'), None)
        meta_pixel = next((p for p in result['pixels'] if p.name == 'Meta Pixel'), None)
        
        assert ga_pixel is not None and ga_pixel.detected
        assert meta_pixel is not None and meta_pixel.detected


class TestPolicyExtraction:
    """Tests for policy extraction."""
    
    def test_extract_return_days(self):
        from modules.policy_extractor import extract_policies
        
        html = """
        <html>
        <body>
            <h1>Return Policy</h1>
            <p>We offer a 30-day return policy on all items.</p>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text()
        
        shipping, returns = extract_policies(soup, text, 'policy')
        
        assert returns is not None
        assert returns.return_days == 30
    
    def test_extract_free_shipping_threshold(self):
        from modules.policy_extractor import extract_policies
        
        html = """
        <html>
        <body>
            <h1>Shipping Policy</h1>
            <p>Free shipping on orders over $75. Standard delivery in 5-7 business days.</p>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text()
        
        shipping, returns = extract_policies(soup, text, 'policy')
        
        assert shipping is not None
        assert shipping.free_shipping_threshold == 75.0


class TestTrustExtraction:
    """Tests for trust signal extraction."""
    
    def test_detect_review_platform(self):
        from modules.trust_extractor import extract_trust_signals
        
        html = """
        <html>
        <body>
            <div class="jdgm-widget" data-review-count="150">
                Reviews powered by Judge.me
            </div>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_trust_signals(soup, html)
        
        assert result['review_platform'] == 'Judge.me'
    
    def test_detect_payment_methods(self):
        from modules.trust_extractor import extract_trust_signals
        
        html = """
        <html>
        <body>
            <div class="payment-icons">
                <img alt="PayPal">
                <img alt="Apple Pay">
                <img alt="Klarna">
            </div>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_trust_signals(soup, html)
        
        assert 'PayPal' in result['payment_methods']
        assert 'Apple Pay' in result['payment_methods']
        assert 'Klarna' in result['payment_methods']


class TestInsightGeneration:
    """Tests for insight generation."""
    
    def test_generate_insights(self):
        from modules.insight_generator import generate_insights
        
        intel = SiteIntelligence(
            domain="example.com",
            url="https://example.com",
            scan_timestamp=datetime.now(),
            platform=Platform.SHOPIFY,
            brand_positioning="Simple cotton basics",
            categories=['Clothing', 'Accessories'],
            price_min=20.0,
            price_max=100.0,
            price_median=45.0,
            has_email_capture=True,
            has_popup=True
        )
        
        result = generate_insights(intel)
        
        assert len(result['key_insights']) > 0
        assert len(result['recommendations']) == 3
        assert len(result['evidence']) > 0
    
    def test_format_changes(self):
        from modules.insight_generator import format_changes_zh
        
        report = ChangeReport(
            domain="example.com",
            previous_scan=datetime.now(),
            current_scan=datetime.now(),
            price_changes=["最低价从 $20 变为 $15"],
            new_products=["新产品: Test Product"]
        )
        
        lines = format_changes_zh(report)
        
        assert any("$20" in line and "$15" in line for line in lines)
        assert any("新产品" in line for line in lines)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
