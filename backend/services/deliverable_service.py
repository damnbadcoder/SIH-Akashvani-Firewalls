import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from final_post_pipeline import generate_final_deliverable
from backend.models.deliverable import DeliverableRecord
from backend.models.session import SessionRecord
from backend.models.chat import ChatMessage

class DeliverableService:
    @staticmethod
    def generate_and_persist_deliverable(
        db: Session,
        session_id: str,
        platform_key: str,
        routed_draft: str,
        content_md: str,
        metadata_json: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Phase 5: Final LLM Node creates deliverables.
        Backend Task 3: Persists deliverable and chat history to database for user retrieval.
        """
        # Call final generation pipeline
        res = generate_final_deliverable(
            platform_key=platform_key,
            approved_draft=routed_draft,
            content_md=content_md,
            metadata_json=metadata_json,
            parameters=parameters,
        )

        final_content = res.final_content
        provenance = [p.model_dump() for p in res.provenance]
        verification = getattr(res, "verification", None)

        # 1. Persist to PostgreSQL DeliverableRecord
        deliverable_record = DeliverableRecord(
            session_id=session_id,
            output_type=platform_key,
            content=final_content,
            parameters_json=json.dumps(parameters),
            provenance_json=json.dumps(provenance),
            verification_json=json.dumps(verification) if verification else None,
        )
        db.add(deliverable_record)

        # 2. Persist to PostgreSQL ChatMessage for Chat History
        chat_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            message_type="deliverable_output",
            content=final_content,
            metadata_json=json.dumps({
                "output_type": platform_key,
                "provenance": provenance,
                "verification": verification,
            }),
        )
        db.add(chat_msg)

        # Update Session
        session = db.query(SessionRecord).filter(SessionRecord.id == session_id).first()
        if session:
            session.updated_at = session.updated_at

        db.commit()
        db.refresh(deliverable_record)

        return {
            "content": final_content,
            "final_content": final_content,
            "provenance": provenance,
            "verification": verification,
            "deliverable_id": deliverable_record.id,
            "session_id": session_id,
        }

deliverable_service = DeliverableService()
