"""
E-commerce Intelligence Tool - Modules Package

This package provides modular components for extracting competitive
intelligence from e-commerce websites.
"""

from .models import (
    Platform, Config, SiteIntelligence, ChangeReport,
    Product, PriceInfo, ShippingPolicy, ReturnPolicy,
    Promotion, TrustSignal, AnalyticsPixel
)

from .http_client import HttpClient
from .robots_checker import RobotsChecker
from .url_utils import normalize_url, extract_domain, deduplicate_urls
from .platform_detector import detect_platform
from .page_discovery import discover_pages
from .product_extractor import extract_products, calculate_price_stats
from .price_extractor import extract_prices_from_js, extract_price_stats_from_html
from .promo_extractor import extract_promotions
from .policy_extractor import extract_policies, PolicyExtractor, extract_policies_from_homepage_js
from .policy_evidence import PolicyEvidenceLadder, PolicyEvidence, EvidenceLevel, create_blocked_policy_note
from .trust_extractor import extract_trust_signals
from .category_extractor import extract_categories, CategoryExtractor
from .snapshot_store import SnapshotStore
from .insight_generator import generate_insights, format_changes_zh
from .report_writer import write_markdown_report, write_csv, ReportWriter
from .business_report import BusinessReportGenerator

# AI-powered analysis (optional, requires additional dependencies)
try:
    from .ai_analyzer import AIAnalyzer, AIConfig, create_analyzer
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

__all__ = [
    # Models
    'Platform', 'Config', 'SiteIntelligence', 'ChangeReport',
    'Product', 'PriceInfo', 'ShippingPolicy', 'ReturnPolicy',
    'Promotion', 'TrustSignal', 'AnalyticsPixel',
    
    # Components
    'HttpClient', 'RobotsChecker', 'SnapshotStore', 'ReportWriter',
    'PolicyExtractor', 'CategoryExtractor',
    'PolicyEvidenceLadder', 'PolicyEvidence', 'EvidenceLevel',
    'BusinessReportGenerator',
    
    # Functions
    'normalize_url', 'extract_domain', 'deduplicate_urls',
    'detect_platform', 'discover_pages',
    'extract_products', 'calculate_price_stats',
    'extract_prices_from_js', 'extract_price_stats_from_html',
    'extract_promotions', 'extract_policies', 'extract_policies_from_homepage_js',
    'extract_trust_signals', 'extract_categories',
    'generate_insights', 'format_changes_zh',
    'write_markdown_report', 'write_csv',
    'create_blocked_policy_note',
    
    # AI (optional)
    'AIAnalyzer', 'AIConfig', 'create_analyzer', 'AI_AVAILABLE',
]
