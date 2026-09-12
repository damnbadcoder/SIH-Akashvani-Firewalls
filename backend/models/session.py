import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.database import Base

class SessionRecord(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    title = Column(String(255), default="Intelligence Transformation Session")
    is_organisation = Column(Boolean, default=False)
    source_text = Column(Text, nullable=True)
    source_links_json = Column(Text, nullable=True)
    grounding_md = Column(Text, nullable=True)
    grounding_json = Column(Text, nullable=True)
    status = Column(String(50), default="blueprint_ready")
    selected_outputs_json = Column(Text, nullable=True)
    parameters_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="sessions")
    files = relationship("FileRecord", back_populates="session", cascade="all, delete-orphan")
    previews = relationship("PreviewRecord", back_populates="session", cascade="all, delete-orphan")
    deliverables = relationship("DeliverableRecord", back_populates="session", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
