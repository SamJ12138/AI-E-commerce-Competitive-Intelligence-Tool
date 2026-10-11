"""
http_client.py - HTTP client with rate limiting, retries, and error handling.

Provides a robust HTTP client that respects rate limits, handles common errors,
and supports JavaScript rendering via Patchright (preferred) or Playwright.

ANTI-BOT BYPASS HIERARCHY:
1. Patchright - Best for Cloudflare, DataDome, etc. (patches CDP leaks)
2. Playwright with stealth - Fallback if Patchright unavailable
3. Cloudscraper - For simple Cloudflare challenges without browser
4. Requests - Basic HTTP for unprotected sites
"""

import time
import logging
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, urljoin
import ssl
import warnings

# Suppress noisy urllib3 retry warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

# Try Patchright first (best for bot detection bypass)
try:
    from patchright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PATCHRIGHT_AVAILABLE = True
    PLAYWRIGHT_AVAILABLE = True
    BROWSER_ENGINE = "patchright"
    logger_msg = "Patchright (anti-bot) available"
except ImportError:  # obs: import-time, reported by HttpClient.__init__
    PATCHRIGHT_AVAILABLE = False
    # Fallback to standard Playwright
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
        PLAYWRIGHT_AVAILABLE = True
        BROWSER_ENGINE = "playwright"
        logger_msg = "Playwright available (consider installing patchright for better bot bypass)"
    except ImportError:  # obs: import-time, reported by HttpClient.__init__
        PLAYWRIGHT_AVAILABLE = False
        BROWSER_ENGINE = None
        logger_msg = "No browser automation available"

# Try Cloudscraper for Cloudflare bypass without browser
try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:  # obs: import-time, reported by HttpClient.__init__
    CLOUDSCRAPER_AVAILABLE = False

from .models import Config
from . import obs

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple per-domain rate limiter."""
    
    def __init__(self, delay: float = 1.5):
        self.delay = delay
        self.last_request: Dict[str, float] = {}
    
    def wait(self, domain: str) -> None:
        """Wait if necessary before making a request to the domain."""
        now = time.time()
        if domain in self.last_request:
            elapsed = now - self.last_request[domain]
            if elapsed < self.delay:
                sleep_time = self.delay - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s for {domain}")
                time.sleep(sleep_time)
        self.last_request[domain] = time.time()


class HttpClient:
    """
    HTTP client with robust error handling and anti-bot bypass capabilities.
    
    Features:
    - Automatic retries with exponential backoff
    - Rate limiting per domain
    - Anti-bot bypass via Patchright (best) or Playwright
    - Cloudscraper fallback for Cloudflare
    - Custom headers to avoid bot detection
    - SSL error handling
    
    ANTI-BOT HIERARCHY:
    1. Patchright - Patches CDP leaks, bypasses Cloudflare/DataDome
    2. Playwright with stealth - Standard browser automation with stealth
    3. Cloudscraper - Cloudflare bypass without browser
    4. Requests - Basic HTTP
    """
    
    # Sites known to have strong bot protection - need special handling
    PROTECTED_SITES = [
        'lululemon.com',
        'shop.lululemon.com',
        'nike.com',
        'adidas.com',
    ]
    
    def __init__(self, config: Config):
        self.config = config
        self.rate_limiter = RateLimiter(config.rate_limit_delay)
        self.session = self._create_session()
        self.cloudscraper_session = self._create_cloudscraper() if CLOUDSCRAPER_AVAILABLE else None
        self._playwright = None
        self._browser = None
        self._context = None
        self._served_by_override = None
        
        # Log which browser engine is being used
        if BROWSER_ENGINE:
            logger.info(f"Browser engine: {BROWSER_ENGINE}")
        if CLOUDSCRAPER_AVAILABLE:
            logger.info("Cloudscraper available for Cloudflare bypass")
        obs.event("fetch", "success", kind="client_init", browser_engine=BROWSER_ENGINE,
                  patchright_available=PATCHRIGHT_AVAILABLE, playwright_available=PLAYWRIGHT_AVAILABLE,
                  cloudscraper_available=CLOUDSCRAPER_AVAILABLE,
                  cloudscraper_session=self.cloudscraper_session is not None,
                  render_js=config.render_js, rate_limit_delay=config.rate_limit_delay)
        if not PATCHRIGHT_AVAILABLE:
            obs.degraded("http_client.py:<import>", "unknown",
                         "patchright not importable", fallback=f"browser engine = {BROWSER_ENGINE}",
                         stage="fetch")
        if not CLOUDSCRAPER_AVAILABLE:
            obs.degraded("http_client.py:<import>", "unknown",
                         "cloudscraper not importable", fallback="no cloudscraper branch", stage="fetch")
    
    def _create_cloudscraper(self):
        """Create a cloudscraper session for Cloudflare bypass."""
        try:
            scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True
                }
            )
            return scraper
        except Exception as e:
            obs.swallowed("http_client.py:_create_cloudscraper", fallback="cloudscraper_session=None",
                          stage="fetch")
            logger.warning(f"Failed to create cloudscraper: {e}")
            return None
    
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic."""
        session = requests.Session()
        
        # Configure retries
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set default headers - more complete to look like real browser
        session.headers.update({
            "User-Agent": self.config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        })
        
        return session
    
    def _init_playwright(self) -> None:
        """Initialize browser for anti-bot bypass (Patchright or Playwright)."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "No browser automation available. Install with:\n"
                "  pip install patchright && patchright install chrome  (RECOMMENDED)\n"
                "  OR: pip install playwright && playwright install chromium"
            )
        
        if self._playwright is None:
            self._playwright = sync_playwright().start()
            
            # Patchright-optimized launch settings
            # Use real Chrome instead of Chromium for better stealth
            launch_args = [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-infobars',
                '--window-size=1920,1080',
                '--start-maximized',
                '--disable-extensions',
            ]
            
            # Try to use real Chrome first (better for bot detection)
            try:
                self._browser = self._playwright.chromium.launch(
                    channel="chrome",  # Use real Chrome, not Chromium
                    headless=True,
                    args=launch_args
                )
                logger.info(f"Browser initialized: Chrome via {BROWSER_ENGINE}")
                obs.event("fetch", "success", kind="browser_init", channel="chrome", engine=BROWSER_ENGINE)
            except Exception as e:
                # Fallback to Chromium
                obs.swallowed("http_client.py:_init_playwright", fallback="bundled Chromium",
                              stage="fetch")
                logger.warning(f"Chrome not available, using Chromium: {e}")
                self._browser = self._playwright.chromium.launch(
                    headless=True,
                    args=launch_args
                )
                logger.info(f"Browser initialized: Chromium via {BROWSER_ENGINE}")
            
            # Context with stealth settings
            self._context = self._browser.new_context(
                user_agent=self.config.user_agent,
                viewport={"width": 1920, "height": 1080},
                java_script_enabled=True,
                bypass_csp=True,
                ignore_https_errors=True,
                locale='en-US',
                timezone_id='America/New_York',
                extra_http_headers={
                    'Accept-Language': 'en-US,en;q=0.9',
                    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"',
                }
            )
            
            # Add stealth scripts (not needed for Patchright but helps Playwright)
            if BROWSER_ENGINE == "playwright":
                self._context.add_init_script("""
                    // Mask webdriver
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    
                    // Mask automation flags
                    window.chrome = { runtime: {} };
                    
                    // Mask plugins
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    
                    // Mask languages
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                    
                    // Override permissions
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission }) :
                            originalQuery(parameters)
                    );
                """)
            logger.info("Playwright browser initialized")
    
    def close(self) -> None:
        """Clean up resources."""
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self.session.close()
    
    def fetch(
        self,
        url: str,
        render_js: Optional[bool] = None
    ) -> Tuple[Optional[str], int, Dict[str, str], Optional[str]]:
        """
        Fetch a URL and return (html_content, status_code, headers, error).
        
        Args:
            url: URL to fetch
            render_js: Override config.render_js for this request
        
        Returns:
            Tuple of (html_content, status_code, response_headers, error_message)
            If error, html_content will be None and error_message will be set.
        """
        use_js = render_js if render_js is not None else self.config.render_js
        parsed = urlparse(url)
        domain = parsed.netloc
        
        # Check if this is a protected site that needs special handling
        is_protected = any(site in domain for site in self.PROTECTED_SITES)
        
        # Apply rate limiting
        timer = obs.Timer()
        self.rate_limiter.wait(domain)
        wait_ms = timer.ms()
        chain = []

        if use_js:
            result = self._attempt('browser', self._fetch_with_playwright, url, chain)

            # If failed (403 or error), try fallback strategies
            if result[1] == 403 or result[3]:
                logger.info(f"Browser fetch failed for {domain}, trying fallbacks...")

                # Fallback 1: Try cloudscraper for Cloudflare bypass
                if CLOUDSCRAPER_AVAILABLE and self.cloudscraper_session:
                    logger.info(f"Trying cloudscraper for {domain}")
                    result = self._attempt('cloudscraper', self._fetch_with_cloudscraper, url, chain)
                    if result[0] and not result[3]:
                        self._log_fetch(url, result, chain, use_js, is_protected, wait_ms, timer)
                        return result

                # Fallback 2: For protected sites, return placeholder
                if is_protected:
                    logger.info(f"Protected site {domain}, returning placeholder")
                    result = self._attempt('placeholder', self._fetch_protected_site, url, chain)

            self._log_fetch(url, result, chain, use_js, is_protected, wait_ms, timer)
            return result
        else:
            # Try regular requests first
            result = self._attempt('requests', self._fetch_with_requests, url, chain)

            # If 403, try cloudscraper
            if result[1] == 403 and CLOUDSCRAPER_AVAILABLE and self.cloudscraper_session:
                logger.info(f"Requests got 403, trying cloudscraper for {domain}")
                result = self._attempt('cloudscraper', self._fetch_with_cloudscraper, url, chain)

            self._log_fetch(url, result, chain, use_js, is_protected, wait_ms, timer)
            return result

    def _attempt(self, branch: str, fn, url: str, chain: list):
        """Run one fetch branch and append what it returned to chain (logging only)."""
        timer = obs.Timer()
        self._served_by_override = None
        result = fn(url)
        html, status, headers, error = result
        chain.append({
            'branch': branch,
            'served_by': self._served_by_override or branch,
            'status': status,
            'bytes': len(html.encode('utf-8', 'replace')) if html else 0,
            'error': error,
            'duration_ms': round(timer.ms(), 2),
        })
        return result

    def _log_fetch(self, url, result, chain, use_js, is_protected, wait_ms, timer) -> None:
        """One 'fetch' event per fetch() call: which branch served it, status, bytes."""
        html, status, headers, error = result
        last = chain[-1] if chain else {}
        obs.event(
            "fetch", "success" if (html and not error) else "fail",
            duration_ms=timer.ms(),
            error_type=obs.classify_fetch(status, error) if error else (None if html else "http"),
            error_message=error if error else (None if html else "Empty response"),
            url=url, status=status, served_by=last.get('served_by'),
            bytes=last.get('bytes', 0), chain=chain, render_js=use_js,
            protected_site=is_protected, rate_limit_wait_ms=round(wait_ms, 2),
            caller_stage=obs.current_stage(),
            server_header=(headers or {}).get('Server') or (headers or {}).get('server'),
        )
    
    def _fetch_with_cloudscraper(
        self,
        url: str
    ) -> Tuple[Optional[str], int, Dict[str, str], Optional[str]]:
        """Fetch using cloudscraper for Cloudflare bypass."""
        try:
            response = self.cloudscraper_session.get(
                url,
                timeout=self.config.timeout,
                allow_redirects=True
            )
            
            headers = dict(response.headers)
            
            if response.status_code == 403:
                return None, 403, headers, "Cloudscraper blocked (403)"
            if response.status_code == 404:
                return None, 404, headers, "Page not found (404)"
            
            response.encoding = response.apparent_encoding or 'utf-8'
            logger.info(f"Cloudscraper succeeded for {url}")
            return response.text, response.status_code, headers, None

        except Exception as e:
            obs.swallowed("http_client.py:_fetch_with_cloudscraper", fallback="returned (None, 0, {}, error)",
                          stage="fetch", url=url)
            # Only log at debug level for common SSL errors
            error_str = str(e)
            if 'SSL' in error_str or 'timeout' in error_str.lower():
                logger.debug(f"Cloudscraper failed for {urlparse(url).netloc}: {type(e).__name__}")
            else:
                logger.info(f"Cloudscraper failed: {type(e).__name__}")
            return None, 0, {}, f"Cloudscraper error: {str(e)}"
    
    def _fetch_protected_site(
        self,
        url: str
    ) -> Tuple[Optional[str], int, Dict[str, str], Optional[str]]:
        """
        Special handling for sites with strong bot protection.
        Returns minimal data with explanation rather than error.
        """
        parsed = urlparse(url)
        domain = parsed.netloc
        
        # Create a placeholder response explaining the limitation
        logger.warning(f"Site {domain} has strong bot protection - limited data available")
        obs.degraded("http_client.py:_fetch_protected_site", "blocked",
                     "PROTECTED_SITES match: synthetic placeholder HTML returned with status 200",
                     fallback="placeholder page", stage="fetch", event_name="fail", url=url)
        
        # Return a minimal HTML response that explains the situation
        # This allows the tool to continue without crashing
        placeholder_html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>{domain}</title></head>
        <body>
            <h1>{domain}</h1>
            <p>This site has strong bot protection that prevents automated access.</p>
            <p>Manual analysis recommended for this competitor.</p>
            <meta name="platform" content="protected">
            <meta name="note" content="Bot protection detected - limited automated data available">
        </body>
        </html>
        """
        
        return placeholder_html, 200, {'X-Bot-Protection': 'detected'}, None
    
    def _fetch_with_requests(
        self,
        url: str
    ) -> Tuple[Optional[str], int, Dict[str, str], Optional[str]]:
        """Fetch using requests library."""
        try:
            # Suppress SSL warnings for self-signed certs
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                response = self.session.get(
                    url,
                    timeout=self.config.timeout,
                    verify=True,  # Will retry with verify=False if needed
                    allow_redirects=True
                )
            
            headers = dict(response.headers)
            
            # Check for common blocks
            if response.status_code == 403:
                return None, 403, headers, "Access forbidden (403)"
            if response.status_code == 404:
                return None, 404, headers, "Page not found (404)"
            if response.status_code == 429:
                return None, 429, headers, "Rate limited (429)"
            
            response.raise_for_status()
            
            # Handle encoding
            response.encoding = response.apparent_encoding or 'utf-8'
            
            return response.text, response.status_code, headers, None
            
        except requests.exceptions.SSLError as e:
            obs.swallowed("http_client.py:_fetch_with_requests", error_type="http",
                          fallback="retry with verify=False", stage="fetch", url=url)
            logger.debug(f"SSL error for {url}, retrying without verification")
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    response = self.session.get(
                        url,
                        timeout=self.config.timeout,
                        verify=False,
                        allow_redirects=True
                    )
                return response.text, response.status_code, dict(response.headers), None
            except Exception as e2:
                obs.swallowed("http_client.py:_fetch_with_requests", error_type="http",
                              fallback="returned (None, 0, {}, error)", stage="fetch", url=url)
                return None, 0, {}, f"SSL error: {str(e2)}"

        except requests.exceptions.Timeout:
            obs.swallowed("http_client.py:_fetch_with_requests", error_type="timeout",
                          fallback="returned (None, 0, {}, error)", stage="fetch", url=url)
            return None, 0, {}, f"Timeout after {self.config.timeout}s"

        except requests.exceptions.ConnectionError as e:
            obs.swallowed("http_client.py:_fetch_with_requests", error_type="http",
                          fallback="returned (None, 0, {}, error)", stage="fetch", url=url)
            return None, 0, {}, f"Connection error: {str(e)}"

        except requests.exceptions.RequestException as e:
            obs.swallowed("http_client.py:_fetch_with_requests", error_type="http",
                          fallback="returned (None, 0, {}, error)", stage="fetch", url=url)
            return None, 0, {}, f"Request error: {str(e)}"
    
    def _fetch_with_playwright(
        self,
        url: str
    ) -> Tuple[Optional[str], int, Dict[str, str], Optional[str]]:
        """Fetch using Playwright for JavaScript rendering."""
        try:
            self._init_playwright()
            
            page = self._context.new_page()
            
            try:
                # Use longer timeout (60s) and domcontentloaded instead of networkidle
                # networkidle can hang on sites with continuous background requests
                response = page.goto(
                    url,
                    timeout=60000,  # 60 seconds
                    wait_until="domcontentloaded"
                )
                
                # Wait for common content indicators
                try:
                    # Try to wait for main content to appear
                    page.wait_for_selector('body', timeout=5000)
                    # Additional wait for dynamic content
                    page.wait_for_timeout(3000)
                except:
                    obs.swallowed("http_client.py:_fetch_with_playwright", fallback="wait 2s and read the page anyway",
                                  stage="fetch", url=url)
                    # If selector wait fails, just continue
                    page.wait_for_timeout(2000)
                
                status = response.status if response else 200
                headers = dict(response.headers) if response else {}
                
                # Get the rendered HTML
                html = page.content()
                
                return html, status, headers, None
                
            finally:
                page.close()
                
        except PlaywrightTimeout:
            obs.swallowed("http_client.py:_fetch_with_playwright", error_type="timeout",
                          fallback="returned (None, 0, {}, error)", stage="fetch", url=url)
            return None, 0, {}, f"Playwright timeout after 60s"
        except Exception as e:
            error_msg = str(e)
            # Handle HTTP/2 protocol errors by falling back to requests
            if any(err in error_msg for err in ['HTTP2_PROTOCOL_ERROR', 'ERR_HTTP2', 'net::ERR_']):
                obs.swallowed("http_client.py:_fetch_with_playwright", error_type="http",
                              fallback="plain requests fetch", stage="fetch", url=url)
                logger.debug(f"Playwright network error for {url}, using fallback")
                self._served_by_override = 'browser->requests'
                return self._fetch_with_requests(url)
            obs.swallowed("http_client.py:_fetch_with_playwright",
                          fallback="returned (None, 0, {}, error)", stage="fetch", url=url)
            return None, 0, {}, f"Playwright error: {error_msg}"
    
    def fetch_and_parse(
        self,
        url: str,
        render_js: Optional[bool] = None
    ) -> Tuple[Optional[BeautifulSoup], int, Optional[str]]:
        """
        Fetch URL and return parsed BeautifulSoup object.
        
        Returns:
            Tuple of (soup, status_code, error_message)
        """
        html, status, headers, error = self.fetch(url, render_js)
        
        if error:
            return None, status, error
        
        if not html:
            obs.degraded("http_client.py:fetch_and_parse", "http", "empty body with no error",
                         fallback="returned (None, status, 'Empty response')", stage="fetch",
                         event_name="fail", url=url, status=status)
            return None, status, "Empty response"
        
        try:
            # Use lxml for speed, fall back to html.parser
            try:
                soup = BeautifulSoup(html, 'lxml')
            except Exception:
                obs.swallowed("http_client.py:fetch_and_parse", error_type="parse",
                              fallback="html.parser", stage="fetch", url=url)
                soup = BeautifulSoup(html, 'html.parser')

            return soup, status, None

        except Exception as e:
            obs.swallowed("http_client.py:fetch_and_parse", error_type="parse",
                          fallback="returned (None, status, error)", stage="fetch", url=url)
            return None, status, f"HTML parsing error: {str(e)}"
    
    def head(self, url: str) -> Tuple[int, Dict[str, str], Optional[str]]:
        """
        Make a HEAD request to check URL status.
        
        Returns:
            Tuple of (status_code, headers, error_message)
        """
        parsed = urlparse(url)
        self.rate_limiter.wait(parsed.netloc)
        
        try:
            response = self.session.head(
                url,
                timeout=self.config.timeout,
                allow_redirects=True
            )
            return response.status_code, dict(response.headers), None
        except Exception as e:
            obs.swallowed("http_client.py:head", fallback="returned (0, {}, error)", stage="fetch", url=url)
            return 0, {}, str(e)
