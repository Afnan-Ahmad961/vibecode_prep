import os
import json

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Expected JSON response schema from Gemini:
# {
#   "hld": { "overview": str, "components": str, "data_flow": str },
#   "lld": { "models": str, "endpoints": str, "folder_structure": str },
#   "project_explanation": { "title": str, "description": str },
#   "milestones": [{ "title": str, "description": str, "complexity": str, "prompt": str }],
#   "tech_stack": { "frontend": str, "backend": str, "database": str, "devops": str },
#   "security": [str],
#   "manual_setup": [str],
#   "guide": { "title": str, "description": str }
# }
# ---------------------------------------------------------------------------

MODEL = "gemini-1.5-flash"

SYSTEM_INSTRUCTION = (
    "You are a Senior Solutions Architect and a senior Full Stack developer. "
    "I will give you a project idea, requirements/constraints and you will return a complete, "
    "structured software engineering plan in JSON format.\n\n"
    "The JSON must have exactly the following keys:\n"
    "- hld: High-level design object with overview, components, data_flow\n"
    "- lld: Low-level design object with models, endpoints, folder_structure\n"
    "- project_explanation: Object with title and short description (for non-technical users)\n"
    "- milestones: Array of objects, each with title, description, complexity, prompt\n"
    "- tech_stack: Object with frontend, backend, database, devops\n"
    "- security: Array of security recommendations (strings)\n"
    "- manual_setup: Array of manual setup steps (strings)\n"
    "- guide: Object with title and short description (for non-technical users explaining "
    "the next steps and how to build the project)\n\n"
    "Return **only** a valid JSON object, without markdown code fences or explanations."
)


def _get_client() -> genai.Client:
    """Return a configured Gemini client."""
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences that Gemini sometimes wraps JSON in."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (e.g. ```json or ```)
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def generate_project_plan(form_data: dict) -> dict:
    """
    Call Gemini to generate a full structured project plan from form data.

    form_data keys: description, framework (optional), platform, requirements (optional)

    Returns:
        { "success": True, "data": <parsed_dict> }
        or
        { "success": False, "error": "<message>" }
    """
    description = form_data.get("description", "")
    framework = form_data.get("framework", "")
    platform = form_data.get("platform", "")
    requirements = form_data.get("requirements", "")

    # Build the user portion of the prompt dynamically
    user_prompt = f"Project Description: {description}\n\nTarget Platform: {platform}"

    if framework:
        user_prompt += f"\nPreferred Framework/Library: {framework}"

    if requirements:
        user_prompt += f"\nSpecific Requirements / Constraints: {requirements}"

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.4,
            ),
        )
        raw_text = response.text

        # Strip markdown fences before parsing (common Gemini gotcha)
        cleaned = _strip_code_fences(raw_text)
        parsed = json.loads(cleaned)

        return {"success": True, "data": parsed}

    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Gemini returned invalid JSON: {str(e)}",
        }
    except Exception as e:
        error_message = str(e)
        if "429" in error_message or "quota" in error_message.lower() or "rate" in error_message.lower():
            return {
                "success": False,
                "error": "Gemini API rate limit reached. Please wait a moment and try again.",
            }
        return {
            "success": False,
            "error": f"Gemini API error: {error_message}",
        }


def send_followup_message(chat_messages: list, user_message: str) -> dict:
    """
    Send a follow-up message to Gemini using the full conversation history for context.

    Uses the new google-genai SDK's multi-turn approach: builds a list of
    Content objects from existing DB messages and appends the new user message.

    chat_messages: list of Message model instances (ordered by created_at).
    user_message:  The plain-text content of the new user message.

    Returns:
        { "success": True, "data": <response_text> }
        or
        { "success": False, "error": "<message>" }
    """
    # Build the conversation history as Content objects
    # Gemini uses "user" and "model" roles (not "assistant")
    contents = []
    for msg in chat_messages:
        role = "model" if msg.role == "assistant" else "user"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg.content)],
            )
        )

    # Append the new user message at the end
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_message)],
        )
    )

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
        )
        return {"success": True, "data": response.text}

    except Exception as e:
        error_message = str(e)
        if "429" in error_message or "quota" in error_message.lower() or "rate" in error_message.lower():
            return {
                "success": False,
                "error": "Gemini API rate limit reached. Please wait a moment and try again.",
            }
        return {
            "success": False,
            "error": f"Gemini API error: {error_message}",
        }
