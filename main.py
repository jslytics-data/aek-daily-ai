import os
import logging

if "K_SERVICE" in os.environ:
    import google.cloud.logging
    google.cloud.logging.Client().setup_logging()
else:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
    )

from flask import Flask, request, jsonify
from dotenv import load_dotenv
from functools import wraps
from src import manager

load_dotenv()
app = Flask(__name__)
log = logging.getLogger(__name__)

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = os.getenv("INTERNAL_API_KEY")
        if not api_key:
            log.error("CRITICAL: INTERNAL_API_KEY is not configured on the server.")
            return jsonify({"status": "error", "message": "Service is not configured."}), 500
        
        provided_key = request.headers.get("X-API-Key")
        if not provided_key or provided_key != api_key:
            log.warning(f"Unauthorized access attempt from IP: {request.remote_addr}")
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
        return f(*args, **kwargs)
    return decorated_function

@app.route("/run-aek-digest", methods=["POST"])
@require_api_key
def run_aek_digest_endpoint():
    QUERY_TERM = "ΑΕΚ"
    LANGUAGE_CODE = "el"
    LOCATION_CODE = 2300
    DAYS_TO_LOOK_BACK = int(os.getenv("DAYS_TO_LOOK_BACK", "1"))

    upload_gcs = os.getenv("DISTRIBUTION_GCS_ENABLED", "true").lower() == "true"
    send_email = os.getenv("DISTRIBUTION_EMAIL_ENABLED", "true").lower() == "true"
    post_reddit = os.getenv("DISTRIBUTION_REDDIT_ENABLED", "false").lower() == "true"
    
    recipient_emails = os.getenv("DISTRIBUTION_EMAIL_RECIPIENTS")
    reddit_subreddit = os.getenv("DISTRIBUTION_REDDIT_SUBREDDIT")
    reddit_flair_id = os.getenv("DISTRIBUTION_REDDIT_FLAIR_ID")
    from_name_template = os.getenv("EMAIL_FROM_NAME_TEMPLATE", "{query_term} Daily")

    log.info(f"Received valid request to run digest for query: '{QUERY_TERM}'")
    
    try:
        success = manager.run_full_digest_pipeline(
            query_term=QUERY_TERM,
            days_to_look_back=DAYS_TO_LOOK_BACK,
            language_code=LANGUAGE_CODE,
            location_code=LOCATION_CODE,
            save_intermediate_files=False,
            upload_to_gcs_enabled=upload_gcs,
            send_email_enabled=send_email,
            post_to_reddit_enabled=post_reddit,
            recipient_emails_str=recipient_emails,
            reddit_subreddit=reddit_subreddit,
            reddit_flair_id=reddit_flair_id,
            from_name_template=from_name_template
        )

        if success:
            log.info(f"Pipeline completed successfully for query: '{QUERY_TERM}'")
            return jsonify({"status": "success", "message": "Digest pipeline completed."}), 200
        else:
            log.error(f"Pipeline failed for query: '{QUERY_TERM}'")
            return jsonify({"status": "error", "message": "Digest pipeline failed during execution."}), 500

    except Exception as e:
        log.critical(f"An unhandled exception occurred in the manager: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "An internal server error occurred."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)