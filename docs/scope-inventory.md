# Scope inventory for Phase 2 decisions (read-only)

Line numbers refer to this commit. Nothing here was changed in Phase 1 except for adding obs log
calls next to the code listed.

Owner decisions already taken:

- **A3** - the bot-protection bypass stays as it is. Section 1 inventories it for documentation only.
- **B1** - the synthetic-data pricing model and the "ML" threat classifier will be removed or
  renamed to a plain scoring rubric. Section 2 says what actually runs; section 3 lists everything
  that depends on them.

## 1. Bot-protection evasion (A3: keep, document)

### 1.1 Code

| file:line | what it does |
|---|---|
| `modules/http_client.py:1-12` | Module docstring: "ANTI-BOT BYPASS HIERARCHY" (patchright -> playwright with stealth -> cloudscraper -> requests). |
| `modules/http_client.py:31-49` | Prefers `patchright` ("patches CDP leaks, bypasses Cloudflare/DataDome"), falls back to `playwright`. |
| `modules/http_client.py:51-56` | Optional `cloudscraper` import ("Cloudflare bypass without browser"). |
| `modules/http_client.py:103-108` | `PROTECTED_SITES` (lululemon.com, shop.lululemon.com, nike.com, adidas.com). |
| `modules/http_client.py:138-153` | `_create_cloudscraper()`: cloudscraper session posing as desktop Chrome on Windows. |
| `modules/http_client.py:155-189` | `_create_session()`: full browser header set (`sec-ch-ua`, `Sec-Fetch-*`, `Upgrade-Insecure-Requests`, Chrome 120 UA) "to look like real browser". |
| `modules/models.py:334` | Default `user_agent`: a desktop Chrome 120 string (no tool identification). |
| `modules/http_client.py:191-280` | `_init_playwright()`: launch flag `--disable-blink-features=AutomationControlled` (:206), real Chrome via `channel="chrome"` (:219, "better for bot detection"), context with `bypass_csp=True` (:241), `ignore_https_errors=True`, fixed locale/timezone, spoofed client-hint headers. |
| `modules/http_client.py:253-279` | Stealth init script when the engine is plain playwright: `navigator.webdriver` -> undefined (:257), fake `window.chrome`, fake `navigator.plugins`, fixed `navigator.languages`, patched `permissions.query`. |
| `modules/http_client.py:292-353` | `fetch()` fallback chains: default `requests -(403)-> cloudscraper`; `--render-js`: `browser -(403/error)-> cloudscraper -> placeholder`. |
| `modules/http_client.py:387-419` | `_fetch_with_cloudscraper()`. |
| `modules/http_client.py:421-454` | `_fetch_protected_site()`: returns synthetic HTML with status 200 and header `X-Bot-Protection: detected` for `PROTECTED_SITES`. |
| `modules/http_client.py:523-580` | `_fetch_with_playwright()`; on `net::ERR_*` falls back to a plain requests fetch (:569-576). |
| `main.py:479-487` | Recognises the placeholder page and records "Site has bot protection" while continuing to extract from it. |
| `main.py:11`, `main.py:964` | `--ignore-robots` (docstring example and CLI flag); `main.py:1020` reads `ignore_robots` from config too. |
| `modules/robots_checker.py:102-104` | `is_allowed()` returns True for every URL when `ignore_robots` is set; `get_crawl_delay()` (:142) also returns None. |
| `main.py:1106-1108` | Site-level robots check skipped when `ignore_robots` is set. |
| `config.example.yaml:20` | `ignore_robots: false  # Ignore robots.txt restrictions`. |

Adjacent but not evasion: `_fetch_with_requests()` retries with `verify=False` on SSL errors
(`http_client.py:489-506`).

### 1.2 Dependencies

| requirement | line | used by |
|---|---|---|
| `patchright` | `requirements.txt:24-27` (commented out, "RECOMMENDED ... for bot detection bypass") | `http_client.py:33` when installed (installed by START.ps1 / START.sh / setup.ps1, not by requirements.txt) |
| `playwright>=1.40.0` | `requirements.txt:29-30` | `http_client.py:42` (fallback engine; it is the engine in this venv) |
| `cloudscraper>=1.2.71` | `requirements.txt:32-33` ("Cloudflare bypass for non-browser requests") | `http_client.py:53` |

### 1.3 Documentation and scripts

| file:line | text |
|---|---|
| `README.md:233` | "No bypassing of crawl restrictions" (contradicts :260-266) |
| `README.md:241` | `http_client.py      # HTTP client with anti-bot bypass` |
| `README.md:260-266` | "Anti-Bot Technology ... advanced anti-bot bypass capabilities: Patchright - bypasses Cloudflare, DataDome; Cloudscraper - Cloudflare challenge solver; Stealth Mode - Real browser fingerprinting" |
| `README.md:319-320` | `pip install patchright` / `patchright install chrome` |
| `README.md:328` | "Site has bot protection ... Tool will try fallback methods automatically" |
| `README.md:354` | Acknowledgment: "Patchright - Anti-bot browser automation" |
| `README.md:366` | "does not bypass access restrictions" (contradicts :260-266) |
| `POWERSHELL_GUIDE.md:293` | `python main.py --sites sites.txt --ignore-robots` |
| `START.ps1:372-387` | Step 6 "Install Patchright for Anti-Bot Bypass ... bypasses Cloudflare, DataDome"; installs cloudscraper "as fallback" |
| `START.sh:216-223` | Same as START.ps1 |
| `setup.ps1:77-87` | "Installing Patchright for anti-bot bypass ... bypasses Cloudflare/DataDome"; "Cloudscraper installed (Cloudflare fallback)" |
| `requirements.txt:24-33` | comments quoted in 1.2 |
| `docs/history/ANTI_BOT_BYPASS_GUIDE.md` (whole file, 150 lines) | v14 guide: Patchright "RECOMMENDED", cloudscraper, "Detection Methods Bypassed" (:68), expected results before/after |
| `docs/history/README_v16_package.md:20-23` | "Anti-Bot Bypass (NEW in v15): Patchright ... Cloudscraper ... Stealth Mode" |
| `docs/history/README_v16_package.md:153, 190, 298, 305-306` | "Instead of bypassing restrictions ..."; `--ignore-robots`; "CAPTCHAs: Not bypassed"; "No login bypass", "No CAPTCHA solving" |
| `docs/history/V15_RELEASE_NOTES.md:67, 129, 135` | "Respects robots.txt by default (no bypassing)", "Never bypasses crawling restrictions", "Tool does NOT bypass the restriction" |
| `docs/history/ANALYSIS_AND_FIXES.md:90, 297` | "Option B: Add `--ignore-robots` Flag Usage"; `.\run.ps1 -AI -RenderJS -IgnoreRobots` (run.ps1 has no `-IgnoreRobots` parameter) |

## 2. "AI" / "ML" wording vs. what runs

### 2.1 What actually runs

| component | file:line | what it is |
|---|---|---|
| `ChineseInsightGenerator` | `modules/ai_analyzer.py:178-338` | A real LLM call: `ollama.chat` with a Chinese prompt built from the scan; the reply is split on `##` headings into key insights / recommendations / threat text / pricing text. If Ollama is down or replies empty, a two-line template is returned and is still shown under the "AI" headings. |
| `CompetitiveAnalyzer` | `:341-401` | A second LLM call for brand positioning; `compare_competitors()` is never called. |
| `PricingPredictor` ("ML-based pricing strategy prediction") | `:404-532` | At every start-up, fits an `XGBRegressor` (or `RandomForestRegressor` without xgboost) on 500 rows of `np.random` data (seed 42, :457) whose target is the fixed formula `price * (0.85 + 0.2 * brand_strength) + tier * 5 - free_shipping * 3` (:470). It is then called with `category_tier=2` and `brand_strength=0.5` always (defaults, :484-485) and `has_free_shipping` always False (reads a key `to_dict()` never has, :776). The output is therefore approximately `0.95 * competitor_median + 10`: measured 24 -> 32.08 (formula 32.80), 31.5 -> 39.58 (39.92), 38 -> 44.05 (46.10), 120 -> 122.26 (124.00); "low" and "high" are that value x0.9 and x1.15. `save_model()` is never called, so `data/pricing_model.pkl` only exists if someone puts it there, and then it is unpickled. |
| `ThreatScorer` ("Score competitor threat level using ML classification") | `:535-700` | No model. A weighted sum of six hand-set factor scores (platform, price tier, count of marketing flags, review/payment flags, shipping threshold, brand signals), rounded to 1-10, with a Chinese explanation from fixed strings. `GradientBoostingClassifier` and `LabelEncoder` are imported (:33-34) and never used; `threat_model_path` (:63) is never read. |
| `InsightGenerator` (no `--ai`) | `modules/insight_generator.py:20-332` | Rule-based Chinese bullet templates; not labelled AI in report.md, but its output is what business_report.md's methodology calls "AI-powered insight generation using Qwen2.5 LLM". |

The AI stage only runs with `--ai` **and** a reachable Ollama with the model pulled (main.py:1036-1057);
otherwise it is skipped for every site (one console warning). AI output is attached to the
in-memory object after the snapshot is saved, so it is never stored.

### 2.2 Where the repo calls something AI or ML

| file:line | wording | what runs there |
|---|---|---|
| `README.md:7` | badge "AI-Qwen2.5" | - |
| `README.md:23-27` | "AI-Powered Analysis: Local AI analysis using Qwen2.5; Competitive threat scoring (1-10 scale); Pricing strategy recommendations; Key insights generation" | LLM call for insights; threat = rubric; pricing = synthetic-data XGBoost |
| `README.md:63` | "8GB recommended for AI" | - |
| `README.md:84-95, 108-115, 124` | "Enable AI Analysis", `--ai` = "Enable AI-powered analysis" | Ollama + rubric + synthetic model |
| `README.md:171` | business report structure lists "AI insights" | LLM key insights (only with Ollama) |
| `README.md:246` | `ai_analyzer.py       # AI-powered analysis` | |
| `README.md:355-356` | acknowledgments: Ollama "Local AI inference", Qwen2.5 "AI model for analysis" | |
| `docs/history/README_v16_package.md:14-17` | "AI-Powered Analysis ... Pricing Prediction: ML-based optimal pricing recommendations; Threat Scoring: Automated competitor threat assessment" | synthetic XGBoost; rubric |
| `docs/history/README_v16_package.md:165-168` | report sections "AI-generated bullet points", threat score, pricing advice | |
| `QUICKSTART.md:11-12, 31-32, 56, 83, 96-97` | "Install Ollama AI", "Qwen2.5 AI model", "AI features not working ... rule-based analysis instead" | |
| `POWERSHELL_GUIDE.md:11, 53, 74-75, 116-161, 304-311` | "Enabling AI Analysis", "Enable AI-powered analysis" | |
| `START.ps1:10, 36, 47, 216-223, 322-368, 465-469, 541` | "AI-Powered Analysis for Cross-Border Sellers"; "[AI] AI Analysis: ENABLED (Qwen2.5)" printed when the flag is passed, before main.py checks Ollama | |
| `START.sh:10-12, 42-73, 91, 167-205, 292-295, 340` | same as START.ps1 | |
| `setup.ps1:6, 102-164`, `run.ps1:8-9, 21-23, 84-99` | "AI components", "Enable AI-powered analysis" | |
| `requirements.txt:52-60` | "AI/ML Dependencies (for AI-powered analysis)"; "Machine Learning for pricing prediction: scikit-learn, xgboost" | |
| `main.py:971` | `--ai` help: "Enable AI-powered analysis with Ollama/Qwen2.5" | |
| `main.py:1056` | "Install with: pip install ollama scikit-learn xgboost" | |
| `modules/ai_analyzer.py:2-8` | "AI-powered analysis using local LLMs and ML models ... Pricing strategy prediction via scikit-learn/XGBoost; Competitor threat scoring via custom classifier" | |
| `modules/ai_analyzer.py:61` | "Model paths for saved ML models" | |
| `modules/ai_analyzer.py:406` | "ML-based pricing strategy prediction using scikit-learn and XGBoost" | |
| `modules/ai_analyzer.py:537` | "Score competitor threat level using ML classification" | rubric |
| `modules/report_writer.py:36-38, 89-91` | "AI-Powered Analysis", "Key Insights (AI Analysis)" / "关键洞察 (AI分析)", "Actionable Recommendations (AI)" / "可复制的动作建议 (AI推荐)" | LLM output, or the template fallback when the LLM call failed |
| `modules/report_writer.py:236` | banner "🤖 **AI-Powered Analysis** (Qwen2.5)" above the threat and pricing sections | threat (:256-267) = rubric; pricing (:269-278) = synthetic XGBoost; positioning (:280-285) = LLM |
| `modules/business_report.py:575` | "Analysis: AI-powered insight generation using Qwen2.5 LLM" | printed on every run, AI or not |
| `modules/business_report.py:354-363` | "Key Insights" from `ai_insights` (unlabelled) | LLM or template |

## 3. What depends on the pricing model and the threat score (B1)

| kind | where | dependency |
|---|---|---|
| Code | `modules/ai_analyzer.py:404-532` `PricingPredictor`, `:535-700` `ThreatScorer` | the components themselves |
| Code | `modules/ai_analyzer.py:719-722` | `AIAnalyzer.__init__` builds both (the pricing model is trained here, on every `--ai` run) |
| Code | `modules/ai_analyzer.py:764-800` | `analyze_site()` fills `results['pricing']` and `results['threat']` |
| Code | `main.py:1155-1157` | copies them to `intel.ai_pricing` / `intel.ai_threat` |
| Code | `modules/__init__.py:31-36, 61-62` | exports `AIAnalyzer`, `AIConfig`, `create_analyzer`, `AI_AVAILABLE` (imported on every run, so numpy is imported on every run) |
| Report | `modules/report_writer.py:256-267` | report.md "Competitive Threat Assessment": score /10 + rubric explanation lines |
| Report | `modules/report_writer.py:269-278` | report.md "Pricing Strategy Recommendations": competitor median, suggested low / optimal / high |
| Report | `modules/report_writer.py:39-40, 76-80, 92-93, 129-133` | translation keys `threat_assessment`, `threat_score`, `*_threat`, `threat_factors`, `pricing_strategy`, `suggested_*`, `competitor_median` |
| Report | report.csv, business_report.md | no pricing or threat output (business_report's SWOT "Threats" is fixed text, unrelated) |
| Prompt | `modules/ai_analyzer.py:265-269`, `:315-318` | the LLM prompt asks for "竞争威胁评估 ... 评分1-10" and "定价策略建议"; `_parse_response` stores them as `threat_analysis` / `pricing_advice`, which nothing prints |
| Docs | `README.md:25-26`, `docs/history/README_v16_package.md:16-17, 167-168`, `requirements.txt:58-60`, `modules/ai_analyzer.py:2-8, 61, 406, 537` | "threat scoring", "ML-based pricing", "Machine Learning for pricing prediction" |
| Config keys | `modules/ai_analyzer.py:58-59` | `enable_pricing_prediction`, `enable_threat_scoring` |
| Config keys | `modules/ai_analyzer.py:62-63` | `pricing_model_path = "data/pricing_model.pkl"` (read if present, never written), `threat_model_path = "data/threat_model.pkl"` (never read) |
| Config keys | `.gitignore` | `data/*.pkl` (added in this phase for those paths) |
| Requirements | `scikit-learn>=1.3.0` (`requirements.txt:59`) | only `ai_analyzer.py:33-34` (and only `RandomForestRegressor`, `StandardScaler` are used) |
| Requirements | `xgboost>=2.0.0` (`requirements.txt:60`) | only `ai_analyzer.py:41` |
| Requirements | `numpy>=1.24.0` (`requirements.txt:63`) | only `ai_analyzer.py:18` (synthetic data and the feature array). Nothing else imports numpy; it would remain installed as a dependency of anything else that needs it, but no project code would need it. |
| Tests | none | no test imports `ai_analyzer` or checks pricing/threat output. All tests import `modules`, which imports `ai_analyzer`; an `ImportError` there is caught (`AI_AVAILABLE = False`). `tests/test_obs.py` audits every `modules/*.py` file's except handlers, so it follows whatever files exist. |
| Observability | `modules/ai_analyzer.py` obs calls added in Phase 1 (`pricing_model_trained`, notes `ai_pricing`, `ai_threat`) and `main.py:1160-1163` field events | will need the same rename/removal |

The LLM parts (`OllamaClient`, `ChineseInsightGenerator`, `CompetitiveAnalyzer`, `ollama` requirement)
are not covered by B1.

## 4. Requirements that nothing imports

Checked by searching `main.py`, `modules/`, `tests/`, `scripts/` for imports of each package.

| requirement | line | status |
|---|---|---|
| `html5lib>=1.1` | 8 | never imported; BeautifulSoup is only given `'lxml'` and `'html.parser'` |
| `pandas>=2.1.0` | 19 | never imported |
| `sqlite-utils>=3.35.0` | 22 | never imported (`snapshot_store.py` uses stdlib `sqlite3`) |
| `python-dateutil>=2.8.2` | 40 | never imported |
| `html2text>=2024.2.26` | 43 | never imported |
| `ratelimit>=2.2.1` | 46 | never imported (`RateLimiter` is hand-written in http_client.py) |
| `deepdiff>=6.7.0` | 49 | imported (`snapshot_store.py:15`) but `DeepDiff` is never used |
| `numpy`, `scikit-learn`, `xgboost` | 59-63 | used only by the B1 components (section 3) |

Everything else is imported: requests, beautifulsoup4, lxml (as the bs4 parser), urllib3,
tldextract, robotexclusionrulesparser, pyyaml, playwright, cloudscraper, click, rich, ollama.
`patchright` is not in requirements.txt (commented out) but is preferred when installed.
