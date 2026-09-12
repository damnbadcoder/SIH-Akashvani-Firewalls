from pydantic import BaseModel
from typing import List

class RelinkMatch(BaseModel):
    original_sentence: str
    edited_sentence: str
    citation_marker: str
    similarity_score: float
    relinked: bool

class RelinkResult(BaseModel):
    relinked_text: str
    relinked_count: int
    matches: List[RelinkMatch]
