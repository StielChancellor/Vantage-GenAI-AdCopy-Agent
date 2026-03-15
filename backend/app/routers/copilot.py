"""Copilot chat and brief management endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from backend.app.core.auth import get_current_user
from backend.app.models.schemas import CopilotChatRequest, CopilotChatResponse
from backend.app.services.copilot_engine import (
    copilot_chat,
    save_brief,
    load_briefs,
    delete_brief,
)

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.post("/chat", response_model=CopilotChatResponse)
async def chat(
    request: CopilotChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """Process a copilot chat turn — returns conversational response + brief extraction."""
    try:
        result = await copilot_chat(request)
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "quota" in error_msg.lower():
            raise HTTPException(status_code=429, detail="Gemini API quota exceeded.")
        raise HTTPException(status_code=500, detail=f"Chat failed: {error_msg[:200]}")
    return result


@router.post("/briefs/save")
async def save_brief_endpoint(
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    """Save a completed brief as a reusable template."""
    brief_id = save_brief(
        user_id=current_user["sub"],
        mode=body.get("mode", "ad_copy"),
        name=body.get("name", "Untitled Brief"),
        brief=body.get("brief", {}),
    )
    return {"brief_id": brief_id, "status": "saved"}


@router.get("/briefs/{mode}")
async def get_briefs(
    mode: str,
    current_user: dict = Depends(get_current_user),
):
    """Load saved briefs for the current user and mode."""
    briefs = load_briefs(user_id=current_user["sub"], mode=mode)
    return {"briefs": briefs}


@router.delete("/briefs/{brief_id}")
async def remove_brief(
    brief_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a saved brief."""
    success = delete_brief(brief_id, user_id=current_user["sub"])
    if not success:
        raise HTTPException(
            status_code=404, detail="Brief not found or not owned by user"
        )
    return {"status": "deleted"}
