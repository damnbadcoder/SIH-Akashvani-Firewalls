import json
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.session import SessionRecord
from backend.models.chat import ChatMessage
from backend.models.preview import PreviewRecord
from backend.models.deliverable import DeliverableRecord
from backend.schemas.chat import ChatMessageCreate, ChatMessageOut
from backend.schemas.review import PreviewEditRequest, PreviewRecordOut
from backend.services.preview_service import preview_service

from backend.models.user import User

router = APIRouter(tags=["Chat and History"])

@router.get("/api/history")
def get_chat_history(
    user_id: Optional[str] = None,
    email: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Backend Task 3: Retrieves user chat history and past transformation sessions.
    Formatted to align with frontend Dashboard loadHistory / tx.history structure.
    Isolated by user account (via user_id or email).
    """
    query = db.query(SessionRecord).order_by(SessionRecord.created_at.desc())

    if email and not user_id:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user_id = user.id
        else:
            return []

    if user_id:
        query = query.filter(SessionRecord.user_id == user_id)
    
    sessions = query.limit(50).all()
    results = []

    for s in sessions:
        # Construct frontend-compatible generation object
        deliverables = []
        for d in s.deliverables:
            orig_en = None
            if d.parameters_json:
                try:
                    p = json.loads(d.parameters_json)
                    if isinstance(p, dict):
                        orig_en = p.get("original_english")
                except Exception:
                    pass
            deliverables.append({
                "outputType": d.output_type,
                "content": d.content,
                "retries": 0,
                "originalEnglish": orig_en or d.content,
            })

        previews_by_type = {}
        previews_dict = {}
        citations = []
        for p in s.previews:
            content = p.edited_preview_content or p.original_preview_content
            previews_by_type[p.output_type] = content
            c_used = json.loads(p.citations_json) if p.citations_json else []
            for c in c_used:
                if isinstance(c, dict) and "id" in c:
                    if not any(x.get("id") == c.get("id") for x in citations):
                        citations.append(c)
                elif isinstance(c, str):
                    if not any(x.get("label") == c for x in citations):
                        citations.append({"id": f"src-{len(citations)+1}", "label": c, "kind": "text"})

            previews_dict[p.output_type] = {
                "platform_key": p.output_type,
                "draft_title": f"{p.output_type} Preview",
                "draft_content": content,
                "citations_used": c_used,
                "sensitive_items_flagged": len(json.loads(p.sensitive_flags_json)) if p.sensitive_flags_json else 0,
            }

        file_names = [f.filename for f in s.files]
        links = json.loads(s.source_links_json) if s.source_links_json else []

        selected_outputs = []
        if getattr(s, "selected_outputs_json", None):
            try:
                selected_outputs = json.loads(s.selected_outputs_json)
            except Exception:
                selected_outputs = []
        if not selected_outputs:
            selected_outputs = list(previews_by_type.keys()) or [d["outputType"] for d in deliverables]

        params_by_type = {}
        if getattr(s, "parameters_json", None):
            try:
                params_by_type = json.loads(s.parameters_json)
            except Exception:
                params_by_type = {}

        # Status: 'completed' if deliverables exist, else 'blueprint_ready'
        sess_status = getattr(s, "status", None)
        if not sess_status:
            sess_status = "completed" if deliverables else "blueprint_ready"

        results.append({
            "id": s.id,
            "sessionId": s.id,
            "status": sess_status,
            "title": s.title,
            "createdAt": int(s.created_at.timestamp() * 1000),
            "sourceText": s.source_text or "",
            "fileNames": file_names,
            "links": links,
            "selectedOutputs": selected_outputs,
            "paramsByType": params_by_type,
            "plan": s.grounding_md or "",
            "previewsByType": previews_by_type,
            "previews": previews_dict,
            "citations": citations,
            "deliverables": deliverables,
            "groundingMd": s.grounding_md or "",
            "groundingJson": json.loads(s.grounding_json) if s.grounding_json else {},
            "isOrganisation": s.is_organisation,
        })

    return results

@router.get("/api/history/{session_id}")
def get_session_details(session_id: str, db: Session = Depends(get_db)):
    session = db.query(SessionRecord).filter(SessionRecord.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    chat_messages = [
        {
            "id": m.id,
            "role": m.role,
            "message_type": m.message_type,
            "content": m.content,
            "metadata": json.loads(m.metadata_json) if m.metadata_json else {},
            "created_at": m.created_at.isoformat(),
        }
        for m in session.chat_messages
    ]

    previews = [
        {
            "id": p.id,
            "output_type": p.output_type,
            "version": p.version,
            "original_preview_path": p.original_preview_path,
            "original_preview_content": p.original_preview_content,
            "edited_preview_path": p.edited_preview_path,
            "edited_preview_content": p.edited_preview_content,
            "is_accepted": p.is_accepted,
            "is_organisation": p.is_organisation,
        }
        for p in session.previews
    ]

    deliverables = [
        {
            "id": d.id,
            "output_type": d.output_type,
            "content": d.content,
            "parameters": json.loads(d.parameters_json) if d.parameters_json else {},
            "provenance": json.loads(d.provenance_json) if d.provenance_json else [],
            "verification": json.loads(d.verification_json) if d.verification_json else None,
        }
        for d in session.deliverables
    ]

    return {
        "id": session.id,
        "title": session.title,
        "is_organisation": session.is_organisation,
        "source_text": session.source_text,
        "grounding_md": session.grounding_md,
        "created_at": session.created_at.isoformat(),
        "chat_messages": chat_messages,
        "previews": previews,
        "deliverables": deliverables,
    }

@router.post("/api/previews/{session_id}/edit", response_model=PreviewRecordOut)
def edit_preview_endpoint(session_id: str, payload: PreviewEditRequest, db: Session = Depends(get_db)):
    """
    Phase 2 / Backend Task 2: Review Loop.
    Applies manual or automated edits to Preview.md, storing original and creating Preview_edited.md.
    """
    db_obj = preview_service.apply_backend_review_edit(
        db=db,
        session_id=session_id,
        output_type=payload.output_type,
        edited_content=payload.edited_content,
        is_organisation=bool(payload.is_organisation),
        accept=payload.accept,
    )
    return db_obj

@router.post("/api/previews/{session_id}/autosave")
async def autosave_preview_endpoint(session_id: str, request: Request, db: Session = Depends(get_db)):
    """
    Debounced autosave for active preview drafts.
    Updates edited_preview_content silently without flooding chat logs.
    """
    payload = await request.json()
    output_type = payload.get("output_type") or payload.get("outputType")
    edited_content = payload.get("edited_content") or payload.get("content") or ""
    
    if not output_type:
        raise HTTPException(status_code=400, detail="output_type is required.")
        
    record = (
        db.query(PreviewRecord)
        .filter(PreviewRecord.session_id == session_id, PreviewRecord.output_type == output_type)
        .order_by(PreviewRecord.version.desc())
        .first()
    )
    if not record:
        # Create record if none exists yet
        record = PreviewRecord(
            session_id=session_id,
            output_type=output_type,
            version=1,
            original_preview_content=edited_content,
            edited_preview_content=edited_content,
        )
        db.add(record)
    else:
        record.edited_preview_content = edited_content
        
    db.commit()
    return {"status": "autosaved", "sessionId": session_id, "outputType": output_type}

@router.post("/api/chat/message", response_model=ChatMessageOut)
def send_chat_message(payload: ChatMessageCreate, db: Session = Depends(get_db)):
    msg = ChatMessage(
        session_id=payload.session_id,
        role=payload.role,
        message_type=payload.message_type,
        content=payload.content,
        metadata_json=json.dumps(payload.metadata) if payload.metadata else None,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return ChatMessageOut(
        id=msg.id,
        session_id=msg.session_id,
        role=msg.role,
        content=msg.content,
        message_type=msg.message_type,
        metadata=payload.metadata,
        created_at=msg.created_at,
    )
