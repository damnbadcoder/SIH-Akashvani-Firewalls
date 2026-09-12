import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer
from sqlalchemy.orm import relationship
from backend.database import Base

class DeliverableRecord(Base):
    __tablename__ = "deliverables"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False, index=True)
    output_type = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    file_path = Column(String(512), nullable=True)
    parameters_json = Column(Text, nullable=True)
    provenance_json = Column(Text, nullable=True)
    verification_json = Column(Text, nullable=True)

    # T9 Cryptographic Signing & Provenance
    signature = Column(Text, nullable=True)
    signing_key_id = Column(String(64), nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)
    signature_metadata_json = Column(Text, nullable=True)
    revision = Column(Integer, default=1)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("SessionRecord", back_populates="deliverables")
    provenance_entries = relationship("ProvenanceRegistryRecord", back_populates="deliverable", cascade="all, delete-orphan")
