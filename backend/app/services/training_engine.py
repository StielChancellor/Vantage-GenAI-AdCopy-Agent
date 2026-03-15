"""AI Training Engine — auto-enhance CSV data with Gemini Q&A and admin approval.

Flow:
1. Admin uploads CSV → parsed data sent to Gemini for auto-analysis
2. Gemini returns structured directives + clarification questions
3. Admin answers questions → Gemini refines directives
4. Admin approves → directives saved to Firestore for use in generation
"""
import json
import uuid
from datetime import datetime, timezone

import pandas as pd
import google.generativeai as genai

from backend.app.core.config import get_settings
from backend.app.core.database import get_firestore
from backend.app.models.schemas import TrainingUploadResponse

settings = get_settings()


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


def start_training_session(hotel_name: str, csv_type: str, df: pd.DataFrame) -> TrainingUploadResponse:
    """Start a training session from uploaded CSV data.

    Args:
        hotel_name: Hotel name extracted from CSV or provided by admin
        csv_type: "historical_ads" or "brand_usp"
        df: Parsed DataFrame from uploaded CSV

    Returns:
        TrainingUploadResponse with session_id, questions, and directive preview
    """
    db = get_firestore()
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model_name = _get_admin_model()

    session_id = str(uuid.uuid4())

    # Parse CSV data into text for Gemini analysis
    csv_summary = _summarize_csv(df, csv_type)

    # Build the meta-prompt for auto-analysis + question generation
    if csv_type == "historical_ads":
        prompt = f"""You are an expert advertising data analyst. Analyze this historical ad performance data
for "{hotel_name}" and:

1. Generate a comprehensive training directive (structured insights about what works)
2. Generate 3-5 clarification questions for the admin to refine the directive

DATA:
{csv_summary}

Return ONLY valid JSON:
{{
  "directive": {{
    "insight_text": "2-3 paragraph summary of performance patterns, what works, what to avoid",
    "top_headlines": ["top 5 best-performing headlines"],
    "top_descriptions": ["top 5 best-performing descriptions"],
    "patterns": ["5-8 actionable findings with specific numbers"],
    "recommended_tone": "suggested tone based on best performers",
    "power_words": ["words that drove high CTR/CVR"],
    "avoid_words": ["words from low performers to avoid"]
  }},
  "questions": [
    {{
      "question_id": 1,
      "question": "What is the primary campaign objective for this hotel?",
      "options": ["Brand Awareness", "Direct Bookings", "Seasonal Promotion", "Loyalty"],
      "default": "Direct Bookings"
    }},
    {{
      "question_id": 2,
      "question": "Which guest segment should the ads primarily target?",
      "options": ["Luxury Travelers", "Business Travelers", "Families", "Couples", "All"],
      "default": "All"
    }}
  ]
}}"""
    else:
        prompt = f"""You are a hotel brand strategist. Analyze this brand & USP data for "{hotel_name}" and:

1. Generate enhanced brand guidelines as a training directive
2. Generate 3-5 clarification questions to refine the brand positioning

DATA:
{csv_summary}

Return ONLY valid JSON:
{{
  "directive": {{
    "brand_positioning": "1-2 sentence brand positioning statement",
    "enhanced_usps": ["refined and expanded USPs"],
    "tone_guidelines": "recommended tone and voice for this brand",
    "target_audience": "primary target audience description",
    "competitive_advantages": ["key differentiators"],
    "messaging_pillars": ["3-5 core messaging themes"]
  }},
  "questions": [
    {{
      "question_id": 1,
      "question": "What is the hotel's star rating or tier?",
      "options": ["5-star Luxury", "4-star Premium", "3-star Mid-range", "Boutique"],
      "default": "5-star Luxury"
    }}
  ]
}}"""

    try:
        model = genai.GenerativeModel(
            model_name,
            system_instruction="You are an expert at analyzing advertising and brand data. Return ONLY valid JSON.",
        )
        response = model.generate_content(prompt)

        json_str = response.text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        result = json.loads(json_str.strip())

        directive = result.get("directive", {})
        questions = result.get("questions", [])

        # Store session in Firestore
        session_doc = {
            "session_id": session_id,
            "hotel_name": hotel_name,
            "csv_type": csv_type,
            "status": "questions_pending",
            "directive_preview": directive,
            "questions": questions,
            "answers": [],
            "csv_summary": csv_summary[:5000],  # Store summary for follow-ups
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        db.collection("training_state").document(session_id).set(session_doc)

        return TrainingUploadResponse(
            session_id=session_id,
            status="questions_pending",
            questions=questions,
            directive_preview=directive,
        )

    except Exception as e:
        return TrainingUploadResponse(
            session_id=session_id,
            status="error",
            questions=[],
            directive_preview={"error": str(e)[:200]},
        )


def answer_training_questions(
    session_id: str,
    answers: list[dict],
    approve: bool = False,
) -> TrainingUploadResponse:
    """Submit answers to training questions and optionally approve the directive.

    Args:
        session_id: Training session ID
        answers: List of {question_id: int, answer: str}
        approve: If True, finalize and save the directive
    """
    db = get_firestore()
    session_ref = db.collection("training_state").document(session_id)
    session_doc = session_ref.get()

    if not session_doc.exists:
        return TrainingUploadResponse(
            session_id=session_id,
            status="error",
            questions=[],
            directive_preview={"error": "Session not found"},
        )

    session = session_doc.to_dict()

    if approve:
        # Finalize: store directive in training_directives
        directive = session.get("directive_preview", {})
        directive_doc = {
            "hotel_name": session["hotel_name"],
            "directive_type": session["csv_type"],
            "content": directive,
            "status": "approved",
            "questions": session.get("questions", []),
            "answers": answers,
            "created_at": session.get("created_at", ""),
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }

        # Upsert: remove old directives of same type for this hotel
        existing = list(
            db.collection("training_directives")
            .where("hotel_name", "==", session["hotel_name"])
            .where("directive_type", "==", session["csv_type"])
            .stream()
        )
        for edoc in existing:
            edoc.reference.delete()

        db.collection("training_directives").add(directive_doc)

        # Also update ad_insights if this is historical_ads type
        if session["csv_type"] == "historical_ads":
            _update_ad_insights(session["hotel_name"], directive)

        # Update session status
        session_ref.update({
            "status": "approved",
            "answers": answers,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        })

        return TrainingUploadResponse(
            session_id=session_id,
            status="approved",
            questions=[],
            directive_preview=directive,
        )

    # Not approving yet — refine the directive with answers
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model_name = _get_admin_model()

    answers_text = "\n".join(
        [f"Q{a.get('question_id', '?')}: {a.get('answer', '')}" for a in answers]
    )

    prompt = f"""You previously analyzed data for "{session['hotel_name']}" and generated this directive:

{json.dumps(session.get('directive_preview', {}), indent=2)}

The admin provided these answers to your questions:
{answers_text}

Based on these answers, refine and improve the directive. Also generate 1-3 follow-up questions
if you need more clarity, or return an empty questions array if the directive is ready for approval.

Return ONLY valid JSON:
{{
  "directive": {{ ... refined directive with same structure as before ... }},
  "questions": [ ... follow-up questions or empty array ... ]
}}"""

    try:
        model = genai.GenerativeModel(
            model_name,
            system_instruction="Refine training directives based on admin feedback. Return ONLY valid JSON.",
        )
        response = model.generate_content(prompt)

        json_str = response.text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        result = json.loads(json_str.strip())
        directive = result.get("directive", session.get("directive_preview", {}))
        questions = result.get("questions", [])

        status = "questions_pending" if questions else "ready_for_approval"

        # Update session
        session_ref.update({
            "directive_preview": directive,
            "questions": questions,
            "answers": answers,
            "status": status,
        })

        return TrainingUploadResponse(
            session_id=session_id,
            status=status,
            questions=questions,
            directive_preview=directive,
        )

    except Exception as e:
        return TrainingUploadResponse(
            session_id=session_id,
            status="error",
            questions=[],
            directive_preview={"error": str(e)[:200]},
        )


def get_training_directives(hotel_name: str) -> list[dict]:
    """Retrieve all approved training directives for a hotel.

    Used by ad_generator and crm_generator to enrich prompts.
    """
    db = get_firestore()
    docs = list(
        db.collection("training_directives")
        .where("hotel_name", "==", hotel_name)
        .where("status", "==", "approved")
        .stream()
    )
    return [doc.to_dict() for doc in docs]


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


def _update_ad_insights(hotel_name: str, directive: dict) -> None:
    """Update ad_insights collection with training directive data."""
    db = get_firestore()

    insight_doc = {
        "hotel_name": hotel_name,
        "insight_text": directive.get("insight_text", ""),
        "top_headlines": directive.get("top_headlines", []),
        "top_descriptions": directive.get("top_descriptions", []),
        "patterns": directive.get("patterns", []),
        "source": "training",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Upsert
    existing = list(
        db.collection("ad_insights")
        .where("hotel_name", "==", hotel_name)
        .stream()
    )
    for edoc in existing:
        edoc.reference.delete()

    db.collection("ad_insights").add(insight_doc)


def _summarize_csv(df: pd.DataFrame, csv_type: str) -> str:
    """Summarize CSV DataFrame into text for Gemini analysis."""
    lines = [f"Columns: {', '.join(df.columns.tolist())}"]
    lines.append(f"Total rows: {len(df)}")

    # Include sample rows (first 50 for analysis, more would hit token limits)
    sample = df.head(50)
    for idx, row in sample.iterrows():
        row_text = " | ".join(
            [f"{col}: {str(val)}" for col, val in row.items() if pd.notna(val) and str(val).strip()]
        )
        if row_text:
            lines.append(f"Row {idx + 1}: {row_text}")

    # Add basic stats for numeric columns
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    for col in numeric_cols:
        lines.append(f"Stats for {col}: mean={df[col].mean():.2f}, max={df[col].max():.2f}, min={df[col].min():.2f}")

    return "\n".join(lines)
