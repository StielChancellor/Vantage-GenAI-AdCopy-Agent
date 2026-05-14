"""Campaign Ideation services (v2.7).

- `critique_engine.next_critique_turn` — multi-turn Gemini critique chat.
- `shortlist_generator.generate_shortlist` — produces the 10-item concept list.
"""
from backend.app.services.ideation.critique_engine import next_critique_turn
from backend.app.services.ideation.shortlist_generator import generate_shortlist

__all__ = ["next_critique_turn", "generate_shortlist"]
