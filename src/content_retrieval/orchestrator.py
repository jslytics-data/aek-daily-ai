import logging
import os
import json
from datetime import datetime
from urllib.parse import urlparse

from . import fetch_google_news_rss
from . import resolve_google_news_urls
from . import extract_article_content

log = logging.getLogger(__name__)

def _get_domain_from_url(url_string: str | None) -> str | None:
    if not url_string:
        return None
    try:
        return urlparse(url_string).netloc.replace("www.", "")
    except Exception:
        return None

def get_all_content_for_query(
    query_term: str,
    days_to_look_back: int,
    language_code: str = "",
    country_code: str = ""
) -> list[dict]:
    log.info(f"Orchestrator starting for query: '{query_term}'")

    rss_articles = fetch_google_news_rss.fetch_google_news_articles(
        query_term=query_term,
        days_to_look_back=days_to_look_back,
        language_code=language_code,
        country_code=country_code
    )
    if not rss_articles:
        log.warning("Orchestrator: Fetch RSS step yielded no articles. Halting.")
        return []
    log.info(f"Orchestrator: Fetched {len(rss_articles)} articles from RSS.")

    resolved_articles = resolve_google_news_urls.enrich_articles_with_resolved_urls(rss_articles)
    log.info("Orchestrator: URL resolution step completed.")

    fully_enriched_articles = extract_article_content.enrich_articles_with_extracted_content(resolved_articles)
    log.info("Orchestrator: Content extraction step completed.")

    final_articles_payload = []
    for article in fully_enriched_articles:
        if article.get('resolved_url') and article.get('extracted_text'):
            final_articles_payload.append({
                "title": article.get('extracted_title') or article.get('title'),
                "link": article.get('resolved_url'),
                "publication_date": article.get('extracted_date') or article.get('publication_date'),
                "source_domain": _get_domain_from_url(article.get('resolved_url')),
                "text": article.get('extracted_text')
            })
        else:
            log.warning(f"Skipping article from final payload due to missing content: {article.get('title')}")

    log.info(f"Orchestrator finished. Produced {len(final_articles_payload)} final articles.")
    return final_articles_payload

def save_articles_to_json_file(
    articles: list[dict],
    query_term: str,
    file_context_name: str,
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
        log.info(f"Saved {len(articles)} orchestrated articles to: {filepath}")
    except IOError as e:
        log.error(f"Failed to write articles to file {filepath}. Error: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')

    test_query_term = "AEK"
    test_country_code = "GR"
    test_days_to_look_back = 2

    log.info("--- Running orchestrator.py test ---")
    final_results = get_all_content_for_query(
        query_term=test_query_term,
        days_to_look_back=test_days_to_look_back,
        country_code=test_country_code
    )

    if final_results:
        save_articles_to_json_file(
            articles=final_results,
            query_term=test_query_term,
            file_context_name="orchestrated_articles"
        )
        print("\n--- Test Results Summary ---")
        print(f"Orchestrator produced {len(final_results)} articles.")
        print("\nSample of first article:")
        print(json.dumps(final_results[0], indent=2))
    else:
        print("\n--- Test Results Summary ---")
        print("Orchestrator did not produce any final articles.")

    log.info("--- orchestrator.py test finished ---")