import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer
from sqlalchemy.orm import relationship
from backend.database import Base

class ProvenanceRegistryRecord(Base):
    __tablename__ = "provenance_registry"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deliverable_id = Column(String(36), ForeignKey("deliverables.id", ondelete="CASCADE"), nullable=False, index=True)
    revision = Column(Integer, nullable=False, default=1)
    content_hash = Column(String(64), nullable=False, index=True)
    signing_key_id = Column(String(64), nullable=False)
    signature = Column(Text, nullable=False)
    organization = Column(String(255), default="Transmute Threat Intel CERT")
    tlp_level = Column(String(50), default="TLP:AMBER+STRICT")
    output_type = Column(String(100), nullable=False)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    deliverable = relationship("DeliverableRecord", back_populates="provenance_entries")
