import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from final_post_pipeline import generate_final_deliverable, strip_preview_wrappers
from backend.models.deliverable import DeliverableRecord
from backend.models.provenance_registry import ProvenanceRegistryRecord
from backend.models.session import SessionRecord
from backend.models.chat import ChatMessage
from backend.services.signing import signing_service
from backend.config import settings

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
        Backend Task 3 & T9: Persists deliverable, cryptographically signs with Ed25519,
        records into public provenance registry, and logs chat history.
        """
        # Call final generation pipeline
        res = generate_final_deliverable(
            platform_key=platform_key,
            approved_draft=routed_draft,
            content_md=content_md,
            metadata_json=metadata_json,
            parameters=parameters,
        )

        final_content = strip_preview_wrappers(res.final_content)
        provenance = [p.model_dump() for p in res.provenance]
        verification = getattr(res, "verification", None)
        relinked_citations = getattr(res, "relinked_citations", None)
        readability = getattr(res, "readability", None)

        if not readability:
            try:
                from enhancements.readability_scorer import score_readability
                readability = score_readability(final_content, platform_key)
            except Exception:
                readability = None

        # 1. Fetch or create DeliverableRecord
        existing_deliv = (
            db.query(DeliverableRecord)
            .filter(
                DeliverableRecord.session_id == session_id,
                DeliverableRecord.output_type == platform_key,
            )
            .first()
        )
        
        if existing_deliv:
            revision = (existing_deliv.revision or 1) + 1
            existing_deliv.content = final_content
            existing_deliv.parameters_json = json.dumps(parameters)
            existing_deliv.provenance_json = json.dumps(provenance)
            existing_deliv.verification_json = json.dumps(verification) if verification else None
            existing_deliv.revision = revision
            deliverable_record = existing_deliv
        else:
            revision = 1
            deliverable_record = DeliverableRecord(
                session_id=session_id,
                output_type=platform_key,
                content=final_content,
                parameters_json=json.dumps(parameters),
                provenance_json=json.dumps(provenance),
                verification_json=json.dumps(verification) if verification else None,
                revision=revision,
            )
            db.add(deliverable_record)
            db.flush()  # Ensures deliverable_record.id is generated

        # 2. T9: Cryptographic Signing with Ed25519 & Envelope Generation
        org_name = (
            parameters.get("organization")
            or (metadata_json.get("organization") if isinstance(metadata_json, dict) else None)
            or settings.DEFAULT_SIGNING_ORG
        )
        tlp = (
            parameters.get("tlp_level")
            or (metadata_json.get("tlp_level") if isinstance(metadata_json, dict) else None)
            or settings.DEFAULT_TLP_LEVEL
        )

        signing_envelope = signing_service.sign_deliverable(
            content=final_content,
            deliverable_id=deliverable_record.id,
            output_type=platform_key,
            revision=revision,
            organization=org_name,
            tlp_level=tlp,
        )

        deliverable_record.signature = signing_envelope["signature"]
        deliverable_record.signing_key_id = signing_envelope["signing_key_id"]
        deliverable_record.content_hash = signing_envelope["content_sha256"]
        deliverable_record.signature_metadata_json = json.dumps(signing_envelope)

        # 3. T9: Register in Provenance Registry (historical versioning ledger)
        registry_entry = ProvenanceRegistryRecord(
            deliverable_id=deliverable_record.id,
            revision=revision,
            content_hash=signing_envelope["content_sha256"],
            signing_key_id=signing_envelope["signing_key_id"],
            signature=signing_envelope["signature"],
            organization=signing_envelope["organization"],
            tlp_level=signing_envelope["tlp_level"],
            output_type=platform_key,
            metadata_json=json.dumps({
                "timestamp": signing_envelope["timestamp"],
                "verification_url": signing_envelope["verification_url"],
            }),
        )
        db.add(registry_entry)

        # 4. Persist to ChatMessage for Chat History
        chat_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            message_type="deliverable_output",
            content=final_content,
            metadata_json=json.dumps({
                "output_type": platform_key,
                "provenance": provenance,
                "verification": verification,
                "relinked_citations": relinked_citations,
                "readability": readability,
                "signature": signing_envelope["signature"],
                "signing_key_id": signing_envelope["signing_key_id"],
                "content_hash": signing_envelope["content_sha256"],
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
            "relinked_citations": relinked_citations,
            "readability": readability,
            "deliverable_id": deliverable_record.id,
            "session_id": session_id,
            "signature": signing_envelope["signature"],
            "signing_key_id": signing_envelope["signing_key_id"],
            "content_hash": signing_envelope["content_sha256"],
            "signature_envelope": signing_envelope,
            "qr_data_url": signing_envelope.get("qr_data_url"),
            "verification_url": signing_envelope.get("verification_url"),
            "revision": revision,
        }

    @staticmethod
    def create_revision(
        db: Session,
        deliverable_id: str,
        updated_content: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Creates a new revision of an existing deliverable, recalculates SHA-256,
        signs with active Ed25519 key, and registers in provenance ledger.
        """
        deliverable = db.query(DeliverableRecord).filter(DeliverableRecord.id == deliverable_id).first()
        if not deliverable:
            raise ValueError(f"Deliverable with ID '{deliverable_id}' not found.")

        clean_content = strip_preview_wrappers(updated_content)
        new_revision = (deliverable.revision or 1) + 1
        deliverable.content = clean_content
        deliverable.revision = new_revision

        params = parameters or {}
        if deliverable.parameters_json:
            try:
                existing_params = json.loads(deliverable.parameters_json)
                existing_params.update(params)
                params = existing_params
            except Exception:
                pass
        deliverable.parameters_json = json.dumps(params)

        org_name = params.get("organization") or settings.DEFAULT_SIGNING_ORG
        tlp = params.get("tlp_level") or settings.DEFAULT_TLP_LEVEL

        signing_envelope = signing_service.sign_deliverable(
            content=clean_content,
            deliverable_id=deliverable.id,
            output_type=deliverable.output_type,
            revision=new_revision,
            organization=org_name,
            tlp_level=tlp,
        )

        deliverable.signature = signing_envelope["signature"]
        deliverable.signing_key_id = signing_envelope["signing_key_id"]
        deliverable.content_hash = signing_envelope["content_sha256"]
        deliverable.signature_metadata_json = json.dumps(signing_envelope)

        registry_entry = ProvenanceRegistryRecord(
            deliverable_id=deliverable.id,
            revision=new_revision,
            content_hash=signing_envelope["content_sha256"],
            signing_key_id=signing_envelope["signing_key_id"],
            signature=signing_envelope["signature"],
            organization=signing_envelope["organization"],
            tlp_level=signing_envelope["tlp_level"],
            output_type=deliverable.output_type,
            metadata_json=json.dumps({
                "timestamp": signing_envelope["timestamp"],
                "verification_url": signing_envelope["verification_url"],
            }),
        )
        db.add(registry_entry)
        db.commit()
        db.refresh(deliverable)

        return {
            "deliverable_id": deliverable.id,
            "output_type": deliverable.output_type,
            "revision": new_revision,
            "content": clean_content,
            "signature": signing_envelope["signature"],
            "signing_key_id": signing_envelope["signing_key_id"],
            "content_hash": signing_envelope["content_sha256"],
            "signature_envelope": signing_envelope,
            "qr_data_url": signing_envelope.get("qr_data_url"),
            "verification_url": signing_envelope.get("verification_url"),
        }

deliverable_service = DeliverableService()
