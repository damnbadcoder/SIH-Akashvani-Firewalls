import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from preview_pipeline import generate_previews
from backend.services.storage_service import storage_service
from backend.models.preview import PreviewRecord
from backend.models.session import SessionRecord
from backend.models.chat import ChatMessage

try:
    from enhancements.sensitivity_checker import scan_and_redact
except ImportError:
    def scan_and_redact(text: str, is_organization: bool = False):
        return text, []

class PreviewService:
    @staticmethod
    def generate_initial_previews(
        db: Session,
        session_id: str,
        enhanced_md: str,
        enhanced_json: Dict[str, Any],
        selected_outputs: List[str],
        parameters: Dict[str, Any],
        is_organisation: bool = False,
    ) -> Dict[str, Any]:
        """
        Phase 2: Initial LLM node generates Preview.md and category drafts.
        Backend Task 2: Saves original Preview.md and stores initial records in DB.
        """
        result = generate_previews(
            content_md=enhanced_md,
            metadata_json=enhanced_json,
            selected_outputs=selected_outputs,
            parameters=parameters,
            is_organization=is_organisation,
        )

        previews_by_type = {}
        previews_dict = {}

        for key, p_obj in result.previews.items():
            content = p_obj.draft_content
            flags = p_obj.sensitive_flags or []
            
            if is_organisation and not flags:
                content, flags = scan_and_redact(content, is_organization=True)
                p_obj.draft_content = content
                p_obj.sensitive_flags = flags

            previews_by_type[key] = content
            previews_dict[p_obj.display_name] = {
                "platform_key": key,
                "output_type_id": key,
                "draft_title": p_obj.draft_title,
                "draft_content": content,
                "citations_used": p_obj.citations_used,
                "sensitive_items_flagged": len(flags),
                "sensitive_flags": [f.model_dump() if hasattr(f, "model_dump") else f for f in flags],
            }

            # Save original Preview.md to disk
            original_path = storage_service.save_original_preview(
                session_id=session_id,
                output_type=key,
                content=content,
            )

            # Store in Database
            db_preview = PreviewRecord(
                session_id=session_id,
                output_type=key,
                version=1,
                original_preview_path=original_path,
                original_preview_content=content,
                edited_preview_path=None,
                edited_preview_content=None,
                is_accepted=False,
                is_organisation=is_organisation,
                sensitive_flags_json=json.dumps([f.model_dump() if hasattr(f, "model_dump") else str(f) for f in flags]),
                citations_json=json.dumps(p_obj.citations_used),
            )
            db.add(db_preview)

        # Log system message into ChatMessage history
        chat_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            message_type="preview_generated",
            content=f"Generated previews for {len(selected_outputs)} deliverable format(s). Saved original Preview.md.",
            metadata_json=json.dumps({"selected_outputs": selected_outputs}),
        )
        db.add(chat_msg)
        db.commit()

        default_plan = result.source_summary
        if selected_outputs and selected_outputs[0] in previews_by_type:
            default_plan = previews_by_type[selected_outputs[0]]

        return {
            "plan": default_plan,
            "previewsByType": previews_by_type,
            "previews": previews_dict,
            "source_summary": result.source_summary,
            "extracted_facts": result.extracted_facts,
            "metadata_anchors": result.metadata_anchors,
        }

    @staticmethod
    def apply_backend_review_edit(
        db: Session,
        session_id: str,
        output_type: str,
        edited_content: str,
        is_organisation: bool = False,
        accept: bool = False,
    ) -> PreviewRecord:
        """
        Backend Task 2: Backend Review.
        Saves user/automated edits into Preview_edited.md while keeping original Preview.md intact.
        """
        # Find latest preview record for this session & output_type
        record = (
            db.query(PreviewRecord)
            .filter(PreviewRecord.session_id == session_id, PreviewRecord.output_type == output_type)
            .order_by(PreviewRecord.version.desc())
            .first()
        )

        new_version = (record.version + 1) if record else 1
        flags = []
        if is_organisation:
            edited_content, flags = scan_and_redact(edited_content, is_organization=True)

        # Save to Preview_edited.md
        edited_path = storage_service.save_edited_preview(
            session_id=session_id,
            output_type=output_type,
            content=edited_content,
            version=new_version,
        )

        if record:
            record.version = new_version
            record.edited_preview_path = edited_path
            record.edited_preview_content = edited_content
            record.is_accepted = accept
            record.sensitive_flags_json = json.dumps([f.model_dump() if hasattr(f, "model_dump") else str(f) for f in flags])
            db_obj = record
        else:
            db_obj = PreviewRecord(
                session_id=session_id,
                output_type=output_type,
                version=new_version,
                original_preview_path=edited_path,
                original_preview_content=edited_content,
                edited_preview_path=edited_path,
                edited_preview_content=edited_content,
                is_accepted=accept,
                is_organisation=is_organisation,
                sensitive_flags_json=json.dumps([f.model_dump() if hasattr(f, "model_dump") else str(f) for f in flags]),
            )
            db.add(db_obj)

        chat_msg = ChatMessage(
            session_id=session_id,
            role="user" if not accept else "system",
            message_type="preview_review",
            content=f"Applied review edit to preview '{output_type}' (v{new_version}). Accepted: {accept}.",
            metadata_json=json.dumps({"version": new_version, "output_type": output_type, "is_accepted": accept}),
        )
        db.add(chat_msg)
        db.commit()
        db.refresh(db_obj)
        return db_obj

preview_service = PreviewService()
