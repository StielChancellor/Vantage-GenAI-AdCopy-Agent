"""Copilot conversational AI engine — manages Gemini chat for campaign brief extraction."""
import json
import time
from datetime import datetime, timezone


from backend.app.core.vertex_client import get_generative_model, extract_token_counts, calculate_cost_inr
from backend.app.core.config import get_settings
from backend.app.core.vertex_client import get_generative_model, extract_token_counts, calculate_cost_inr
from backend.app.core.database import get_firestore
from backend.app.models.schemas import CopilotChatRequest, CopilotChatResponse

settings = get_settings()

# ── Brief Field Definitions ─────────────────────────────
AD_COPY_FIELDS = {
    "identity": {
        "label": "Property / Brand Identity",
        "required": True,
        "description": "The hotel, property, or brand name. E.g., 'The Taj Mahal Palace', 'ITC Hotels'.",
    },
    "offer_name": {
        "label": "Offer Name",
        "required": True,
        "description": "The campaign/offer name. E.g., 'Monsoon Spa Retreat', 'Summer Escape'.",
    },
    "inclusions": {
        "label": "Inclusions",
        "required": True,
        "description": "What the offer includes. E.g., 'Breakfast, spa, airport transfer'.",
    },
    "reference_urls": {
        "label": "Reference URLs",
        "required": True,
        "description": "Hotel website URLs for context. Comma-separated if multiple.",
    },
    "google_listings": {
        "label": "Google Listings",
        "required": False,
        "description": "Google Maps listing URLs. Comma-separated if multiple.",
    },
    "campaign_objective": {
        "label": "Campaign Objective",
        "required": False,
        "description": "One of: Awareness, Consideration, Conversion. Leave empty for auto-detect.",
        "valid_values": ["Awareness", "Consideration", "Conversion"],
    },
    "platforms": {
        "label": "Platforms",
        "required": True,
        "description": "Ad platforms to generate for. Valid values: google_search, fb_single_image, fb_carousel, fb_video, pmax, youtube. Comma-separated.",
        "valid_values": [
            "google_search", "fb_single_image", "fb_carousel",
            "fb_video", "pmax", "youtube",
        ],
    },
}

CRM_FIELDS = {
    "identity": {
        "label": "Property / Brand Identity",
        "required": True,
        "description": "The hotel, property, or brand name.",
    },
    "channels": {
        "label": "Channels",
        "required": True,
        "description": "CRM channels to generate for. Valid values: whatsapp, email, app_push. Comma-separated.",
        "valid_values": ["whatsapp", "email", "app_push"],
    },
    "campaign_type": {
        "label": "Campaign Type",
        "required": True,
        "description": "One of: promotional, seasonal, event, loyalty, re-engagement.",
        "valid_values": ["promotional", "seasonal", "event", "loyalty", "re-engagement"],
    },
    "target_audience": {
        "label": "Target Audience",
        "required": True,
        "description": "Who the campaign targets. E.g., 'Luxury leisure travelers aged 30-55'.",
    },
    "offer_details": {
        "label": "Offer Details",
        "required": True,
        "description": "The offer or promotion being communicated.",
    },
    "tone": {
        "label": "Tone",
        "required": False,
        "description": "One of: luxurious, formal, casual, urgent. Defaults to luxurious.",
        "valid_values": ["luxurious", "formal", "casual", "urgent"],
    },
    "schedule": {
        "label": "Schedule",
        "required": False,
        "description": "Campaign start and end dates. Format: 'YYYY-MM-DD to YYYY-MM-DD'.",
    },
    "events": {
        "label": "Events",
        "required": False,
        "description": "Relevant upcoming events to tie into. E.g., 'Diwali, Christmas, New Year'.",
    },
}


def _get_admin_model() -> str:
    """Get admin-configured Gemini model from Firestore."""
    try:
        db = get_firestore()
        doc = db.collection("admin_settings").document("config").get()
        if doc.exists:
            return doc.to_dict().get("default_model", "gemini-2.5-flash")
    except Exception:
        pass
    return "gemini-2.5-flash"


def _build_copilot_system_prompt(mode: str) -> str:
    """Build the system prompt instructing Gemini to return dual output (message + brief)."""
    fields = AD_COPY_FIELDS if mode == "ad_copy" else CRM_FIELDS
    mode_label = "Ad Copy" if mode == "ad_copy" else "CRM Campaign"

    field_lines = []
    for key, info in fields.items():
        req_tag = "REQUIRED" if info["required"] else "optional"
        line = f"  - {key}: {info['label']} ({req_tag}) — {info['description']}"
        if "valid_values" in info:
            line += f" Valid values: {', '.join(info['valid_values'])}."
        field_lines.append(line)
    field_block = "\n".join(field_lines)

    all_field_keys = list(fields.keys())
    brief_template = ",\n    ".join(
        f'"{k}": {{"value": "extracted value or null", "confidence": "confirmed|inferred|missing"}}'
        for k in all_field_keys
    )

    return f"""You are a luxury hospitality marketing copilot. You help marketing professionals build {mode_label} campaign briefs through natural, expert conversation.

YOUR ROLE:
- You are an expert marketing consultant specialising in luxury hospitality.
- Guide the user to provide all brief information through friendly, professional conversation.
- Extract structured data from whatever the user says, in any order.
- When the user provides multiple pieces of information at once, extract ALL of them in a single turn.
- Ask for missing REQUIRED fields naturally — do not interrogate.
- Suggest improvements or best practices when appropriate.
- Be concise but warm. Keep responses under 120 words.

BRIEF FIELDS TO COLLECT:
{field_block}

RESPONSE FORMAT:
You MUST always respond with valid JSON in exactly this structure — no text before or after:
{{
  "message": "Your conversational response to the user",
  "brief": {{
    {brief_template}
  }},
  "ready_to_generate": false,
  "suggestions": ["Quick-reply suggestion 1", "Quick-reply suggestion 2"]
}}

FIELD CONFIDENCE RULES:
- "confirmed" = the user explicitly stated this value.
- "inferred" = you deduced this from context (e.g., user said "Taj Mahal Palace" so you infer a single luxury hotel in Mumbai).
- "missing" = not yet mentioned or discussed.

GENERATION READINESS:
- Set ready_to_generate to true ONLY when ALL REQUIRED fields have confidence "confirmed" or "inferred".
- When ready, your message should summarise the brief and tell the user a summary card will appear.

SUGGESTIONS:
- Provide 2-4 short quick-reply phrases the user might want to say next.
- Make them contextual to what's still missing.

FORMATTING RULES:
- For list-type fields (platforms, channels, urls, events), store as comma-separated strings in the value.
- For schedule, use format "YYYY-MM-DD to YYYY-MM-DD" in the value.
- Always include ALL fields in the brief, even missing ones.
- NEVER output anything outside the JSON structure.
- If the user asks something unrelated, answer briefly in "message" but still include the full brief."""


def _build_conversation_prompt(
    messages: list, current_brief: dict | None
) -> str:
    """Build a single prompt containing conversation history and current brief state."""
    parts = []

    if current_brief:
        parts.append(f"CURRENT BRIEF STATE:\n{json.dumps(current_brief, indent=2)}\n")

    parts.append("CONVERSATION HISTORY:")
    for msg in messages:
        role_label = "USER" if msg.role == "user" else "ASSISTANT"
        # For assistant messages, only include the message text (not the full JSON)
        content = msg.content
        parts.append(f"{role_label}: {content}")

    parts.append(
        "\nRespond to the latest USER message. "
        "Update the brief with any new information extracted. "
        "Return valid JSON only."
    )
    return "\n".join(parts)


async def copilot_chat(request: CopilotChatRequest) -> CopilotChatResponse:
    """Process a copilot chat turn — send conversation to Gemini, get dual output."""
    start_time = time.time()
    model_name = _get_admin_model()

    system_prompt = _build_copilot_system_prompt(request.mode)

    # Cap conversation history to last 20 messages for token management
    recent_messages = request.messages[-20:] if len(request.messages) > 20 else request.messages
    user_prompt = _build_conversation_prompt(recent_messages, request.current_brief)

    model = get_generative_model(model_name, system_instruction=system_prompt)
    response = model.generate_content(user_prompt)

    # Extract tokens
    input_tokens = 0
    output_tokens = 0
    if response.usage_metadata:
        input_tokens = response.usage_metadata.prompt_token_count
        output_tokens = response.usage_metadata.candidates_token_count

    elapsed = round(time.time() - start_time, 2)

    # Parse structured JSON response
    parsed = _parse_copilot_response(response.text, request.mode)

    return CopilotChatResponse(
        message=parsed["message"],
        brief=parsed["brief"],
        ready_to_generate=parsed.get("ready_to_generate", False),
        suggestions=parsed.get("suggestions", []),
        tokens_used=input_tokens + output_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_used=model_name,
    )


def _parse_copilot_response(response_text: str, mode: str) -> dict:
    """Parse Gemini's JSON response, with fallback for malformed output."""
    json_str = response_text.strip()

    # Strip markdown code fences if present
    if "```json" in json_str:
        json_str = json_str.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in json_str:
        json_str = json_str.split("```", 1)[1].split("```", 1)[0]

    try:
        data = json.loads(json_str.strip())
        # Validate structure
        if "message" in data and "brief" in data:
            return data
    except json.JSONDecodeError:
        pass

    # Fallback: treat the whole response as a message with empty brief
    fields = AD_COPY_FIELDS if mode == "ad_copy" else CRM_FIELDS
    empty_brief = {
        key: {"value": None, "confidence": "missing"} for key in fields
    }
    return {
        "message": response_text[:500],
        "brief": empty_brief,
        "ready_to_generate": False,
        "suggestions": [],
    }


# ── Brief Persistence ───────────────────────────────────
def save_brief(user_id: str, mode: str, name: str, brief: dict) -> str:
    """Save a completed brief to Firestore. Returns brief_id."""
    db = get_firestore()
    doc_ref = db.collection("copilot_briefs").document()
    doc_ref.set({
        "user_id": user_id,
        "mode": mode,
        "name": name,
        "brief": brief,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return doc_ref.id


def load_briefs(user_id: str, mode: str) -> list[dict]:
    """Load all saved briefs for a user and mode."""
    db = get_firestore()
    try:
        # Try with ordering (requires composite index)
        docs = (
            db.collection("copilot_briefs")
            .where("user_id", "==", user_id)
            .where("mode", "==", mode)
            .order_by("created_at", direction="DESCENDING")
            .limit(20)
            .stream()
        )
        results = []
        for doc in docs:
            data = doc.to_dict()
            data["brief_id"] = doc.id
            results.append(data)
        return results
    except Exception:
        # Fallback: query without ordering if composite index missing
        docs = (
            db.collection("copilot_briefs")
            .where("user_id", "==", user_id)
            .where("mode", "==", mode)
            .limit(20)
            .stream()
        )
        results = []
        for doc in docs:
            data = doc.to_dict()
            data["brief_id"] = doc.id
            results.append(data)
        # Sort client-side
        results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return results


def delete_brief(brief_id: str, user_id: str) -> bool:
    """Delete a saved brief (only if owned by user)."""
    db = get_firestore()
    doc = db.collection("copilot_briefs").document(brief_id).get()
    if doc.exists and doc.to_dict().get("user_id") == user_id:
        db.collection("copilot_briefs").document(brief_id).delete()
        return True
    return False
