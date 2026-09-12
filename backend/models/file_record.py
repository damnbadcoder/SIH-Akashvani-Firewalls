import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.database import Base

class FileRecord(Base):
    __tablename__ = "files"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)  # 'text', 'audio', 'video', 'image', 'cyber'
    file_format = Column(String(50), nullable=False)  # '.pdf', '.docx', '.stix', etc.
    file_size = Column(Integer, default=0)
    file_path = Column(String(512), nullable=True)
    sha256 = Column(String(64), nullable=True)
    extracted_markdown = Column(Text, nullable=True)
    extracted_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("SessionRecord", back_populates="files")
