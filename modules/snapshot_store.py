"""
snapshot_store.py - SQLite-based snapshot storage for change detection.

Stores site intelligence snapshots and provides diff functionality
to detect changes between scans.
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

from deepdiff import DeepDiff

from .models import SiteIntelligence, ChangeReport

logger = logging.getLogger(__name__)


class SnapshotStore:
    """
    SQLite-based storage for site intelligence snapshots.
    
    Enables:
    - Caching of scan results
    - Change detection between scans
    - Historical tracking
    """
    
    def __init__(self, db_path: str = "data/intel_cache.db"):
        self.db_path = db_path
        self._ensure_db()
    
    def _ensure_db(self) -> None:
        """Create database and tables if they don't exist."""
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Main snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                url TEXT NOT NULL,
                scan_timestamp TEXT NOT NULL,
                data JSON NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Index for quick lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_domain_timestamp 
            ON snapshots (domain, scan_timestamp DESC)
        """)
        
        # Page content cache
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS page_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                content_hash TEXT,
                html_preview TEXT,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(url)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def save_snapshot(self, intel: SiteIntelligence) -> int:
        """
        Save a site intelligence snapshot.
        
        Args:
            intel: SiteIntelligence object to save
            
        Returns:
            Row ID of the saved snapshot
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        data_json = json.dumps(intel.to_dict(), ensure_ascii=False)
        
        cursor.execute("""
            INSERT INTO snapshots (domain, url, scan_timestamp, data)
            VALUES (?, ?, ?, ?)
        """, (
            intel.domain,
            intel.url,
            intel.scan_timestamp.isoformat(),
            data_json
        ))
        
        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Saved snapshot for {intel.domain} (id={row_id})")
        return row_id
    
    def get_latest_snapshot(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent snapshot for a domain.
        
        Args:
            domain: Domain to look up
            
        Returns:
            Snapshot data as dictionary, or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT data, scan_timestamp FROM snapshots
            WHERE domain = ?
            ORDER BY scan_timestamp DESC
            LIMIT 1
        """, (domain,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return json.loads(row[0])
        return None
    
    def get_previous_snapshot(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Get the second most recent snapshot for a domain.
        
        Used for change detection against the latest scan.
        
        Args:
            domain: Domain to look up
            
        Returns:
            Snapshot data as dictionary, or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT data, scan_timestamp FROM snapshots
            WHERE domain = ?
            ORDER BY scan_timestamp DESC
            LIMIT 1 OFFSET 1
        """, (domain,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return json.loads(row[0])
        return None
    
    def get_all_snapshots(self, domain: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get all snapshots for a domain.
        
        Args:
            domain: Domain to look up
            limit: Maximum number of snapshots to return
            
        Returns:
            List of snapshot dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT data, scan_timestamp FROM snapshots
            WHERE domain = ?
            ORDER BY scan_timestamp DESC
            LIMIT ?
        """, (domain, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [json.loads(row[0]) for row in rows]
    
    def compute_changes(
        self,
        current: SiteIntelligence,
        previous: Optional[Dict[str, Any]] = None
    ) -> Optional[ChangeReport]:
        """
        Compute changes between current scan and previous snapshot.
        
        Args:
            current: Current SiteIntelligence object
            previous: Previous snapshot dict (if None, will fetch from DB)
            
        Returns:
            ChangeReport if changes detected, None otherwise
        """
        if previous is None:
            previous = self.get_previous_snapshot(current.domain)
        
        if previous is None:
            logger.info(f"No previous snapshot for {current.domain}")
            return None
        
        current_data = current.to_dict()
        
        report = ChangeReport(
            domain=current.domain,
            previous_scan=datetime.fromisoformat(previous['scan_timestamp']),
            current_scan=current.scan_timestamp
        )
        
        # Compare prices
        if previous.get('price_min') != current_data.get('price_min'):
            old_min = previous.get('price_min', 'N/A')
            new_min = current_data.get('price_min', 'N/A')
            report.price_changes.append(f"最低价从 ${old_min} 变为 ${new_min}")
        
        if previous.get('price_max') != current_data.get('price_max'):
            old_max = previous.get('price_max', 'N/A')
            new_max = current_data.get('price_max', 'N/A')
            report.price_changes.append(f"最高价从 ${old_max} 变为 ${new_max}")
        
        # Compare promotions
        old_announcement = previous.get('announcement_bar_text', '')
        new_announcement = current_data.get('announcement_bar_text', '')
        
        if old_announcement != new_announcement:
            if new_announcement:
                report.promo_changes.append(f"新公告栏: {new_announcement[:100]}")
            elif old_announcement:
                report.promo_changes.append("公告栏已移除")
        
        # Compare products
        old_products = set(p.get('title', '') for p in previous.get('hero_products', []))
        new_products = set(p.title for p in current.hero_products)
        
        added_products = new_products - old_products
        removed_products = old_products - new_products
        
        for product in list(added_products)[:3]:
            report.new_products.append(f"新产品: {product}")
        
        for product in list(removed_products)[:3]:
            report.removed_products.append(f"下架产品: {product}")
        
        # Compare categories
        old_categories = set(previous.get('categories', []))
        new_categories = set(current_data.get('categories', []))
        
        added_cats = new_categories - old_categories
        removed_cats = old_categories - new_categories
        
        for cat in list(added_cats)[:3]:
            report.category_changes.append(f"新品类: {cat}")
        
        for cat in list(removed_cats)[:3]:
            report.category_changes.append(f"移除品类: {cat}")
        
        # Compare policies
        old_shipping = previous.get('shipping_policy') or {}
        new_shipping = current_data.get('shipping_policy') or {}
        
        if old_shipping.get('free_shipping_threshold') != new_shipping.get('free_shipping_threshold'):
            old_thresh = old_shipping.get('free_shipping_threshold', 'N/A')
            new_thresh = new_shipping.get('free_shipping_threshold', 'N/A')
            report.policy_changes.append(f"免运费门槛从 ${old_thresh} 变为 ${new_thresh}")
        
        old_returns = previous.get('return_policy') or {}
        new_returns = current_data.get('return_policy') or {}
        
        if old_returns.get('return_days') != new_returns.get('return_days'):
            old_days = old_returns.get('return_days', 'N/A')
            new_days = new_returns.get('return_days', 'N/A')
            report.policy_changes.append(f"退货期限从 {old_days}天 变为 {new_days}天")
        
        return report if report.has_changes() else None
    
    def cache_page(
        self,
        url: str,
        content_hash: str,
        html_preview: str
    ) -> None:
        """
        Cache page content hash for change detection.
        
        Args:
            url: Page URL
            content_hash: Hash of page content
            html_preview: First N characters of HTML for debugging
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO page_cache (url, content_hash, html_preview, fetched_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (url, content_hash, html_preview[:1000]))
        
        conn.commit()
        conn.close()
    
    def get_cached_hash(self, url: str) -> Optional[str]:
        """
        Get cached content hash for a URL.
        
        Args:
            url: Page URL
            
        Returns:
            Content hash if cached, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT content_hash FROM page_cache WHERE url = ?
        """, (url,))
        
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else None
    
    def clear_domain(self, domain: str) -> int:
        """
        Clear all snapshots for a domain.
        
        Args:
            domain: Domain to clear
            
        Returns:
            Number of rows deleted
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM snapshots WHERE domain = ?", (domain,))
        deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(f"Cleared {deleted} snapshots for {domain}")
        return deleted
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Dictionary with stats
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM snapshots")
        total_snapshots = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT domain) FROM snapshots")
        unique_domains = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM page_cache")
        cached_pages = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_snapshots': total_snapshots,
            'unique_domains': unique_domains,
            'cached_pages': cached_pages,
            'db_path': self.db_path
        }
    
    def get_domain_scan_history(self, domain: str) -> List[Dict[str, Any]]:
        """
        Get complete scan history for a domain.
        
        Args:
            domain: Domain to look up
            
        Returns:
            List of scan records with timestamp and summary data
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, scan_timestamp, data, created_at FROM snapshots
            WHERE domain = ?
            ORDER BY scan_timestamp DESC
        """, (domain,))
        
        rows = cursor.fetchall()
        conn.close()
        
        history = []
        for row in rows:
            data = json.loads(row[2])
            history.append({
                'id': row[0],
                'scan_timestamp': row[1],
                'created_at': row[3],
                'price_min': data.get('price_min'),
                'price_max': data.get('price_max'),
                'price_median': data.get('price_median'),
                'has_free_shipping': data.get('shipping_policy', {}).get('free_shipping_threshold') == 0 if data.get('shipping_policy') else False,
                'return_days': data.get('return_policy', {}).get('return_days') if data.get('return_policy') else None,
                'full_data': data
            })
        
        return history
    
    def get_all_domains_history(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get scan history for all domains.
        
        Returns:
            Dictionary mapping domain to list of scan records
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT domain FROM snapshots
            ORDER BY domain
        """)
        
        domains = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        history = {}
        for domain in domains:
            history[domain] = self.get_domain_scan_history(domain)
        
        return history
    
    def get_scan_count(self, domain: str) -> int:
        """Get number of scans for a domain."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM snapshots WHERE domain = ?
        """, (domain,))
        
        count = cursor.fetchone()[0]
        conn.close()
        return count
