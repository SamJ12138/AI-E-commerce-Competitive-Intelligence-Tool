"""
models.py - Data models and type definitions for e-commerce intelligence extraction.

This module defines all the dataclasses used throughout the application for
structured data representation. Keeping models separate enables easy testing
and extension.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class Platform(Enum):
    """Supported e-commerce platforms."""
    SHOPIFY = "Shopify"
    WOOCOMMERCE = "WooCommerce"
    MAGENTO = "Magento"
    BIGCOMMERCE = "BigCommerce"
    WIX = "Wix"
    SQUARESPACE = "Squarespace"
    PRESTASHOP = "PrestaShop"
    CUSTOM = "Custom/Unknown"


@dataclass
class PriceInfo:
    """Pricing information extracted from a product."""
    currency: str = "USD"
    current_price: Optional[float] = None
    compare_at_price: Optional[float] = None  # Original/strikethrough price
    is_on_sale: bool = False
    discount_percent: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "current_price": self.current_price,
            "compare_at_price": self.compare_at_price,
            "is_on_sale": self.is_on_sale,
            "discount_percent": self.discount_percent
        }


@dataclass
class Product:
    """Extracted product information."""
    title: str
    url: str
    price: Optional[PriceInfo] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    has_reviews: bool = False
    review_count: Optional[int] = None
    is_bundle: bool = False
    is_subscription: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "price": self.price.to_dict() if self.price else None,
            "image_url": self.image_url,
            "category": self.category,
            "has_reviews": self.has_reviews,
            "review_count": self.review_count,
            "is_bundle": self.is_bundle,
            "is_subscription": self.is_subscription
        }


@dataclass
class ShippingPolicy:
    """Shipping policy information with evidence source tracking."""
    regions: List[str] = field(default_factory=list)
    free_shipping_threshold: Optional[float] = None
    estimated_days_min: Optional[int] = None
    estimated_days_max: Optional[int] = None
    has_international: bool = False
    raw_text: str = ""
    # Evidence tracking for legal compliance
    evidence_source: str = ""  # 'policy_page', 'faq', 'product_page', 'cart', 'blocked'
    evidence_url: str = ""  # URL where data was extracted
    evidence_level: int = 0  # 1=official policy, 2=FAQ, 3=product/cart, 4=blocked
    requires_manual_verification: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "regions": self.regions,
            "free_shipping_threshold": self.free_shipping_threshold,
            "estimated_days_min": self.estimated_days_min,
            "estimated_days_max": self.estimated_days_max,
            "has_international": self.has_international,
            "raw_text": self.raw_text[:500] if self.raw_text else "",
            "evidence_source": self.evidence_source,
            "evidence_url": self.evidence_url,
            "evidence_level": self.evidence_level,
            "requires_manual_verification": self.requires_manual_verification
        }


@dataclass
class ReturnPolicy:
    """Return policy information with evidence source tracking."""
    return_days: Optional[int] = None
    free_returns: bool = False
    conditions: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)
    raw_text: str = ""
    # Evidence tracking for legal compliance
    evidence_source: str = ""  # 'policy_page', 'faq', 'product_page', 'blocked'
    evidence_url: str = ""  # URL where data was extracted
    evidence_level: int = 0  # 1=official policy, 2=FAQ, 3=product/cart, 4=blocked
    requires_manual_verification: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "return_days": self.return_days,
            "free_returns": self.free_returns,
            "conditions": self.conditions,
            "exclusions": self.exclusions,
            "raw_text": self.raw_text[:500] if self.raw_text else "",
            "evidence_source": self.evidence_source,
            "evidence_url": self.evidence_url,
            "evidence_level": self.evidence_level,
            "requires_manual_verification": self.requires_manual_verification
        }


@dataclass
class Promotion:
    """Detected promotion or marketing tactic."""
    promo_type: str  # e.g., "announcement_bar", "popup", "free_shipping", "discount_code"
    description: str
    value: Optional[str] = None  # e.g., "15% OFF", "$50"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "promo_type": self.promo_type,
            "description": self.description,
            "value": self.value
        }


@dataclass
class TrustSignal:
    """Trust and conversion optimization signals."""
    signal_type: str  # e.g., "reviews", "badge", "payment_method"
    name: str
    details: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "name": self.name,
            "details": self.details
        }


@dataclass
class AnalyticsPixel:
    """Detected analytics/tracking pixel."""
    name: str  # e.g., "Google Analytics", "Meta Pixel", "TikTok Pixel"
    detected: bool = False
    identifier: Optional[str] = None  # e.g., GA tracking ID if found
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "detected": self.detected,
            "identifier": self.identifier
        }


@dataclass
class SiteIntelligence:
    """Complete intelligence report for a single site."""
    domain: str
    url: str
    scan_timestamp: datetime

    # 'ok', 'blocked' (no page answered 2xx) or 'unreachable' (no HTTP answer at all).
    # For anything but 'ok' every extracted field is None: the tool did not see the site.
    status: str = "ok"
    fetch_attempts: List[str] = field(default_factory=list)  # e.g. ['requests 403', 'cloudscraper 403']
    fetch_branches: Dict[str, int] = field(default_factory=dict)  # branch -> usable responses it served

    # Platform detection
    platform: Optional[Platform] = Platform.CUSTOM
    platform_confidence: float = 0.0
    platform_signals: List[str] = field(default_factory=list)
    
    # Brand positioning
    brand_name: str = ""
    brand_positioning: Optional[str] = None         # verbatim from the page, never inferred
    brand_positioning_source: Optional[str] = None  # 'meta description' / 'title' / 'headline'
    meta_description: str = ""
    hero_text: str = ""
    about_snippet: str = ""
    
    # Products
    categories: List[str] = field(default_factory=list)
    hero_products: List[Product] = field(default_factory=list)
    all_products: List[Product] = field(default_factory=list)
    has_bundles: bool = False
    has_subscriptions: bool = False
    
    # Pricing
    currency: Optional[str] = "USD"
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    price_median: Optional[float] = None
    has_discounts: bool = False
    discount_summary: str = ""
    
    # Promotions
    promotions: List[Promotion] = field(default_factory=list)
    announcement_bar_text: str = ""
    has_popup: bool = False
    has_email_capture: bool = False
    has_loyalty_program: bool = False
    has_referral_program: bool = False
    social_embeds: List[str] = field(default_factory=list)
    
    # Analytics
    pixels: List[AnalyticsPixel] = field(default_factory=list)
    
    # Trust signals
    trust_signals: List[TrustSignal] = field(default_factory=list)
    review_platform: str = ""
    total_reviews: Optional[int] = None
    payment_methods: List[str] = field(default_factory=list)
    
    # Policies
    shipping_policy: Optional[ShippingPolicy] = None
    return_policy: Optional[ReturnPolicy] = None
    
    # Page data
    pages_crawled: List[str] = field(default_factory=list)
    pages_failed: List[str] = field(default_factory=list)
    
    # Errors
    errors: List[str] = field(default_factory=list)

    # Output of the optional LLM step (--ai). Set only for text the LLM actually produced;
    # ai_model names the Ollama model and stays None when the LLM did not run.
    ai_insights: Dict[str, Any] = field(default_factory=dict)
    ai_positioning: str = ""
    ai_model: Optional[str] = None

    UNKNOWN_WHEN_BLOCKED = (
        'platform', 'platform_confidence', 'brand_name', 'brand_positioning', 'brand_positioning_source',
        'currency', 'price_min', 'price_max', 'price_median', 'has_discounts', 'has_bundles',
        'has_subscriptions', 'announcement_bar_text', 'has_popup', 'has_email_capture',
        'has_loyalty_program', 'has_referral_program', 'review_platform', 'total_reviews',
        'shipping_policy', 'return_policy',
    )

    def mark_unknown(self, status: str, fetch_attempts: List[str]) -> None:
        """The site could not be seen: every extracted field becomes None (lists empty)."""
        self.status = status
        self.fetch_attempts = list(fetch_attempts)
        for name in self.UNKNOWN_WHEN_BLOCKED:
            setattr(self, name, None)
        self.categories, self.hero_products, self.all_products = [], [], []
        self.promotions, self.pixels, self.trust_signals = [], [], []
        self.payment_methods, self.platform_signals, self.social_embeds = [], [], []

    @property
    def is_analyzed(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage and serialization."""
        return {
            "domain": self.domain,
            "url": self.url,
            "scan_timestamp": self.scan_timestamp.isoformat(),
            "status": self.status,
            "fetch_attempts": self.fetch_attempts,
            "fetch_branches": self.fetch_branches,
            "platform": self.platform.value if self.platform else None,
            "platform_confidence": self.platform_confidence,
            "platform_signals": self.platform_signals,
            "brand_name": self.brand_name,
            "brand_positioning": self.brand_positioning,
            "brand_positioning_source": self.brand_positioning_source,
            "meta_description": self.meta_description,
            "hero_text": self.hero_text,
            "about_snippet": self.about_snippet,
            "categories": self.categories,
            "hero_products": [p.to_dict() for p in self.hero_products],
            "all_products": [p.to_dict() for p in self.all_products],
            "has_bundles": self.has_bundles,
            "has_subscriptions": self.has_subscriptions,
            "currency": self.currency,
            "price_min": self.price_min,
            "price_max": self.price_max,
            "price_median": self.price_median,
            "has_discounts": self.has_discounts,
            "discount_summary": self.discount_summary,
            "promotions": [p.to_dict() for p in self.promotions],
            "announcement_bar_text": self.announcement_bar_text,
            "has_popup": self.has_popup,
            "has_email_capture": self.has_email_capture,
            "has_loyalty_program": self.has_loyalty_program,
            "has_referral_program": self.has_referral_program,
            "social_embeds": self.social_embeds,
            "pixels": [p.to_dict() for p in self.pixels],
            "trust_signals": [t.to_dict() for t in self.trust_signals],
            "review_platform": self.review_platform,
            "total_reviews": self.total_reviews,
            "payment_methods": self.payment_methods,
            "shipping_policy": self.shipping_policy.to_dict() if self.shipping_policy else None,
            "return_policy": self.return_policy.to_dict() if self.return_policy else None,
            "pages_crawled": self.pages_crawled,
            "pages_failed": self.pages_failed,
            "errors": self.errors
        }


@dataclass
class ChangeReport:
    """Report of changes detected between two scans."""
    domain: str
    previous_scan: datetime
    current_scan: datetime
    
    price_changes: List[str] = field(default_factory=list)
    promo_changes: List[str] = field(default_factory=list)
    new_products: List[str] = field(default_factory=list)
    removed_products: List[str] = field(default_factory=list)
    category_changes: List[str] = field(default_factory=list)
    policy_changes: List[str] = field(default_factory=list)
    
    def has_changes(self) -> bool:
        return any([
            self.price_changes,
            self.promo_changes,
            self.new_products,
            self.removed_products,
            self.category_changes,
            self.policy_changes
        ])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "previous_scan": self.previous_scan.isoformat(),
            "current_scan": self.current_scan.isoformat(),
            "price_changes": self.price_changes,
            "promo_changes": self.promo_changes,
            "new_products": self.new_products,
            "removed_products": self.removed_products,
            "category_changes": self.category_changes,
            "policy_changes": self.policy_changes
        }


@dataclass
class Config:
    """Application configuration."""
    sites_file: str = "sites.txt"
    output_dir: str = "output"
    render_js: bool = False
    ignore_robots: bool = False
    timeout: int = 30
    max_products: int = 50
    max_pages: int = 20
    language: str = "zh"
    rate_limit_delay: float = 1.5  # seconds between requests to same domain
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    db_path: str = "data/intel_cache.db"
    monitor_mode: bool = False
