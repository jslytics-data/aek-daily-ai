import logging
import os
import glob
import json
from datetime import datetime

from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, HtmlContent

log = logging.getLogger(__name__)

def send_digest_email(
    recipient_emails: list[str],
    subject: str,
    html_content: str,
    from_name: str | None = None,
    preview_text: str | None = None
) -> bool:
    log.info(f"Preparing to send email with subject '{subject}' to {len(recipient_emails)} recipient(s).")
    
    sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
    sender_email = os.getenv("VERIFIED_SENDER_EMAIL")

    if not sendgrid_api_key or not sender_email:
        log.error("SENDGRID_API_KEY or VERIFIED_SENDER_EMAIL not found in environment.")
        return False
    if not recipient_emails:
        log.error("Recipient email list is empty.")
        return False
    if not html_content:
        log.error("HTML content is empty.")
        return False

    from_header = sender_email
    if from_name:
        log.info(f"Using From Name: '{from_name}'")
        from_header = (sender_email, from_name)

    final_html = html_content
    if preview_text:
        log.info(f"Prepending preview text: '{preview_text[:80]}...'")
        spacer = "‌ " * 100
        preview_block = f"""
            <div style="display:none;font-size:1px;color:#ffffff;line-height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;">
                {preview_text}
            </div>
            <div style="display:none;font-size:1px;color:#ffffff;line-height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;">
                {spacer}
            </div>
        """
        final_html = preview_block + html_content
    
    message = Mail(
        from_email=from_header,
        to_emails=recipient_emails,
        subject=subject
    )
    message.content = HtmlContent(final_html)

    try:
        sg_client = SendGridAPIClient(sendgrid_api_key)
        response = sg_client.send(message)
        status_code = response.status_code

        if 200 <= status_code < 300:
            log.info(f"Email successfully accepted by SendGrid. Status: {status_code}.")
            return True
        else:
            log.error(f"SendGrid returned an error. Status: {status_code}. Body: {response.body}")
            return False
    except Exception as e:
        log.error(f"An exception occurred while sending email via SendGrid: {e}", exc_info=True)
        return False

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

    log.info("--- Running send_sendgrid_email.py test ---")

    test_recipients_str = os.getenv("TEST_RECIPIENT_EMAILS")
    if not test_recipients_str:
        log.critical("TEST_RECIPIENT_EMAILS not set in .env file. Test cannot run.")
    else:
        email_metas_path = _find_latest_file_by_pattern("exports", "email_metas_*.json")
        base_html_path = _find_latest_file_by_pattern("exports", "base_digest_html_*.html")

        if not email_metas_path or not base_html_path:
            log.error("Could not find required input files in 'exports/'.")
            log.error("Please run 'generate_base_digest.py' and 'generate_email_metas.py' first.")
        else:
            log.info(f"Using metadata file: {email_metas_path}")
            log.info(f"Using HTML file: {base_html_path}")
            try:
                with open(email_metas_path, 'r', encoding='utf-8') as f:
                    email_metas = json.load(f)
                
                with open(base_html_path, 'r', encoding='utf-8') as f:
                    email_html = f.read()

                recipients = [email.strip() for email in test_recipients_str.split(',') if email.strip()]
                subject = email_metas.get("subject_line")
                preview = email_metas.get("preview_text")
                
                test_from_name = f"AEK Daily - {datetime.now().strftime('%d/%m')}"

                if not subject:
                    log.critical("Subject line not found in metadata file. Cannot send email.")
                else:
                    success = send_digest_email(
                        recipient_emails=recipients,
                        subject=subject,
                        html_content=email_html,
                        from_name=test_from_name,
                        preview_text=preview
                    )

                    if success:
                        log.info("Test email dispatch successful.")
                        print("\n--- Test Result: Success ---")
                        print(f"Email sent to: {', '.join(recipients)}")
                    else:
                        log.error("Test email dispatch failed.")
                        print("\n--- Test Result: Failure ---")
                        print("Could not send email. Please check the logs for details.")

            except Exception as e:
                log.error(f"An error occurred during the CLI test: {e}", exc_info=True)
    
    log.info("--- send_sendgrid_email.py test finished ---")