import logging
import os
import json
import re
import glob
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

log = logging.getLogger(__name__)

HEADLESS_MODE = True
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
CONSENT_CLICK_TIMEOUT = 10000
PAGE_NAVIGATION_TIMEOUT = 15000
FINAL_URL_TIMEOUT = 15000

CONSENT_BUTTON_SELECTORS = [
    'button[aria-label="Accept all"]',
    'button:has-text("Accept all")',
    'button:has-text("Agree")'
]

GOOGLE_DOMAINS_PATTERN = re.compile(r"^(https?://)?([a-z0-9-]+\.)*google\.")

def _is_google_url(url: str) -> bool:
    if not url:
        return False
    return GOOGLE_DOMAINS_PATTERN.match(url) is not None

def _prime_browser_with_first_url(page: Page, priming_url: str) -> bool:
    log.info(f"Priming browser session with first URL: {priming_url[:80]}")
    try:
        page.goto(priming_url, wait_until='domcontentloaded', timeout=PAGE_NAVIGATION_TIMEOUT)
        if "consent.google.com" not in page.url:
            log.info("No consent page detected during priming. Session is ready.")
            return True

        log.info("Consent page detected. Attempting to click 'Accept'.")
        for selector in CONSENT_BUTTON_SELECTORS:
            try:
                button = page.locator(selector).first
                button.click(timeout=CONSENT_CLICK_TIMEOUT)
                page.wait_for_load_state('domcontentloaded', timeout=PAGE_NAVIGATION_TIMEOUT)
                log.info(f"Successfully clicked consent button using: {selector}")
                return True
            except PlaywrightTimeoutError:
                log.debug(f"Consent selector timed out: {selector}")

        log.error("Failed to handle consent page after trying all selectors.")
        return False
    except Exception as e:
        log.error(f"Failed to prime browser session with URL {priming_url}: {e}")
        return False

def enrich_articles_with_resolved_urls(articles: list[dict]) -> list[dict]:
    if not PLAYWRIGHT_AVAILABLE:
        log.critical("Playwright is not available. Cannot resolve URLs.")
        for article in articles:
            article['resolved_url'] = None
            article['resolution_error'] = "Playwright unavailable"
        return articles

    articles_with_links = [a for a in articles if a.get('rss_google_link')]
    if not articles_with_links:
        log.info("No articles with 'rss_google_link' found to process.")
        return articles

    log.info(f"Initializing Playwright to resolve {len(articles_with_links)} URLs.")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=HEADLESS_MODE)
            context = browser.new_context(user_agent=USER_AGENT, locale="en-US")
            page = context.new_page()
            page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "stylesheet", "font"] else route.continue_())
        except Exception as e:
            log.error(f"Failed to launch Playwright browser: {e}")
            for article in articles:
                article['resolved_url'] = None
                article['resolution_error'] = f"Playwright launch failed: {e}"
            return articles

        first_url_to_prime = articles_with_links[0]['rss_google_link']
        if not _prime_browser_with_first_url(page, first_url_to_prime):
            for article in articles:
                article['resolved_url'] = None
                article['resolution_error'] = "Failed to handle Google consent screen."
            browser.close()
            return articles

        for article in articles:
            gnews_url = article.get('rss_google_link')
            if not gnews_url:
                article['resolved_url'] = None
                article['resolution_error'] = "Missing rss_google_link"
                continue

            log.info(f"Resolving: {gnews_url[:80]}")
            try:
                page.goto(gnews_url, wait_until='commit', timeout=PAGE_NAVIGATION_TIMEOUT)
                if _is_google_url(page.url):
                    page.wait_for_url(
                        lambda new_url: not _is_google_url(new_url),
                        timeout=FINAL_URL_TIMEOUT,
                        wait_until='commit'
                    )
                article['resolved_url'] = page.url
                article['resolution_error'] = None
                log.info(f"Resolved to: {article['resolved_url']}")
            except PlaywrightTimeoutError:
                current_url = page.url
                log.warning(f"Navigation timed out. Last URL: {current_url}")
                if not _is_google_url(current_url):
                    article['resolved_url'] = current_url
                    article['resolution_error'] = None
                else:
                    article['resolved_url'] = None
                    article['resolution_error'] = "Timeout on Google domain"
            except Exception as e:
                log.error(f"Unexpected error resolving {gnews_url}: {e}")
                article['resolved_url'] = None
                article['resolution_error'] = str(e)

        browser.close()

    log.info("Playwright URL resolution finished.")
    return articles

def save_articles_to_json_file(
    articles: list[dict],
    file_context_name: str,
    exports_dir: str = "exports"
) -> None:
    os.makedirs(exports_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{file_context_name}_{timestamp_str}.json"
    filepath = os.path.join(exports_dir, filename)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        log.info(f"Saved {len(articles)} enriched articles to: {filepath}")
    except IOError as e:
        log.error(f"Failed to write articles to file {filepath}. Error: {e}")

def find_latest_input_file(search_dir: str) -> str | None:
    search_pattern = os.path.join(search_dir, "gnews_rss_feed_*.json")
    try:
        list_of_files = glob.glob(search_pattern)
        if not list_of_files:
            return None
        latest_file = max(list_of_files, key=os.path.getctime)
        return latest_file
    except Exception as e:
        log.error(f"Error finding input file in {search_dir}: {e}")
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    
    if not PLAYWRIGHT_AVAILABLE:
        log.critical("Playwright is not available. Test cannot run.")
    else:
        log.info("--- Running resolve_google_news_urls.py test ---")
        exports_directory = "exports"
        
        input_file_path = find_latest_input_file(exports_directory)

        if not input_file_path:
            log.error(f"No input file found in '{exports_directory}'.")
            log.error("Please run 'fetch_google_news_rss.py' first to generate a file.")
        else:
            log.info(f"Using input file: {input_file_path}")
            with open(input_file_path, 'r', encoding='utf-8') as f:
                articles_to_process = json.load(f)

            enriched_articles = enrich_articles_with_resolved_urls(articles_to_process)

            if enriched_articles:
                save_articles_to_json_file(
                    articles=enriched_articles,
                    file_context_name="gnews_resolved_articles"
                )
                print("\n--- Test Results Summary ---")
                successful = sum(1 for a in enriched_articles if a.get('resolved_url'))
                failed = len(enriched_articles) - successful
                print(f"Successfully resolved: {successful}")
                print(f"Failed to resolve: {failed}")
            else:
                print("Processing returned no articles.")

    log.info("--- resolve_google_news_urls.py test finished ---")