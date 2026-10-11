"""
robots_checker.py - robots.txt compliance checker.

Respects website crawling policies by default, with option to override.
Tracks blocked URLs for evidence reporting in the Policy Evidence Ladder.
"""

import logging
from typing import Dict, Optional, List
from urllib.parse import urlparse, urljoin

import requests
from robotexclusionrulesparser import RobotExclusionRulesParser

from .models import Config

logger = logging.getLogger(__name__)


class RobotsChecker:
    """
    Checks robots.txt compliance for URLs.
    
    Caches robots.txt files per domain to avoid repeated fetches.
    Tracks blocked URLs for evidence reporting.
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.cache: Dict[str, Optional[RobotExclusionRulesParser]] = {}
        self.user_agent = config.user_agent
        self.blocked_urls: List[str] = []  # Track blocked URLs for evidence
    
    def _get_robots_url(self, url: str) -> str:
        """Get the robots.txt URL for a given URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    
    def _fetch_robots(self, url: str) -> Optional[RobotExclusionRulesParser]:
        """Fetch and parse robots.txt for a domain."""
        robots_url = self._get_robots_url(url)
        
        try:
            response = requests.get(
                robots_url,
                timeout=10,
                headers={"User-Agent": self.user_agent}
            )
            
            if response.status_code == 200:
                parser = RobotExclusionRulesParser()
                parser.parse(response.text)
                logger.debug(f"Loaded robots.txt from {robots_url}")
                return parser
            else:
                # No robots.txt or error - assume allowed
                logger.debug(f"No robots.txt at {robots_url} (status {response.status_code})")
                return None
                
        except Exception as e:
            # Only log at debug level - SSL errors are common and not critical
            logger.debug(f"Could not fetch robots.txt from {robots_url}: {e}")
            return None
    
    def _get_parser(self, url: str) -> Optional[RobotExclusionRulesParser]:
        """Get cached or fetch robots.txt parser for a URL."""
        parsed = urlparse(url)
        domain = parsed.netloc
        
        if domain not in self.cache:
            self.cache[domain] = self._fetch_robots(url)
        
        return self.cache[domain]
        self.blocked_urls: List[str] = []  # Track blocked URLs for evidence
    
    def is_allowed(self, url: str) -> bool:
        """
        Check if crawling a URL is allowed by robots.txt.
        
        Args:
            url: URL to check
            
        Returns:
            True if crawling is allowed (or if ignore_robots is set)
        """
        # If configured to ignore robots.txt
        if self.config.ignore_robots:
            return True
        
        parser = self._get_parser(url)
        
        # No robots.txt means allowed
        if parser is None:
            return True
        
        # Check if allowed for our user agent
        try:
            # Use a generic bot user agent for checking
            allowed = parser.is_allowed("*", url)
            
            if not allowed:
                logger.info(f"URL blocked by robots.txt: {url}")
                # Track blocked URL for evidence reporting
                if url not in self.blocked_urls:
                    self.blocked_urls.append(url)
            
            return allowed
            
        except Exception as e:
            logger.warning(f"Error checking robots.txt for {url}: {e}")
            return True  # Default to allowed on error
    
    def get_blocked_urls(self) -> List[str]:
        """Return list of URLs that were blocked by robots.txt."""
        return self.blocked_urls.copy()
    
    def get_blocked_policy_urls(self) -> List[str]:
        """Return list of blocked URLs that look like policy pages."""
        policy_patterns = ['/policies/', '/policy/', '/shipping', '/return', '/refund']
        return [url for url in self.blocked_urls 
                if any(p in url.lower() for p in policy_patterns)]
    
    def get_crawl_delay(self, url: str) -> Optional[float]:
        """
        Get the crawl delay specified in robots.txt.
        
        Args:
            url: URL to check
            
        Returns:
            Crawl delay in seconds, or None if not specified
        """
        if self.config.ignore_robots:
            return None
        
        parser = self._get_parser(url)
        
        if parser is None:
            return None
        
        try:
            delay = parser.get_crawl_delay("*")
            return float(delay) if delay else None
        except Exception:
            return None
    
    def get_sitemaps(self, url: str) -> list:
        """
        Get sitemap URLs from robots.txt.
        
        Args:
            url: Any URL from the domain
            
        Returns:
            List of sitemap URLs
        """
        parser = self._get_parser(url)
        
        if parser is None:
            # Try common sitemap locations
            parsed = urlparse(url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            return [
                f"{base}/sitemap.xml",
                f"{base}/sitemap_index.xml",
            ]
        
        try:
            sitemaps = parser.sitemaps or []
            return list(sitemaps)
        except Exception:
            return []
