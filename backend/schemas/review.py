from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel

class PreviewEditRequest(BaseModel):
    session_id: str
    output_type: str
    edited_content: str
    is_organisation: Optional[bool] = False
    accept: bool = False

class PreviewAcceptRequest(BaseModel):
    session_id: str
    output_type: str

class PreviewRecordOut(BaseModel):
    id: str
    session_id: str
    output_type: str
    version: int
    original_preview_path: Optional[str] = None
    original_preview_content: str
    edited_preview_path: Optional[str] = None
    edited_preview_content: Optional[str] = None
    is_accepted: bool
    is_organisation: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
