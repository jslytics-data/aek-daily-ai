import logging
import os
import glob
from datetime import datetime

from dotenv import load_dotenv
from google.cloud import storage

log = logging.getLogger(__name__)

def upload_content_to_gcs(
    content: str,
    destination_blob_name: str,
    bucket_name: str,
    project_id: str,
    content_type: str = "text/html"
) -> str | None:
    
    if not bucket_name:
        log.error("GCS bucket name not provided.")
        return None
    if not project_id:
        log.error("GCS project ID not provided.")
        return None
    if not content:
        log.error("Content to upload is empty.")
        return None
    
    log.info(f"Uploading content to gs://{bucket_name}/{destination_blob_name} in project {project_id}")
    
    try:
        storage_client = storage.Client(project=project_id)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)

        blob.upload_from_string(content, content_type=content_type)
        
        public_url = blob.public_url
        log.info(f"Content uploaded successfully. Public URL: {public_url}")
        return public_url

    except Exception as e:
        log.error(f"Failed to upload to GCS bucket '{bucket_name}'. Error: {e}", exc_info=True)
        if "forbidden" in str(e).lower() or "does not have storage.objects.create" in str(e).lower():
            log.error("Suggestion: Check if the service account has 'Storage Object Creator' permission on the bucket.")
        return None

def _find_latest_file_by_pattern(directory: str, pattern: str) -> str | None:
    try:
        search_path = os.path.join(directory, pattern)
        list_of_files = glob.glob(search_path)
        return max(list_of_files, key=os.path.getctime) if list_of_files else None
    except Exception as e:
        log.error(f"Error finding latest file with pattern '{pattern}': {e}")
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    load_dotenv()

    log.info("--- Running upload_to_gcs.py test ---")
    
    gcs_bucket = os.getenv("GCS_BUCKET_NAME")
    gcp_project_id = os.getenv("GCLOUD_PROJECT")

    if not gcs_bucket or not gcp_project_id:
        log.critical("GCS_BUCKET_NAME or GCLOUD_PROJECT not set in .env file. Test cannot run.")
    else:
        email_html_path = _find_latest_file_by_pattern("exports", "email_adapted_html_*.html")

        if not email_html_path:
            log.error("No email-adapted HTML file found in 'exports/'.")
            log.error("Please run 'format_adapters.email_adapter' first.")
        else:
            log.info(f"Using email HTML file for upload: {email_html_path}")
            try:
                with open(email_html_path, 'r', encoding='utf-8') as f:
                    html_to_upload = f.read()
                
                timestamp = datetime.now().strftime("%Y/%m/%d")
                filename = os.path.basename(email_html_path)
                destination_name = f"digests/{timestamp}/{filename}"
                
                public_url = upload_content_to_gcs(
                    content=html_to_upload,
                    destination_blob_name=destination_name,
                    bucket_name=gcs_bucket,
                    project_id=gcp_project_id,
                    content_type="text/html; charset=utf-8"
                )

                if public_url:
                    log.info("GCS upload test successful.")
                    print("\n--- Test Result: Success ---")
                    print(f"File uploaded to: {public_url}")
                else:
                    log.error("GCS upload test failed.")
                    print("\n--- Test Result: Failure ---")
                    print("Could not upload to GCS. Check logs for details.")

            except Exception as e:
                log.error(f"An error occurred during the CLI test: {e}", exc_info=True)

    log.info("--- upload_to_gcs.py test finished ---")