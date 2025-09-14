import logging
import os
import glob
import json
from datetime import datetime

import litellm
from dotenv import load_dotenv

litellm.set_verbose = False
log = logging.getLogger(__name__)

ENABLE_LLM_THINKING = True
LLM_THINKING_BUDGET_TOKENS = 32768

TEMPERATURE = 1.0
REDDIT_MARKDOWN_ADAPTATION_PROMPT_TEMPLATE = """
You are an expert content adapter specializing in converting HTML newsletters to Reddit-flavored Markdown posts.
Your task is to process an existing base HTML newsletter and generate two components for a Reddit self-post:
1. A specifically formatted title.
2. The main body content converted to Reddit-flavored Markdown.

You are provided with the Base HTML Newsletter Content.

Your Task:

1.  **Extract and Format the Reddit Title:**
    *   From the Base HTML, identify the newsletter's main topic or name (e.g., "AEK Daily").
    *   From the Base HTML, identify the full publication date of the newsletter (e.g., "Τετάρτη, 11 Ιουνίου 2025").
    *   Construct the Reddit post title using this format: "{Extracted Full Date} | {Short Title from Context}".
    *   Ensure the language of the title matches the primary language used in the Base HTML content.

2.  **Convert to Markdown Body:**
    *   Convert the HTML structure and content into Reddit-flavored Markdown, maintaining the original style and tone. Output in same source language.
    *   Use appropriate Markdown for headings (##), lists (*), links ([text](URL)), and emphasis (*italic*, **bold**) etc.
    *   Use '---' for thematic breaks where appropriate.
    *   Do not include any closing disclaimer.
    *   Do not over-do it with cringy greetings, like "καλημερα Βολο!". If there's enough content you can include a Highlights bullet point section at the top. Start straight with the bullet points - it looks nice on the post listing page where it shows the first few lines of the post and users can see the bullet points right away
    *   Your goal here is not just to adapt the formatting to markdown. Your goal is to transform the base HTML into a native engaging reddit post. Use formatting extensively to keep things interesting.
    *   If source language is not english, output the full post in the source language. But below that, add a thematic break and then an english version. Will be in the same post.
    *   Do not include these blacklisted words: "km, KM, κιτρινομαυρο, Στυλιανόπουλος, κμ, Στυλ, ΚΜ, Κιτρονόμαυρο, styl, kitrinomavro, Styl"
    *   Small adaptation - if the original HTML is a bit too disrespectful to ex players or staf, tone that down. There was an edition which made fun of an ex-coach losing a few games in a row, which is not nice.

Output Requirements:
You will provide your response in a structured JSON format. The JSON object must have two fields:
- "extracted_title": A string containing the Reddit post title, formatted as described above.
- "markdown_body": A string containing ONLY the Markdown text for the post body. Do NOT include any ```markdown ... ``` wrappers.
"""

def _clean_markdown_body(raw_markdown: str) -> str | None:
    if not raw_markdown or not isinstance(raw_markdown, str):
        return None
    cleaned_text = raw_markdown.strip()
    if cleaned_text.startswith("```markdown"):
        cleaned_text = cleaned_text[len("```markdown"):].strip()
    if cleaned_text.endswith("```"):
        cleaned_text = cleaned_text[:-len("```")].strip()
    return cleaned_text

def adapt_html_for_reddit(base_html_content: str) -> tuple[str | None, str | None]:
    log.info("Starting Reddit Markdown adaptation process.")

    if not os.getenv("GEMINI_API_KEY"):
        log.error("GEMINI_API_KEY not found in environment for LiteLLM Reddit adaptation.")
        return None, None
        
    model_string = os.getenv("LITELLM_MODEL_STRING")
    if not model_string:
        log.error("LITELLM_MODEL_STRING not found in environment.")
        return None, None

    if not base_html_content:
        log.error("Base HTML content must be provided.")
        return None, None

    full_prompt_for_llm = (
        f"{REDDIT_MARKDOWN_ADAPTATION_PROMPT_TEMPLATE}\n\n"
        f"--- Base HTML Newsletter Content (to be Adapted to Markdown) ---\n"
        f"```html\n{base_html_content}\n```"
    )

    messages = [{"role": "user", "content": full_prompt_for_llm}]
    
    completion_kwargs = {
        "model": model_string, 
        "messages": messages, 
        "temperature": TEMPERATURE,
        "response_format": {"type": "json_object"}
    }

    if ENABLE_LLM_THINKING:
        completion_kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": LLM_THINKING_BUDGET_TOKENS,
        }
        log.info(f"LLM thinking enabled with token budget: {LLM_THINKING_BUDGET_TOKENS}")

    try:
        log.info(f"Requesting Reddit-adapted content from LiteLLM model: {model_string}")
        response = litellm.completion(**completion_kwargs)
        
        if not (response and response.choices and response.choices[0].message and response.choices[0].message.content):
            log.warning("No valid content in LiteLLM response for Reddit adaptation.")
            return None, None

        content_str = response.choices[0].message.content
        data = json.loads(content_str)
        
        title = data.get("extracted_title")
        raw_markdown = data.get("markdown_body")
        
        if not title or not raw_markdown:
            log.error(f"LLM JSON response missing 'extracted_title' or 'markdown_body'. Response: {data}")
            return None, None

        cleaned_markdown = _clean_markdown_body(raw_markdown)
        log.info(f"Successfully generated Reddit content. Title: '{title}'")
        return title, cleaned_markdown

    except json.JSONDecodeError:
        log.error(f"Failed to decode JSON from LLM response. Raw: {response.choices[0].message.content[:300]}...")
        return None, None
    except Exception as e:
        log.error(f"LiteLLM error during Reddit adaptation: {e}", exc_info=True)
        return None, None

def save_markdown_to_file(content: str, query_term: str, file_context_name: str, exports_dir: str = "exports") -> str | None:
    os.makedirs(exports_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_query = "".join(c for c in query_term if c.isalnum()).lower()
    filename = f"{file_context_name}_{sanitized_query}_{timestamp_str}.md"
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

    log.info("--- Running reddit_adapter.py test ---")

    if not os.getenv("GEMINI_API_KEY") or not os.getenv("LITELLM_MODEL_STRING"):
        log.critical("GEMINI_API_KEY or LITELLM_MODEL_STRING not in .env. Test cannot run.")
    else:
        exports_dir = "exports"
        base_html_path = _find_latest_file_by_pattern(exports_dir, "base_digest_html_*.html")

        if not base_html_path:
            log.error("Could not find latest base HTML file in 'exports/'.")
            log.error("Please run 'base_digest_generator' first.")
        else:
            log.info(f"Using base HTML file: {base_html_path}")
            try:
                with open(base_html_path, 'r', encoding='utf-8') as f:
                    base_html = f.read()
                
                filename_parts = os.path.basename(base_html_path).split('_')
                query_term = "testquery"
                if len(filename_parts) > 3:
                    query_term = filename_parts[3]

                log.info(f"Extracted query term for test: {query_term}")

                title, markdown_body = adapt_html_for_reddit(base_html)
                
                if title and markdown_body:
                    log.info("Reddit title and markdown generated successfully for test.")
                    print(f"\n--- Reddit Title ---\n{title}")
                    print("\n--- Reddit Markdown (Snippet) ---")
                    print(markdown_body[:1000] + "...")
                    save_markdown_to_file(markdown_body, query_term, "reddit_adapted_markdown")
                else:
                    log.error("Failed to generate Reddit title and/or markdown during test.")
                    print("\n--- Reddit Content Generation FAILED ---")

            except Exception as e:
                log.error(f"Error during CLI test execution: {e}", exc_info=True)

    log.info("--- reddit_adapter.py test finished ---")