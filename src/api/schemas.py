from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class EventIn(BaseModel):
    """Event payload received from an external webhook sender."""

    id: str = Field(min_length=1, max_length=64)
    type: str = Field(min_length=1, max_length=100)
    occurred_at: datetime
    data: dict[str, Any] = Field(default_factory=dict)


class EventAccepted(BaseModel):
    """Response returned after the event is durably stored."""

    id: str
    status: Literal["accepted", "duplicate"]