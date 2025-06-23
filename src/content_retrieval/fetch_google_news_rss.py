import logging
import os
import json
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, urlunparse, urlparse
from datetime import timezone, datetime, timedelta
from email.utils import parsedate_to_datetime

log = logging.getLogger(__name__)

def _generate_google_news_rss_url(
    query_term: str,
    language_code: str = "",
    country_code: str = ""
) -> str | None:
    if not query_term:
        log.error("Query term is mandatory for Google News RSS.")
        return None

    base_url_parts = ('https', 'news.google.com', '/rss/search', '', '', '')
    query_params = {'q': query_term}
    if language_code:
        query_params['hl'] = language_code
    if country_code:
        query_params['gl'] = country_code
    if language_code and country_code:
        query_params['ceid'] = f"{country_code.upper()}:{language_code.lower()}"

    encoded_query_string = urlencode(query_params)
    url_components = list(base_url_parts)
    url_components[4] = encoded_query_string
    generated_url = urlunparse(tuple(url_components))
    log.info(f"Generated Google News RSS URL: {generated_url}")
    return generated_url

def _canonicalize_date_to_isoformat(date_str: str | None) -> str | None:
    if not date_str:
        return None
    try:
        dt_obj = parsedate_to_datetime(date_str)
        if dt_obj.tzinfo is None or dt_obj.tzinfo.utcoffset(dt_obj) is None:
            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
        else:
            dt_obj = dt_obj.astimezone(timezone.utc)
        return dt_obj.isoformat()
    except (TypeError, ValueError) as e:
        log.warning(f"Could not parse or canonicalize date '{date_str}': {e}")
        return None

def _get_domain_from_url(url_string: str | None) -> str | None:
    if not url_string:
        return None
    try:
        parsed_url = urlparse(url_string)
        domain = parsed_url.netloc
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception as e:
        log.warning(f"Could not parse domain from URL '{url_string}': {e}")
        return None

def _parse_rss_feed_content(xml_content: str) -> list[dict]:
    try:
        xml_root_element = ET.fromstring(xml_content)
        log.info("Successfully parsed XML content from RSS feed.")
    except ET.ParseError as e:
        log.error(f"Failed to parse XML content. Error: {e}")
        return []

    extracted_news_items = []
    for item_element in xml_root_element.findall('./channel/item'):
        title = item_element.findtext('title')
        rss_link = item_element.findtext('link')
        pub_date_str = item_element.findtext('pubDate')
        canonical_pub_date = _canonicalize_date_to_isoformat(pub_date_str)
        source_tag = item_element.find('source')
        source_name = source_tag.text if source_tag is not None else None
        source_url = source_tag.get('url') if source_tag is not None else None
        source_domain = _get_domain_from_url(source_url)

        extracted_news_items.append({
            'title': title,
            'rss_google_link': rss_link,
            'publication_date': canonical_pub_date,
            'source_name_from_rss': source_name,
            'source_domain_from_rss': source_domain
        })
    log.info(f"Extracted {len(extracted_news_items)} items from RSS feed.")
    return extracted_news_items

def _filter_articles_by_date(
    articles: list[dict],
    days_to_look_back: int
) -> list[dict]:
    if days_to_look_back < 0:
        log.warning("days_to_look_back is negative, returning all articles.")
        return articles

    filtered_articles = []
    today_utc = datetime.now(timezone.utc).date()
    start_date_utc = today_utc - timedelta(days=days_to_look_back)
    log.info(f"Filtering articles from {start_date_utc.isoformat()} to now.")

    for article in articles:
        pub_date = article.get('publication_date')
        if not pub_date:
            log.warning(f"Skipping article with no publication_date: {article.get('title', 'N/A')[:50]}...")
            continue
        try:
            article_pub_date = datetime.fromisoformat(pub_date).date()
            if start_date_utc <= article_pub_date <= today_utc:
                filtered_articles.append(article)
        except (ValueError, TypeError) as e:
            log.warning(f"Could not parse publication_date '{pub_date}': {e}. Skipping article.")
            continue

    log.info(f"Filtered {len(articles)} to {len(filtered_articles)} articles.")
    return filtered_articles

def fetch_google_news_articles(
    query_term: str,
    days_to_look_back: int,
    language_code: str = "",
    country_code: str = ""
) -> list[dict]:
    log.info(f"Starting fetch for query: '{query_term}', days: {days_to_look_back}")

    rss_feed_url = _generate_google_news_rss_url(query_term, language_code, country_code)
    if not rss_feed_url:
        return []

    try:
        response = requests.get(rss_feed_url, timeout=20)
        response.raise_for_status()
        log.info(f"Successfully fetched RSS feed with status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        log.error(f"Failed to fetch RSS feed from {rss_feed_url}. Error: {e}")
        return []

    parsed_items = _parse_rss_feed_content(response.content)
    if not parsed_items:
        log.info("No items parsed from RSS feed content.")
        return []

    filtered_items = _filter_articles_by_date(parsed_items, days_to_look_back)
    log.info(f"Google News RSS fetch finished. Found {len(filtered_items)} articles.")
    return filtered_items

def save_articles_to_json_file(
    articles: list[dict],
    file_context_name: str,
    query_term: str,
    exports_dir: str = "exports"
) -> None:
    os.makedirs(exports_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_query = "".join(c for c in query_term if c.isalnum()).lower()
    filename = f"{file_context_name}_{sanitized_query}_{timestamp_str}.json"
    filepath = os.path.join(exports_dir, filename)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        log.info(f"Saved {len(articles)} articles to: {filepath}")
    except IOError as e:
        log.error(f"Failed to write articles to file {filepath}. Error: {e}")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
    )
    
    test_query_term = "ΑΕΚ"
    test_country_code = "GR"
    test_days_to_look_back = 1

    log.info("--- Running fetch_google_news_rss.py test ---")
    
    fetched_articles = fetch_google_news_articles(
        query_term=test_query_term,
        days_to_look_back=test_days_to_look_back,
        country_code=test_country_code
    )

    if fetched_articles:
        save_articles_to_json_file(
            articles=fetched_articles,
            file_context_name="gnews_rss_feed",
            query_term=test_query_term
        )
        print(f"Successfully fetched and saved {len(fetched_articles)} articles.")
    else:
        print("No articles found for the given test query.")

    log.info("--- fetch_google_news_rss.py test finished ---")