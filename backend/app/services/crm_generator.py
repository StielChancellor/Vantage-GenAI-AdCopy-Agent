"""CRM content generation for WhatsApp, Email, and App Push campaigns.

Generates channel-specific marketing messages with calendar scheduling.
WhatsApp has strict character limits; Email and App Push have soft guidance.
"""
import io
import csv
import json
import time
from datetime import datetime, timezone, timedelta


from backend.app.core.vertex_client import get_generative_model, extract_token_counts, calculate_cost_inr
from backend.app.core.config import get_settings
from backend.app.core.vertex_client import get_generative_model, extract_token_counts, calculate_cost_inr
from backend.app.core.database import get_firestore
from backend.app.services.profile_insights import get_or_create_profile
from backend.app.services.training_engine import get_training_directives
from backend.app.services.rag_engine import get_brand_usps
from backend.app.models.schemas import (
    CRMGenerateRequest, CRMGenerateResponse, CRMContentOutput,
    CRMRefineRequest,
)

settings = get_settings()

# Channel specifications
CRM_CHANNEL_SPECS = {
    "whatsapp": {
        "name": "WhatsApp",
        "max_chars": 1024,
        "strict": True,
        "supports_subject": False,
        "supports_cta_button": True,
        "message_count": 3,
    },
    "email": {
        "name": "Email",
        "max_chars": 2000,
        "strict": False,
        "supports_subject": True,
        "supports_cta_button": True,
        "message_count": 3,
    },
    "app_push": {
        "name": "App Push Notification",
        "title_max_chars": 50,
        "body_max_chars": 128,
        "max_chars": 178,
        "strict": False,
        "supports_subject": True,
        "supports_cta_button": False,
        "message_count": 5,
    },
}

# Day name mapping
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _get_admin_model() -> str:
    """Get the admin-configured default model from Firestore."""
    try:
        db = get_firestore()
        doc = db.collection("admin_settings").document("config").get()
        if doc.exists:
            return doc.to_dict().get("default_model", "gemini-2.5-flash")
    except Exception:
        pass
    return "gemini-2.5-flash"


async def generate_crm_content(request: CRMGenerateRequest) -> CRMGenerateResponse:
    """Generate CRM campaign content for selected channels with calendar."""
    start_time = time.time()
    model_name = _get_admin_model()

    # 1. Gather context
    # Hotel profile (cached)
    profile = await get_or_create_profile(
        request.hotel_name,
        request.reference_urls,
        request.google_listing_urls,
    )

    # Training directives (global — no hotel_name filter)
    directives = get_training_directives()

    # Brand USPs (rag_engine.get_brand_usps is async — must await; otherwise
    # brand_data ends up as a coroutine and downstream .get() raises 500.)
    try:
        brand_data = await get_brand_usps(request.hotel_name)
    except Exception:
        brand_data = None

    # 2. Build prompts
    system_prompt = _build_crm_system_prompt(request.channels, brand_data)
    user_prompt = _build_crm_user_prompt(request, profile, directives, brand_data)

    # 3. Call Gemini
    model = get_generative_model(model_name, system_instruction=system_prompt)
    response = model.generate_content(user_prompt)

    # 4. Parse response
    input_tokens = 0
    output_tokens = 0
    if response.usage_metadata:
        input_tokens = response.usage_metadata.prompt_token_count
        output_tokens = response.usage_metadata.candidates_token_count

    content_outputs = _parse_crm_response(response.text, request.channels)

    # 5. Generate calendar
    calendar = _generate_calendar(
        content_outputs,
        request.schedule_start,
        request.schedule_end,
        request.frequency,
        channel_frequencies=getattr(request, 'channel_frequencies', {}),
    )

    elapsed = round(time.time() - start_time, 2)

    return CRMGenerateResponse(
        hotel_name=request.hotel_name,
        content=content_outputs,
        calendar=calendar,
        tokens_used=input_tokens + output_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_used=model_name,
        time_seconds=elapsed,
    )


async def refine_crm_content(request: CRMRefineRequest) -> CRMGenerateResponse:
    """Refine CRM content based on user feedback."""
    start_time = time.time()
    model_name = _get_admin_model()

    previous_json = json.dumps(
        [
            {
                "channel": c.channel,
                "messages": c.messages,
                "warnings": c.warnings,
            }
            for c in request.previous_content
        ],
        indent=2,
    )

    system_prompt = """You are an expert CRM copywriter for luxury hotels. Refine previously generated
CRM campaign content based on user feedback.

RULES:
- Apply the feedback precisely.
- Maintain all character limits for each channel.
- Only change what the feedback requests. Keep everything else intact.
- WhatsApp: STRICT 1024 char limit per message.
- Email: 2000 char soft guidance.
- App Push: title 50 chars, body 128 chars soft guidance.
- Output ONLY valid JSON matching the same format as the input."""

    # Build channel specs reminder
    channel_specs = ""
    for ch in request.channels:
        spec = CRM_CHANNEL_SPECS.get(ch, {})
        if spec:
            limit_type = "STRICT" if spec.get("strict") else "soft"
            channel_specs += f"\n- {spec['name']}: {spec['max_chars']} chars ({limit_type})"

    user_prompt = f"""## CONTEXT:
- Hotel: {request.hotel_name}

## CHARACTER LIMITS:{channel_specs}

## PREVIOUS CRM CONTENT:
```json
{previous_json}
```

## USER FEEDBACK:
{request.feedback}

## INSTRUCTIONS:
Apply the feedback. Return the FULL updated JSON array (all channels, all messages), not just changed items.

```json
[
  {{
    "channel": "channel_name",
    "messages": [
      {{"subject": "optional subject", "body": "message body", "cta": "call to action"}}
    ]
  }}
]
```"""

    model = get_generative_model(model_name, system_instruction=system_prompt)
    response = model.generate_content(user_prompt)

    input_tokens = 0
    output_tokens = 0
    if response.usage_metadata:
        input_tokens = response.usage_metadata.prompt_token_count
        output_tokens = response.usage_metadata.candidates_token_count

    content_outputs = _parse_crm_response(response.text, request.channels)

    # Regenerate calendar with updated content
    calendar = request.previous_calendar  # Keep existing calendar structure

    elapsed = round(time.time() - start_time, 2)

    return CRMGenerateResponse(
        hotel_name=request.hotel_name,
        content=content_outputs,
        calendar=calendar,
        tokens_used=input_tokens + output_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_used=model_name,
        time_seconds=elapsed,
    )


def export_calendar_csv(calendar: list[dict]) -> str:
    """Export calendar data as CSV string with full message fields."""
    output = io.StringIO()
    fieldnames = ["day", "date", "time_range", "channel", "headline", "body", "subject", "cta", "message_preview"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for entry in calendar:
        writer.writerow({f: entry.get(f, "") for f in fieldnames})
    return output.getvalue()


def _build_crm_system_prompt(channels: list[str], brand_data: dict | None) -> str:
    """Build system prompt with channel specs and brand guardrails."""
    base = """You are an expert CRM copywriter for luxury hotels. You create high-converting
marketing messages for WhatsApp, Email, and App Push campaigns.

CHANNEL RULES:"""

    for ch in channels:
        spec = CRM_CHANNEL_SPECS.get(ch, {})
        if spec:
            limit_type = "STRICT — messages exceeding this WILL be rejected" if spec.get("strict") else "soft guidance"
            base += f"\n\n{spec['name']}:"
            base += f"\n- Character limit: {spec['max_chars']} chars ({limit_type})"
            base += f"\n- Generate {spec['message_count']} message variants"
            if spec.get("supports_subject"):
                base += "\n- Include a subject/title line"
            if spec.get("supports_cta_button"):
                base += "\n- Include a clear CTA (call-to-action)"
            if ch == "app_push":
                base += f"\n- Title: max {spec.get('title_max_chars', 50)} chars"
                base += f"\n- Body: max {spec.get('body_max_chars', 128)} chars"

    base += """

GENERAL RULES:
- Messages should feel personal and luxurious
- Include specific offer details and dates
- Use power words that drive urgency and desire
- Each variant must be unique — no duplicates
- Output ONLY valid JSON"""

    if brand_data:
        if brand_data.get("restricted_keywords"):
            keywords = ", ".join(brand_data["restricted_keywords"])
            base += f"\n\nSTRICT RESTRICTION: NEVER use: [{keywords}]"
        if brand_data.get("negative_keywords"):
            neg = ", ".join(brand_data["negative_keywords"])
            base += f"\nAVOID: [{neg}]"

    return base


def _build_crm_user_prompt(
    request: CRMGenerateRequest,
    profile: dict,
    directives: list[dict],
    brand_data: dict | None,
) -> str:
    """Build user prompt with all context for CRM generation."""
    # Event context
    event_context = ""
    if request.events:
        event_context = "\n\n## UPCOMING EVENTS (use for timing and messaging):\n"
        for e in request.events:
            event_context += f"- {e.get('title', '')} ({e.get('date', '')}): {e.get('description', '')}\n"

    # Profile context
    profile_context = ""
    if profile.get("website_summary"):
        profile_context += f"\n\n## HOTEL PROFILE:\n{profile['website_summary']}"
    if profile.get("review_summary"):
        profile_context += f"\n\n## GUEST SENTIMENT ({profile.get('rating', 'N/A')}★):\n{profile['review_summary']}"
    if profile.get("key_usps"):
        profile_context += "\n\n## KEY USPs:\n- " + "\n- ".join(profile["key_usps"])

    # Training directive context
    directive_context = ""
    if directives:
        for d in directives:
            content = d.get("content", {})
            if content.get("insight_text"):
                directive_context += f"\n\n## TRAINING INSIGHTS:\n{content['insight_text']}"
            if content.get("recommended_tone"):
                directive_context += f"\nRecommended Tone: {content['recommended_tone']}"

    # Brand USP context
    usp_context = ""
    if brand_data:
        if brand_data.get("usps"):
            usp_context += "\n\n## BRAND USPs:\n- " + "\n- ".join(brand_data["usps"])
        if brand_data.get("positive_keywords"):
            usp_context += "\n\n## PREFERRED KEYWORDS:\n- " + "\n- ".join(brand_data["positive_keywords"])

    # Channel output format
    output_format = []
    for ch in request.channels:
        spec = CRM_CHANNEL_SPECS.get(ch, {})
        if spec:
            msg_format = '{"headline": "short attention-grabbing headline", "body": "message text", "cta": "call to action"}'
            if spec.get("supports_subject"):
                msg_format = '{"headline": "short attention-grabbing headline", "subject": "subject/title", "body": "message body", "cta": "call to action"}'
            output_format.append(f'  {{"channel": "{ch}", "messages": [{msg_format}, ...]}}')

    prompt = f"""Generate CRM campaign messages with the following details:

## CAMPAIGN DETAILS:
- Hotel: {request.hotel_name}
- Campaign Type: {request.campaign_type}
- Target Audience: {request.target_audience}
- Offer: {request.offer_details}
- Tone: {request.tone}
{f'- Inclusions: {request.inclusions}' if request.inclusions else ''}
{f'- Additional Info: {request.other_info}' if request.other_info else ''}
{f'- Schedule: {request.schedule_start} to {request.schedule_end}, {request.frequency}' if request.schedule_start else ''}
{event_context}
{profile_context}
{directive_context}
{usp_context}

## OUTPUT FORMAT:
Return ONLY a JSON array:
```json
[
{chr(10).join(output_format)}
]
```

For each channel, generate exactly {max(spec.get('message_count', 3) for spec in [CRM_CHANNEL_SPECS.get(ch, {}) for ch in request.channels] if spec)} unique message variants.
Ensure EVERY message respects the character limits specified above. Count characters carefully.
For WhatsApp: STRICT 1024 char max — no exceptions."""

    return prompt


def _parse_crm_response(response_text: str, channels: list[str]) -> list[CRMContentOutput]:
    """Parse Gemini response into CRMContentOutput objects with validation."""
    json_str = response_text
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0]
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0]

    try:
        data = json.loads(json_str.strip())
    except json.JSONDecodeError:
        return [
            CRMContentOutput(
                channel=channels[0] if channels else "unknown",
                messages=[{"body": response_text[:500], "cta": "Learn More"}],
                warnings=["Failed to parse AI response — raw text returned"],
            )
        ]

    outputs = []
    for item in data:
        channel = item.get("channel", "unknown")
        spec = CRM_CHANNEL_SPECS.get(channel, {})
        messages = item.get("messages", [])
        warnings = []

        # Validate character limits
        for i, msg in enumerate(messages):
            body = msg.get("body", "")
            subject = msg.get("subject", "")
            char_count = len(body) + len(subject)
            msg["char_count"] = char_count

            if spec:
                max_chars = spec.get("max_chars", 9999)
                if char_count > max_chars:
                    if spec.get("strict"):
                        warnings.append(
                            f"Message {i+1} exceeds STRICT {max_chars} char limit ({char_count} chars)"
                        )
                    else:
                        warnings.append(
                            f"Message {i+1} exceeds recommended {max_chars} char limit ({char_count} chars)"
                        )

                # App push specific validation
                if channel == "app_push":
                    if len(subject) > spec.get("title_max_chars", 50):
                        warnings.append(f"Message {i+1} title exceeds {spec.get('title_max_chars', 50)} chars")
                    if len(body) > spec.get("body_max_chars", 128):
                        warnings.append(f"Message {i+1} body exceeds {spec.get('body_max_chars', 128)} chars")

        outputs.append(
            CRMContentOutput(
                channel=channel,
                messages=messages,
                warnings=warnings,
            )
        )

    return outputs


def _generate_calendar(
    content: list[CRMContentOutput],
    schedule_start: str,
    schedule_end: str,
    frequency: str,
    channel_frequencies: dict | None = None,
) -> list[dict]:
    """Generate a campaign calendar distributing messages across the schedule.

    Supports per-channel frequency via channel_frequencies dict.
    Falls back to uniform frequency when channel_frequencies is empty.

    Returns list of {day, date, time_range, channel, headline, body, subject, cta, message_preview}.
    """
    if not schedule_start or not schedule_end:
        return []

    try:
        start = datetime.fromisoformat(schedule_start)
        end = datetime.fromisoformat(schedule_end)
    except (ValueError, TypeError):
        return []

    # Optimal time ranges per channel
    time_ranges = {
        "whatsapp": "10:00 AM - 12:00 PM",
        "email": "9:00 AM - 11:00 AM",
        "app_push": "6:00 PM - 8:00 PM",
    }

    # Day abbreviation to weekday index mapping
    day_to_idx = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

    calendar = []

    # Build a lookup: channel -> messages
    channel_messages = {}
    for cc in content:
        channel_messages[cc.channel] = cc.messages or []

    if channel_frequencies:
        # Per-channel independent scheduling
        for channel_content in content:
            ch = channel_content.channel
            messages = channel_content.messages
            if not messages:
                continue

            freq_config = channel_frequencies.get(ch, {})
            send_days = freq_config.get("days", ["Mon"])
            every_n_weeks = freq_config.get("every_n_weeks", 1)
            duration_weeks = freq_config.get("duration_weeks", None)

            # Convert day names to weekday indices
            send_day_indices = set()
            for d in send_days:
                if d in day_to_idx:
                    send_day_indices.add(day_to_idx[d])

            if not send_day_indices:
                send_day_indices = {0}  # Default Monday

            # Calculate effective end date
            ch_end = end
            if duration_weeks:
                ch_end = min(end, start + timedelta(weeks=duration_weeks))

            msg_idx = 0
            current = start
            week_count = 0
            last_week_num = None

            while current <= ch_end:
                current_week = current.isocalendar()[1]

                # Track week transitions for every_n_weeks logic
                if last_week_num is not None and current_week != last_week_num:
                    week_count += 1
                last_week_num = current_week

                # Only send on designated weeks (every N weeks)
                if week_count % every_n_weeks == 0 and current.weekday() in send_day_indices:
                    msg = messages[msg_idx % len(messages)]
                    headline = msg.get("headline", "")
                    body = msg.get("body", "")
                    subject = msg.get("subject", "")
                    cta = msg.get("cta", "")

                    preview = body[:50]
                    if subject:
                        preview = f"[{subject}] {preview}"

                    calendar.append({
                        "day": DAY_NAMES[current.weekday()],
                        "date": current.strftime("%Y-%m-%d"),
                        "time_range": time_ranges.get(ch, "10:00 AM - 12:00 PM"),
                        "channel": ch,
                        "headline": headline,
                        "body": body,
                        "subject": subject,
                        "cta": cta,
                        "message_preview": preview + ("..." if len(body) > 50 else ""),
                    })
                    msg_idx += 1

                current += timedelta(days=1)
    else:
        # Uniform frequency fallback
        intervals = {
            "daily": timedelta(days=1),
            "weekly": timedelta(weeks=1),
            "biweekly": timedelta(weeks=2),
            "monthly": timedelta(days=30),
        }
        interval = intervals.get(frequency, timedelta(weeks=1))
        msg_indices = {ch: 0 for ch in [c.channel for c in content]}
        current = start

        while current <= end:
            for channel_content in content:
                ch = channel_content.channel
                messages = channel_content.messages
                if not messages:
                    continue

                idx = msg_indices.get(ch, 0)
                msg = messages[idx % len(messages)]

                headline = msg.get("headline", "")
                body = msg.get("body", "")
                subject = msg.get("subject", "")
                cta = msg.get("cta", "")

                preview = body[:50]
                if subject:
                    preview = f"[{subject}] {preview}"

                calendar.append({
                    "day": DAY_NAMES[current.weekday()],
                    "date": current.strftime("%Y-%m-%d"),
                    "time_range": time_ranges.get(ch, "10:00 AM - 12:00 PM"),
                    "channel": ch,
                    "headline": headline,
                    "body": body,
                    "subject": subject,
                    "cta": cta,
                    "message_preview": preview + ("..." if len(body) > 50 else ""),
                })

                msg_indices[ch] = idx + 1

            current += interval

    # Sort by date
    calendar.sort(key=lambda x: x["date"])
    return calendar
