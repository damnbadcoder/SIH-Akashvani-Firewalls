import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.database import Base

class PreviewRecord(Base):
    __tablename__ = "previews"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False, index=True)
    output_type = Column(String(100), nullable=False)
    version = Column(Integer, default=1)
    
    # Storage of original Preview.md file and edited preview file
    original_preview_path = Column(String(512), nullable=True)
    original_preview_content = Column(Text, nullable=False)
    edited_preview_path = Column(String(512), nullable=True)
    edited_preview_content = Column(Text, nullable=True)
    
    is_accepted = Column(Boolean, default=False)
    is_organisation = Column(Boolean, default=False)
    sensitive_flags_json = Column(Text, nullable=True)
    citations_json = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    session = relationship("SessionRecord", back_populates="previews")
