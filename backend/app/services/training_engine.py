"""AI Training Engine — Phase 2.1 Overhaul.

Supports 3 training modes (CSV, Text, CSV+Text), 3 section types
(ad_performance, brand_usp, crm_performance), hero/KPI columns,
append/replace directives, token tracking, and cost calculation.
"""
import io
import csv
import json
import time
import uuid
from datetime import datetime, timezone

import pandas as pd
import google.generativeai as genai

from backend.app.core.config import get_settings
from backend.app.core.database import get_firestore
from backend.app.models.schemas import TrainingUploadResponse

settings = get_settings()

# Approximate pricing per million tokens (USD→INR ≈ 84)
MODEL_PRICING = {
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-pro": {"input": 3.50, "output": 10.50},
}
USD_TO_INR = 84


def _get_admin_model() -> str:
    try:
        db = get_firestore()
        doc = db.collection("admin_settings").document("config").get()
        if doc.exists:
            return doc.to_dict().get("default_model", "gemini-2.5-flash")
    except Exception:
        pass
    return "gemini-2.5-flash"


def _calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model_name, MODEL_PRICING["gemini-2.5-flash"])
    cost_usd = (input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing["output"]
    return round(cost_usd * USD_TO_INR, 4)


def _extract_tokens(response) -> tuple[int, int]:
    try:
        meta = response.usage_metadata
        return meta.prompt_token_count or 0, meta.candidates_token_count or 0
    except Exception:
        return 0, 0


def _parse_json(text: str) -> dict:
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return json.loads(text.strip())


def start_training_session(
    section_type: str,
    training_mode: str,
    df: pd.DataFrame | None = None,
    text_input: str = "",
    kpi_columns: list[str] | None = None,
    hero_columns: list[dict] | None = None,
) -> TrainingUploadResponse:
    """Start a training session with flexible input modes."""
    db = get_firestore()
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model_name = _get_admin_model()
    session_id = str(uuid.uuid4())
    start_time = time.time()

    csv_summary = ""
    if df is not None and not df.empty:
        csv_summary = _summarize_csv(df, section_type)

    kpi_context = ""
    if kpi_columns:
        kpi_context = f"\n\nFOCUS: Optimize analysis around these KPI columns: {', '.join(kpi_columns)}"

    hero_context = ""
    if hero_columns:
        hero_parts = [f"{h['column']} — {h.get('description', 'primary metric')}" for h in hero_columns]
        hero_context = f"\n\nHERO COLUMNS (pay special attention): {'; '.join(hero_parts)}"

    text_context = ""
    if text_input.strip():
        text_context = f"\n\nADMIN INSTRUCTIONS & CONTEXT:\n{text_input.strip()}"

    # Build prompt based on section_type
    data_section = ""
    if csv_summary:
        data_section = f"\n\nDATA:\n{csv_summary}"

    prompt = _build_training_prompt(section_type, data_section, kpi_context, hero_context, text_context)

    try:
        model = genai.GenerativeModel(
            model_name,
            system_instruction="You are an expert at analyzing marketing data. Return ONLY valid JSON.",
        )
        response = model.generate_content(prompt)
        input_tokens, output_tokens = _extract_tokens(response)
        elapsed = round(time.time() - start_time, 2)

        result = _parse_json(response.text)
        directive = result.get("directive", {})
        questions = result.get("questions", [])

        session_doc = {
            "session_id": session_id,
            "section_type": section_type,
            "training_mode": training_mode,
            "status": "questions_pending",
            "directive_preview": directive,
            "questions": questions,
            "answers": [],
            "csv_summary": csv_summary[:5000] if csv_summary else "",
            "text_input": text_input[:5000] if text_input else "",
            "kpi_columns": kpi_columns or [],
            "hero_columns": hero_columns or [],
            "save_mode": None,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "time_seconds": elapsed,
            "cost_inr": _calculate_cost(model_name, input_tokens, output_tokens),
            "model_used": model_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }
        db.collection("training_state").document(session_id).set(session_doc)

        return TrainingUploadResponse(
            session_id=session_id,
            status="questions_pending",
            questions=questions,
            directive_preview=directive,
        )

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        session_doc = {
            "session_id": session_id,
            "section_type": section_type,
            "training_mode": training_mode,
            "status": "error",
            "directive_preview": {"error": str(e)[:200]},
            "questions": [],
            "answers": [],
            "input_tokens": 0,
            "output_tokens": 0,
            "time_seconds": elapsed,
            "cost_inr": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }
        db.collection("training_state").document(session_id).set(session_doc)
        return TrainingUploadResponse(
            session_id=session_id,
            status="error",
            questions=[],
            directive_preview={"error": str(e)[:200]},
        )


def _build_training_prompt(section_type, data_section, kpi_context, hero_context, text_context):
    if section_type == "ad_performance":
        return f"""You are an expert advertising data analyst. Analyze this data and:

1. Generate a comprehensive training directive (structured insights about what works)
2. Generate 3-5 clarification questions
{kpi_context}{hero_context}{data_section}{text_context}

Return ONLY valid JSON:
{{
  "directive": {{
    "insight_text": "2-3 paragraph summary of patterns",
    "top_headlines": ["top 5 headlines"],
    "top_descriptions": ["top 5 descriptions"],
    "patterns": ["5-8 actionable findings with numbers"],
    "recommended_tone": "suggested tone",
    "power_words": ["high-CTR words"],
    "avoid_words": ["low-performer words"]
  }},
  "questions": [
    {{"question_id": 1, "question": "...", "options": ["..."], "default": "..."}}
  ]
}}"""

    elif section_type == "brand_usp":
        return f"""You are a hotel brand strategist. Analyze this data and:

1. Generate enhanced brand guidelines as a training directive
2. Generate 3-5 clarification questions
{kpi_context}{hero_context}{data_section}{text_context}

Return ONLY valid JSON:
{{
  "directive": {{
    "brand_positioning": "1-2 sentence positioning",
    "enhanced_usps": ["refined USPs"],
    "tone_guidelines": "recommended voice",
    "target_audience": "primary audience",
    "competitive_advantages": ["differentiators"],
    "messaging_pillars": ["3-5 themes"]
  }},
  "questions": [
    {{"question_id": 1, "question": "...", "options": ["..."], "default": "..."}}
  ]
}}"""

    else:  # crm_performance
        return f"""You are a CRM performance analyst for hospitality. Analyze this CRM campaign data and:

1. Generate insights about what drives engagement across channels (WhatsApp, Email, App Push)
2. Generate 3-5 clarification questions
{kpi_context}{hero_context}{data_section}{text_context}

Return ONLY valid JSON:
{{
  "directive": {{
    "insight_text": "2-3 paragraph analysis of channel performance",
    "top_performing_messages": ["best messages by channel"],
    "channel_insights": {{"whatsapp": "...", "email": "...", "app_push": "..."}},
    "patterns": ["actionable findings"],
    "recommended_timing": "best send times based on data",
    "audience_insights": "target audience recommendations",
    "recommended_tone": "tone that drives engagement",
    "power_words": ["high-engagement words"],
    "avoid_words": ["low-engagement words"]
  }},
  "questions": [
    {{"question_id": 1, "question": "...", "options": ["..."], "default": "..."}}
  ]
}}"""


def answer_training_questions(
    session_id: str,
    answers: list[dict],
    approve: bool = False,
    save_mode: str | None = None,
) -> TrainingUploadResponse:
    """Submit answers and optionally approve with append/replace mode."""
    db = get_firestore()
    session_ref = db.collection("training_state").document(session_id)
    session_doc = session_ref.get()

    if not session_doc.exists:
        return TrainingUploadResponse(
            session_id=session_id, status="error",
            directive_preview={"error": "Session not found"},
        )

    session = session_doc.to_dict()
    start_time = time.time()

    if approve:
        directive = session.get("directive_preview", {})
        section_type = session.get("section_type", session.get("csv_type", "ad_performance"))

        directive_doc = {
            "directive_type": section_type,
            "content": directive,
            "status": "approved",
            "questions": session.get("questions", []),
            "answers": answers,
            "created_at": session.get("created_at", ""),
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }

        effective_save_mode = save_mode or "replace"

        if effective_save_mode == "replace":
            existing = list(
                db.collection("training_directives")
                .where("directive_type", "==", section_type)
                .where("status", "==", "approved")
                .stream()
            )
            for edoc in existing:
                edoc.reference.delete()

        db.collection("training_directives").add(directive_doc)

        if section_type == "ad_performance":
            _update_ad_insights(directive)

        elapsed = round(time.time() - start_time, 2)
        prev_tokens_in = session.get("input_tokens", 0)
        prev_tokens_out = session.get("output_tokens", 0)

        session_ref.update({
            "status": "approved",
            "answers": answers,
            "save_mode": effective_save_mode,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "time_seconds": session.get("time_seconds", 0) + elapsed,
        })

        return TrainingUploadResponse(
            session_id=session_id, status="approved",
            questions=[], directive_preview=directive,
        )

    # Refine directive with answers
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model_name = _get_admin_model()

    answers_text = "\n".join(
        [f"Q{a.get('question_id', '?')}: {a.get('answer', '')}" for a in answers]
    )

    prompt = f"""You previously analyzed data and generated this directive:

{json.dumps(session.get('directive_preview', {}), indent=2)}

The admin provided these answers:
{answers_text}

Refine the directive. Generate 1-3 follow-up questions if needed, or empty array if ready.

Return ONLY valid JSON:
{{
  "directive": {{ ... refined directive ... }},
  "questions": [ ... follow-ups or empty ... ]
}}"""

    try:
        model = genai.GenerativeModel(
            model_name,
            system_instruction="Refine training directives based on admin feedback. Return ONLY valid JSON.",
        )
        response = model.generate_content(prompt)
        new_in, new_out = _extract_tokens(response)
        elapsed = round(time.time() - start_time, 2)

        result = _parse_json(response.text)
        directive = result.get("directive", session.get("directive_preview", {}))
        questions = result.get("questions", [])

        status = "questions_pending" if questions else "ready_for_approval"
        total_in = session.get("input_tokens", 0) + new_in
        total_out = session.get("output_tokens", 0) + new_out
        total_time = session.get("time_seconds", 0) + elapsed

        session_ref.update({
            "directive_preview": directive,
            "questions": questions,
            "answers": answers,
            "status": status,
            "input_tokens": total_in,
            "output_tokens": total_out,
            "time_seconds": total_time,
            "cost_inr": _calculate_cost(model_name, total_in, total_out),
        })

        return TrainingUploadResponse(
            session_id=session_id, status=status,
            questions=questions, directive_preview=directive,
        )

    except Exception as e:
        return TrainingUploadResponse(
            session_id=session_id, status="error",
            directive_preview={"error": str(e)[:200]},
        )


def get_training_directives(section_type: str | None = None) -> list[dict]:
    """Retrieve all approved training directives globally, optionally by section."""
    db = get_firestore()
    query = db.collection("training_directives").where("status", "==", "approved")
    if section_type:
        query = query.where("directive_type", "==", section_type)
    docs = list(query.stream())
    result = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        result.append(d)
    return result


def get_training_sessions(limit: int = 20) -> list[dict]:
    """List recent training sessions for admin view."""
    db = get_firestore()
    docs = list(
        db.collection("training_state")
        .order_by("created_at", direction="DESCENDING")
        .limit(limit)
        .stream()
    )
    return [doc.to_dict() for doc in docs]


def export_sessions_csv(limit: int = 500) -> str:
    """Export training sessions as CSV string."""
    sessions = get_training_sessions(limit=limit)
    output = io.StringIO()
    fieldnames = [
        "session_id", "section_type", "training_mode", "status", "save_mode",
        "input_tokens", "output_tokens", "cost_inr", "time_seconds",
        "created_at", "completed_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for s in sessions:
        writer.writerow({f: s.get(f, "") for f in fieldnames})
    return output.getvalue()


def _update_ad_insights(directive: dict) -> None:
    """Update global ad_insights with training directive data."""
    db = get_firestore()
    insight_doc = {
        "hotel_name": "_global",
        "insight_text": directive.get("insight_text", ""),
        "top_headlines": directive.get("top_headlines", []),
        "top_descriptions": directive.get("top_descriptions", []),
        "patterns": directive.get("patterns", []),
        "source": "training",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    existing = list(
        db.collection("ad_insights")
        .where("hotel_name", "==", "_global")
        .where("source", "==", "training")
        .stream()
    )
    for edoc in existing:
        edoc.reference.delete()
    db.collection("ad_insights").add(insight_doc)


def _summarize_csv(df: pd.DataFrame, section_type: str) -> str:
    """Summarize CSV DataFrame into text for Gemini analysis."""
    lines = [f"Columns: {', '.join(df.columns.tolist())}"]
    lines.append(f"Total rows: {len(df)}")
    sample = df.head(50)
    for idx, row in sample.iterrows():
        row_text = " | ".join(
            [f"{col}: {str(val)}" for col, val in row.items() if pd.notna(val) and str(val).strip()]
        )
        if row_text:
            lines.append(f"Row {idx + 1}: {row_text}")
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    for col in numeric_cols:
        lines.append(f"Stats for {col}: mean={df[col].mean():.2f}, max={df[col].max():.2f}, min={df[col].min():.2f}")
    return "\n".join(lines)
