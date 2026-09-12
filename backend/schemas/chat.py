from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel

class ChatMessageCreate(BaseModel):
    session_id: str
    role: str
    content: str
    message_type: str = "text"
    metadata: Optional[Dict[str, Any]] = None

class ChatMessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    message_type: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True

class SessionDetailOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    title: str
    is_organisation: bool
    source_text: Optional[str] = None
    grounding_md: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    chat_messages: List[ChatMessageOut] = []
    previews: List[Dict[str, Any]] = []
    deliverables: List[Dict[str, Any]] = []

    class Config:
        from_attributes = True
