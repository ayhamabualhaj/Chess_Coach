from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["tactics", "opening", "middlegame", "endgame", "time_or_focus", "other"]


class Weakness(BaseModel):
    title: str = Field(description="Short name, e.g. 'Leaving pieces undefended'.")
    category: Category
    explanation: str = Field(description="What goes wrong and why it matters.")
    evidence: str = Field(description="Numbers and example moves from the tools.")
    example_game_ids: list[int] = Field(description="Ids of games where it happened.")
    priority: int = Field(ge=1, le=3, description="1 = work on this first, 3 = least urgent.")
    how_to_improve: str = Field(description="Concrete change of habit or thinking.")
    exercises: list[str] = Field(min_length=1, description="2-3 practical exercises.")


class Diagnosis(BaseModel):
    summary: str = Field(description="2-4 sentences about the player overall.")
    weaknesses: list[Weakness] = Field(min_length=1, description="Most important first.")