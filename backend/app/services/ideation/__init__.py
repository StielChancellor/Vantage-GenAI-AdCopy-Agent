"""Campaign Ideation services.

v2.7 (legacy, still used for in-progress chat-coach ideations):
- `critique_engine.next_critique_turn`
- `shortlist_generator.generate_shortlist`

v2.8 (current — Form -> Directions -> Final 10 -> Handoff):
- `hotels_resolver.resolve_hotels` — natural-language phrase -> hotel_ids.
- `direction_generator.generate_directions` — 3-5 directions x 5 concepts.
- `finalizer.generate_final_concepts` — exactly 10 polished concepts.
"""
from backend.app.services.ideation.critique_engine import next_critique_turn
from backend.app.services.ideation.shortlist_generator import generate_shortlist
from backend.app.services.ideation.hotels_resolver import resolve_hotels
from backend.app.services.ideation.discount_resolver import resolve_discount
from backend.app.services.ideation.direction_generator import generate_directions
from backend.app.services.ideation.finalizer import generate_final_concepts
from backend.app.services.ideation.campaign_id import (
    generate_campaign_id, ensure_campaign_id,
)
from backend.app.services.ideation import exporters

__all__ = [
    "next_critique_turn",
    "generate_shortlist",
    "resolve_hotels",
    "resolve_discount",
    "generate_directions",
    "generate_final_concepts",
    "generate_campaign_id",
    "ensure_campaign_id",
    "exporters",
]
