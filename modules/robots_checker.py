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

from .models import Config, HONEST_USER_AGENT
from . import obs

logger = logging.getLogger(__name__)


def crawl_delay_for_all_agents(text: str) -> Optional[float]:
    """Crawl-delay of the `User-agent: *` group (the group is_allowed() reads), or None.

    Read here because robotexclusionrulesparser drops a group that has no Allow/Disallow line.
    """
    agents: List[str] = []
    in_agent_lines = False
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if ':' not in line:
            continue
        key, _, value = line.partition(':')
        key, value = key.strip().lower(), value.strip()
        if key == 'user-agent':
            if not in_agent_lines:
                agents = []
            agents.append(value.lower())
            in_agent_lines = True
            continue
        in_agent_lines = False
        if key == 'crawl-delay' and '*' in agents:
            try:
                delay = float(value)
            except ValueError:
                obs.swallowed("robots_checker.py:crawl_delay_for_all_agents", error_type="parse",
                              fallback="ignore this Crawl-delay line", stage="robots")
                continue
            return delay if delay > 0 else None
    return None


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
        self.unreachable: Dict[str, str] = {}  # netloc -> why robots.txt could not be read
        self.texts: Dict[str, str] = {}  # netloc -> robots.txt body (2xx only)

    def _get_robots_url(self, url: str) -> str:
        """Get the robots.txt URL for a given URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    
    def _fetch_robots(self, url: str) -> Optional[RobotExclusionRulesParser]:
        """Fetch and parse robots.txt for a domain (RFC 9309, section 2.3.1).

        2xx: the rules apply. 4xx ("unavailable"): no robots.txt, every URL is allowed.
        5xx or no answer at all ("unreachable"): every URL is disallowed for this run.
        """
        robots_url = self._get_robots_url(url)
        domain = urlparse(url).netloc
        timeout = min(10, self.config.timeout)
        timer = obs.Timer()

        try:
            response = requests.get(
                robots_url,
                timeout=timeout,
                headers={"User-Agent": self.user_agent}
            )
            if response.status_code in (403, 429):
                # Refused to the browser-like User-Agent: ask once more, saying who is asking.
                refused = response.status_code
                response = requests.get(robots_url, timeout=timeout,
                                        headers={"User-Agent": HONEST_USER_AGENT})
                obs.event("robots", "success" if 200 <= response.status_code < 300 else "fail",
                          kind="robots_honest_retry", url=robots_url, first_status=refused,
                          status=response.status_code, identity="honest User-Agent")
        except requests.exceptions.TooManyRedirects:
            # RFC 9309 2.3.1.2: more than five redirects MAY be treated as unavailable.
            obs.swallowed("robots_checker.py:_fetch_robots", error_type="http",
                          fallback="treat every URL as allowed (too many redirects = unavailable)",
                          stage="robots", url=robots_url)
            return None
        except Exception as e:
            obs.swallowed("robots_checker.py:_fetch_robots",
                          fallback="disallow every URL for this run (RFC 9309: unreachable)",
                          stage="robots", url=robots_url)
            if isinstance(e, requests.exceptions.Timeout):
                return self._disallow_all(domain, f"robots.txt not reachable (timeout after {timeout} s)")
            return self._disallow_all(domain, f"robots.txt not reachable ({type(e).__name__})")

        status = response.status_code
        ok = 200 <= status < 300
        obs.event("robots", "success" if ok else "fail",
                  duration_ms=timer.ms(),
                  error_type=None if ok else obs.classify_fetch(status, f"robots.txt status {status}"),
                  error_message=None if ok else f"robots.txt status {status}",
                  kind="robots_fetch", url=robots_url, status=status,
                  served_by="requests(direct, no rate limit, no cloudscraper)",
                  bytes=len(response.content or b""))

        if ok:
            parser = RobotExclusionRulesParser()
            parser.parse(response.text)
            self.texts[domain] = response.text
            logger.debug(f"Loaded robots.txt from {robots_url}")
            return parser
        if status >= 500:
            obs.degraded("robots_checker.py:_fetch_robots",
                         obs.classify_fetch(status, f"status {status}") or "http",
                         f"robots.txt answered {status}",
                         fallback="disallow every URL for this run (RFC 9309: unreachable)",
                         stage="robots", url=robots_url)
            return self._disallow_all(domain, f"robots.txt answered HTTP {status}")
        # 4xx (and any other non-2xx): no robots.txt, every URL is allowed.
        obs.degraded("robots_checker.py:_fetch_robots",
                     obs.classify_fetch(status, f"status {status}") or "http",
                     f"robots.txt answered {status}",
                     fallback="treat every URL as allowed (RFC 9309: unavailable)",
                     stage="robots", url=robots_url)
        logger.debug(f"No robots.txt at {robots_url} (status {status})")
        return None

    def _disallow_all(self, domain: str, reason: str) -> RobotExclusionRulesParser:
        """A parser that disallows every URL, for a robots.txt that could not be read."""
        self.unreachable[domain] = reason
        logger.warning(f"{reason}: every URL on {domain} is treated as disallowed (RFC 9309)")
        parser = RobotExclusionRulesParser()
        parser.parse("User-agent: *\nDisallow: /\n")
        return parser

    def unreachable_reason(self, url: str) -> Optional[str]:
        """Why every URL on this host is disallowed (robots.txt 5xx / no answer), or None."""
        self._get_parser(url)
        return self.unreachable.get(urlparse(url).netloc)

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
                obs.event("robots", "skip", kind="disallowed", url=url, rule_agent="*")
                logger.info(f"URL blocked by robots.txt: {url}")
                # Track blocked URL for evidence reporting
                if url not in self.blocked_urls:
                    self.blocked_urls.append(url)
            
            return allowed
            
        except Exception as e:
            obs.swallowed("robots_checker.py:is_allowed", error_type="parse", fallback="allowed",
                          stage="robots", url=url)
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
            return crawl_delay_for_all_agents(self.texts.get(urlparse(url).netloc, ""))
        except Exception:
            obs.swallowed("robots_checker.py:get_crawl_delay", error_type="parse", fallback="None",
                          stage="robots", url=url)
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
            obs.degraded("robots_checker.py:get_sitemaps", "parse", "no parsed robots.txt",
                         fallback="no declared sitemaps", stage="discovery", url=url)
            return []
        
        try:
            sitemaps = parser.sitemaps or []
            return list(sitemaps)
        except Exception:
            obs.swallowed("robots_checker.py:get_sitemaps", error_type="parse", fallback="[]",
                          stage="discovery", url=url)
            return []
