import logging
import os
import glob
import re
from datetime import datetime

import litellm
from dotenv import load_dotenv

litellm.set_verbose = False
log = logging.getLogger(__name__)

TEMPERATURE = 1.0
EMAIL_ADAPTATION_PROMPT_TEMPLATE = """
You are an expert UI/UX and Design Specialist for email newsletters.
Your task is to take an existing base HTML newsletter and enhance its visual appeal, branding consistency, and user experience, specifically for email consumption, aiming for a style similar to "Morning Brew" (clean, modern, highly readable).

You are provided with:
1. The Original Optimised Prompt: This prompt was used to generate the base HTML and contains key information about the newsletter's topic, desired tone, and target audience. Use this for contextual understanding of the intended style.
2. The Base HTML Newsletter Content: This is the raw HTML that requires your design and UX improvements.

Your Task - Design & UX Overhaul for Email:
- Review the Base HTML and use the Original Optimised Prompt as a guide for branding and tone.
- Transform the Base HTML into a polished, professional, and readable email newsletter.
- All styling MUST use inline CSS for maximum email client compatibility. Avoid <style> blocks.
- Ensure the HTML structure is robust for various email clients, using tables for layout if necessary.
- Improve typography, spacing, and visual hierarchy.
- Preserve all original textual content and functional links.
- For mobile view, keep side margins minimal to maximize text space.

Output Requirements:
- Your output MUST be ONLY the complete, refined HTML document with inline CSS.
- Do NOT include any additional text, explanations, or comments outside of the HTML code itself.
"""

def _clean_llm_html_output(raw_html_text: str) -> str | None:
    if not raw_html_text or not isinstance(raw_html_text, str):
        return None
    
    cleaned_text = raw_html_text.strip()
    if cleaned_text.startswith("```html"):
        cleaned_text = cleaned_text[7:]
    if cleaned_text.endswith("```"):
        cleaned_text = cleaned_text[:-3]
    cleaned_text = cleaned_text.strip()

    start_match = re.search(r"<!DOCTYPE\s+html|<html", cleaned_text, re.IGNORECASE)
    if not start_match:
        log.warning("Could not find standard HTML start in LLM output.")
        return cleaned_text if cleaned_text.startswith("<") and cleaned_text.endswith(">") else None
    
    start_index = start_match.start()
    last_end_tag_index = cleaned_text.rfind("</html>")
    if last_end_tag_index == -1:
        log.warning("Could not find standard </html> end tag.")
        return cleaned_text[start_index:].strip()
        
    return cleaned_text[start_index : last_end_tag_index + len("</html>")].strip()

def adapt_html_for_email(base_html_content: str, original_prompt_content: str) -> str | None:
    log.info("Starting email HTML adaptation process.")
    
    if not os.getenv("GEMINI_API_KEY"):
        log.error("GEMINI_API_KEY not found in environment for LiteLLM email adaptation.")
        return None
        
    model_string = os.getenv("LITELLM_MODEL_STRING")
    if not model_string:
        log.error("LITELLM_MODEL_STRING not found in environment.")
        return None

    if not base_html_content or not original_prompt_content:
        log.error("Base HTML content and original prompt content must be provided.")
        return None

    full_prompt_for_llm = (
        f"{EMAIL_ADAPTATION_PROMPT_TEMPLATE}\n\n"
        f"--- Original Optimised Prompt (for Context and Style Guidance) ---\n"
        f"{original_prompt_content}\n\n"
        f"--- Base HTML Newsletter Content (to be Adapted) ---\n"
        f"```html\n{base_html_content}\n```"
    )

    messages = [{"role": "user", "content": full_prompt_for_llm}]
    
    try:
        log.info(f"Requesting email-adapted HTML from LiteLLM model: {model_string}")
        response = litellm.completion(model=model_string, messages=messages, temperature=TEMPERATURE)
        
        if response and response.choices and response.choices[0].message and response.choices[0].message.content:
            raw_html = response.choices[0].message.content
            cleaned_html = _clean_llm_html_output(raw_html)
            if cleaned_html:
                log.info("Successfully generated and cleaned email-adapted HTML.")
                return cleaned_html
            log.warning(f"Could not clean HTML from LiteLLM output. Raw: {raw_html[:300]}...")
            return None
        log.warning("No valid content in LiteLLM response for email adaptation.")
        return None
    except Exception as e:
        log.error(f"LiteLLM error during email adaptation: {e}", exc_info=True)
        return None

def save_html_to_file(content: str, query_term: str, file_context_name: str, exports_dir: str = "exports") -> str | None:
    os.makedirs(exports_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_query = "".join(c for c in query_term if c.isalnum()).lower()
    filename = f"{file_context_name}_{sanitized_query}_{timestamp_str}.html"
    filepath = os.path.join(exports_dir, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        log.info(f"Saved content to: {filepath}")
        return filepath
    except IOError as e:
        log.error(f"Failed to write to file {filepath}. Error: {e}")
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

    log.info("--- Running email_adapter.py test ---")

    if not os.getenv("GEMINI_API_KEY") or not os.getenv("LITELLM_MODEL_STRING"):
        log.critical("GEMINI_API_KEY or LITELLM_MODEL_STRING not in .env. Test cannot run.")
    else:
        exports_dir = "exports"
        base_html_path = _find_latest_file_by_pattern(exports_dir, "base_digest_html_*.html")
        prompt_path = _find_latest_file_by_pattern(exports_dir, "optimised_digest_prompt_*.txt")

        if not base_html_path or not prompt_path:
            log.error("Could not find latest base HTML and/or optimised prompt files in 'exports/'.")
            log.error("Please run 'generate_base_digest' first.")
        else:
            log.info(f"Using base HTML file: {base_html_path}")
            log.info(f"Using prompt file: {prompt_path}")
            try:
                with open(base_html_path, 'r', encoding='utf-8') as f:
                    base_html = f.read()
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    prompt_text = f.read()
                
                filename_parts = os.path.basename(base_html_path).split('_')
                query_term = "testquery"
                if len(filename_parts) > 3:
                    query_term = filename_parts[3]

                log.info(f"Extracted query term for test: {query_term}")

                email_html = adapt_html_for_email(base_html, prompt_text)
                
                if email_html:
                    log.info("Email HTML generated successfully for test.")
                    print("\n--- Email HTML (Snippet) ---")
                    print(email_html[:1000] + "...")
                    save_html_to_file(email_html, query_term, "email_adapted_html")
                else:
                    log.error("Failed to generate email HTML during test.")
                    print("\n--- Email HTML Generation FAILED ---")

            except Exception as e:
                log.error(f"Error during CLI test execution: {e}", exc_info=True)

    log.info("--- email_adapter.py test finished ---")