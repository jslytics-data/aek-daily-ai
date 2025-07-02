import logging
import os
from datetime import datetime

from dotenv import load_dotenv

from .content_retrieval import orchestrator as content_orchestrator
from . import generate_base_digest
from .format_adapters import generate_email_metas
from .format_adapters import generate_reddit_markdown as reddit_adapter
from .distribution import upload_to_gcs
from .distribution import send_sendgrid_email
from .distribution import post_to_reddit

log = logging.getLogger(__name__)

def _save_debug_file(content: str, query_term: str, context: str, extension: str) -> None:
    exports_dir = "exports"
    os.makedirs(exports_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_query = "".join(c for c in query_term if c.isalnum()).lower()
    filename = f"{context}_{sanitized_query}_{timestamp_str}.{extension}"
    filepath = os.path.join(exports_dir, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        log.info(f"Saved debug artifact to: {filepath}")
    except IOError as e:
        log.error(f"Failed to write debug file {filepath}. Error: {e}")

def run_full_digest_pipeline(
    query_term: str,
    days_to_look_back: int,
    language_code: str,
    location_code: int,
    save_intermediate_files: bool = False,
    upload_to_gcs_enabled: bool = False,
    send_email_enabled: bool = False,
    post_to_reddit_enabled: bool = False,
    recipient_emails_str: str | None = None,
    reddit_subreddit: str | None = None,
    reddit_flair_id: str | None = None,
    from_name_template: str | None = None
) -> bool:
    
    log.info(f"--- Starting full digest pipeline for query: '{query_term}' ---")

    articles = content_orchestrator.get_all_content_for_query(
        query_term=query_term,
        days_to_look_back=days_to_look_back,
        language_code=language_code,
        location_code=location_code
    )
    if not articles:
        log.error("Content retrieval yielded no articles. Halting pipeline.")
        return False
    
    if save_intermediate_files:
        import json
        _save_debug_file(json.dumps(articles, indent=2, ensure_ascii=False), query_term, "manager_retrieved_articles", "json")

    base_html = generate_base_digest.generate_base_html_digest(query_term, articles)
    if not base_html:
        log.error("Base HTML digest generation failed. Halting pipeline.")
        return False
    log.info("Base HTML digest generated successfully.")
    
    if save_intermediate_files:
        _save_debug_file(base_html, query_term, "manager_base_digest", "html")

    if upload_to_gcs_enabled:
        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        gcp_project = os.getenv("GCLOUD_PROJECT")
        if gcs_bucket and gcp_project:
            timestamp = datetime.now().strftime("%Y/%m/%d")
            sanitized_query = "".join(c for c in query_term if c.isalnum()).lower()
            filename = f"{sanitized_query}_digest_{datetime.now().strftime('%Y%m%d%H%M')}.html"
            dest_name = f"digests/{timestamp}/{filename}"
            upload_to_gcs.upload_content_to_gcs(base_html, dest_name, gcs_bucket, gcp_project)
        else:
            log.warning("GCS upload enabled, but GCS_BUCKET_NAME or GCLOUD_PROJECT missing")

    if send_email_enabled:
        if not recipient_emails_str:
            log.warning("Email sending enabled, but no recipient emails were provided.")
        else:
            log.info("Generating dynamic email subject and preview text.")
            email_metas = generate_email_metas.generate_email_metadata_from_html(base_html)

            if email_metas:
                recipients = [e.strip() for e in recipient_emails_str.split(',') if e.strip()]
                subject = email_metas["subject_line"]
                preview_text = email_metas["preview_text"]
                
                from_name = from_name_template.format(query_term=query_term.title()) if from_name_template else f"{query_term.title()} Daily"
                
                log.info(f"Proceeding to send email from '{from_name}'")
                send_sendgrid_email.send_digest_email(
                    recipient_emails=recipients,
                    subject=subject,
                    html_content=base_html,
                    from_name=from_name,
                    preview_text=preview_text
                )
            else:
                log.error("Failed to generate email metadata. Skipping email dispatch.")

    if post_to_reddit_enabled:
        if not reddit_subreddit:
            log.warning("Reddit posting enabled, but no subreddit was provided.")
        else:
            title, markdown = reddit_adapter.adapt_html_for_reddit(base_html)
            if title and markdown:
                if save_intermediate_files:
                    _save_debug_file(markdown, query_term, "manager_reddit_adapted", "md")
                post_to_reddit.post_content_to_reddit(reddit_subreddit, title, markdown, reddit_flair_id)
            else:
                log.error("Failed to adapt HTML for Reddit.")

    log.info(f"--- Full digest pipeline for query: '{query_term}' finished. ---")
    return True

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    load_dotenv()
    
    log.info("--- Running manager.py test ---")

    TEST_QUERY = "ΑΕΚ"
    TEST_LANG_CODE = "el"
    TEST_LOC_CODE = 2300 
    TEST_DAYS_BACK = 2
    
    TEST_SAVE_FILES = True
    TEST_UPLOAD_GCS = False
    TEST_SEND_EMAIL = True
    TEST_POST_REDDIT = False

    TEST_RECIPIENTS = os.getenv("TEST_RECIPIENT_EMAILS")
    TEST_SUBREDDIT = "testingground4bots"
    TEST_FLAIR_ID = None
    TEST_FROM_NAME_TEMPLATE = "{query_term} Today"

    success = run_full_digest_pipeline(
        query_term=TEST_QUERY,
        days_to_look_back=TEST_DAYS_BACK,
        language_code=TEST_LANG_CODE,
        location_code=TEST_LOC_CODE,
        save_intermediate_files=TEST_SAVE_FILES,
        upload_to_gcs_enabled=TEST_UPLOAD_GCS,
        send_email_enabled=TEST_SEND_EMAIL,
        post_to_reddit_enabled=TEST_POST_REDDIT,
        recipient_emails_str=TEST_RECIPIENTS,
        reddit_subreddit=TEST_SUBREDDIT,
        reddit_flair_id=TEST_FLAIR_ID,
        from_name_template=TEST_FROM_NAME_TEMPLATE
    )

    if success:
        print("\n--- Manager Test Result: Pipeline Completed ---")
    else:
        print("\n--- Manager Test Result: Pipeline Failed ---")
        print("Check logs for details on where the process was halted.")
        
    log.info("--- manager.py test finished ---")