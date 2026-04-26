import os
import json

from groq import Groq

# ---------------------------------------------------------------------------
# Response JSON schema:
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

MODEL = "llama-3.3-70b-versatile"

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

FOLLOWUP_SYSTEM_INSTRUCTION = (
    "You are a Senior Solutions Architect and Full Stack developer helping a user refine "
    "their software project plan. The conversation history contains the original project "
    "description and the structured plan you generated. Answer the user's follow-up questions "
    "or apply requested changes clearly and helpfully."
)


def _get_client() -> Groq:
    """Return a configured Groq client."""
    return Groq(api_key=os.getenv("GROQ_API_KEY"))


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences that LLMs sometimes wrap JSON in."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (e.g. ```json or ```)
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def generate_project_plan(form_data: dict) -> dict:
    """
    Call Groq to generate a full structured project plan from form data.

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

    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "user",   "content": user_prompt},
    ]

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.4,
        )
        raw_text = response.choices[0].message.content

        # Strip markdown fences before parsing
        cleaned = _strip_code_fences(raw_text)
        parsed = json.loads(cleaned)

        return {"success": True, "data": parsed}

    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Groq returned invalid JSON: {str(e)}",
        }
    except Exception as e:
        error_message = str(e)
        if "429" in error_message or "rate" in error_message.lower() or "quota" in error_message.lower():
            return {
                "success": False,
                "error": "Groq API rate limit reached. Please wait a moment and try again.",
            }
        return {
            "success": False,
            "error": f"Groq API error: {error_message}",
        }


def send_followup_message(chat_messages: list, user_message: str) -> dict:
    """
    Send a follow-up message to Groq using the full conversation history for context.

    Groq uses OpenAI-style roles: "system", "user", "assistant".
    DB already stores "user" and "assistant" — no role mapping needed.

    chat_messages: list of Message model instances (ordered by created_at).
    user_message:  The plain-text content of the new user message.

    Returns:
        { "success": True, "data": <response_text> }
        or
        { "success": False, "error": "<message>" }
    """
    # Start with a system message to set the follow-up context
    messages = [{"role": "system", "content": FOLLOWUP_SYSTEM_INSTRUCTION}]

    # Append full conversation history — roles map directly from DB ("user"/"assistant")
    for msg in chat_messages:
        messages.append({"role": msg.role, "content": msg.content})

    # Append the new user message
    messages.append({"role": "user", "content": user_message})

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
        )
        return {"success": True, "data": response.choices[0].message.content}

    except Exception as e:
        error_message = str(e)
        if "429" in error_message or "rate" in error_message.lower() or "quota" in error_message.lower():
            return {
                "success": False,
                "error": "Groq API rate limit reached. Please wait a moment and try again.",
            }
        return {
            "success": False,
            "error": f"Groq API error: {error_message}",
        }
