import os
import json
import re
import tempfile
import traceback
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.session import SessionRecord
from backend.models.file_record import FileRecord
from backend.models.chat import ChatMessage
from backend.schemas.pipeline import (
    GeneratePlanResponse,
    DeliverableResponse,
    PlatformPreview,
    Citation,
)
from backend.services.storage_service import storage_service
from backend.services.router_service import router_service, ALL_SUPPORTED_EXTENSIONS
from backend.services.context_service import enhancer_1_node
from backend.services.preview_service import preview_service
from backend.services.branching_service import branching_service
from backend.services.conditional_service import conditional_routing_service
from backend.services.deliverable_service import deliverable_service

router = APIRouter(tags=["Pipeline Orchestration"])

KEY_MAPPING = {
    "advisory": "advisory",
    "executive_summary": "exec_summary",
    "exec_summary": "exec_summary",
    "incident_report": "incident_report",
    "linkedin": "linkedin_post",
    "linkedin_post": "linkedin_post",
    "twitter": "social_thread",
    "social_thread": "social_thread",
    "presentation": "slide_deck",
    "slide_deck": "slide_deck",
    "video_package": "video_script",
    "video_script": "video_script",
    "infographic": "playbook",
    "playbook": "playbook",
    "press_release": "press_release",
}


@router.post("/api/generate-plan")
@router.post("/api/preview")
async def generate_plan_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Phase 1: Data Ingestion & Context Generation (Multi-modal 46 formats routing & md + json convergence)
    Phase 2: Context Enhancement (Enhancer-1 node) & Preview.md Generation
    """
    content_type = request.headers.get("Content-Type", "")

    source_text = ""
    source_links: List[str] = []
    outputs_raw: List[Dict[str, Any]] = []
    is_organisation = False
    uploaded_files: List[Tuple[str, bytes]] = []
    parameters: Dict[str, Any] = {}

    if "multipart/form-data" in content_type:
        form = await request.form()
        source_text = str(form.get("sourceText", "") or "")
        links_str = str(form.get("sourceLinks", "[]") or "[]")
        outputs_str = str(form.get("outputs", "[]") or "[]")
        is_org_val = form.get("isOrganisation", "false")
        is_organisation = str(is_org_val).lower() in ("true", "1", "yes")

        try:
            source_links = json.loads(links_str) if isinstance(links_str, str) else []
        except Exception:
            source_links = []

        try:
            outputs_raw = json.loads(outputs_str) if isinstance(outputs_str, str) else []
        except Exception:
            outputs_raw = []

        for field_name, value in form.multi_items():
            if field_name == "files" and hasattr(value, "filename") and value.filename:
                file_bytes = await value.read()
                uploaded_files.append((value.filename, file_bytes))

    else:
        payload = await request.json()
        source_text = payload.get("sourceText") or payload.get("content_md") or ""
        source_links = payload.get("sourceLinks") or []
        outputs_raw = payload.get("outputs") or []
        selected_outputs_list = payload.get("selected_outputs") or []
        parameters = payload.get("parameters") or {}
        is_organisation = bool(
            payload.get("isOrganisation", False) or payload.get("is_organization", False)
        )

        if not outputs_raw and selected_outputs_list:
            outputs_raw = [{"id": k, "params": parameters} for k in selected_outputs_list]

    # Map output categories and collect parameters
    selected_keys = []
    merged_params = dict(parameters)

    for out in outputs_raw:
        oid = out.get("id", "")
        pkey = KEY_MAPPING.get(oid, oid)
        if pkey not in selected_keys:
            selected_keys.append(pkey)
        if "params" in out and isinstance(out["params"], dict):
            merged_params.update(out["params"])

    if not selected_keys:
        selected_keys = ["linkedin_post", "advisory"]

    # 1. Create DB Session
    session = SessionRecord(
        title=f"Transformation: {selected_keys[0]} ({len(selected_keys)} outputs)",
        is_organisation=is_organisation,
        source_text=source_text,
        source_links_json=json.dumps(source_links),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # -------------------------------------------------------------------------
    # PHASE 1: Data Ingestion & Pipeline Routing (46 formats)
    # -------------------------------------------------------------------------
    extracted_md_sections = []
    citations: List[Citation] = []
    raw_citations_list: List[Dict[str, Any]] = []

    for idx, (filename, file_bytes) in enumerate(uploaded_files, 1):
        file_path, sha, file_size = storage_service.save_upload(
            session_id=session.id,
            filename=filename,
            data=file_bytes,
        )
        ext = Path(filename).suffix.lower()
        pipeline_type = router_service.detect_media_pipeline(filename)

        # Route through specific processing pipeline based on media type
        processed = router_service.process_file_into_context(file_path, filename)
        markdown_chunk = processed["markdown"]
        file_citations = processed["citations"]
        structured_meta = processed["metadata"]

        if markdown_chunk:
            extracted_md_sections.append(markdown_chunk)

        # Save FileRecord in PostgreSQL
        file_rec = FileRecord(
            session_id=session.id,
            filename=filename,
            file_type=pipeline_type,
            file_format=ext,
            file_size=file_size,
            file_path=file_path,
            sha256=sha,
            extracted_markdown=markdown_chunk,
            extracted_json=json.dumps(structured_meta),
        )
        db.add(file_rec)

        citations.append(Citation(id=f"src-{idx}", label=filename, kind="file"))
        raw_citations_list.append({"id": f"src-{idx}", "label": filename, "kind": "file"})
        for c in file_citations:
            citations.append(Citation(id=c["id"], label=c["label"], kind=c.get("kind", "file")))
            raw_citations_list.append(c)

    # Convergence: Merge all pipeline outputs into foundational Context (md + json)
    if extracted_md_sections:
        if source_text and source_text.strip():
            foundational_md = f"{source_text.strip()}\n\n---\n\n" + "\n\n".join(extracted_md_sections)
        else:
            foundational_md = "\n\n".join(extracted_md_sections)
    else:
        foundational_md = source_text

    if not citations and source_text and source_text.strip():
        citations.append(Citation(id="src-1", label="Raw Telemetry & Advisory Input", kind="text"))
        raw_citations_list.append({"id": "src-1", "label": "Raw Telemetry & Advisory Input", "kind": "text"})

    for l in source_links:
        citations.append(Citation(id=f"src-{len(citations)+1}", label=l, kind="link"))
        raw_citations_list.append({"id": f"src-{len(citations)}", "label": l, "kind": "link"})

    initial_metadata_json = {
        "source_links": source_links,
        "files_count": len(uploaded_files),
        "output_categories": selected_keys,
    }

    # -------------------------------------------------------------------------
    # PHASE 2: Enhancer-1 Node (Connects context and groups unrelated content)
    # -------------------------------------------------------------------------
    enhanced_md, enhanced_metadata_json, enhanced_key_points = enhancer_1_node.enhance_context(
        grounding_md=foundational_md,
        citations=raw_citations_list,
        metadata_json=initial_metadata_json,
        source_links=source_links,
    )

    session.grounding_md = enhanced_md
    session.grounding_json = json.dumps(enhanced_metadata_json)
    db.commit()

    # Initial LLM Preview Generation -> generates Preview.md and saves to storage & DB
    preview_data = preview_service.generate_initial_previews(
        db=db,
        session_id=session.id,
        enhanced_md=enhanced_md,
        enhanced_json=enhanced_metadata_json,
        selected_outputs=selected_keys,
        parameters=merged_params,
        is_organisation=is_organisation,
    )

    # Format PlatformPreview objects for frontend
    formatted_previews: Dict[str, PlatformPreview] = {}
    for p_name, p_info in preview_data["previews"].items():
        formatted_previews[p_name] = PlatformPreview(
            platform_key=p_info["platform_key"],
            output_type_id=p_info.get("output_type_id"),
            draft_title=p_info["draft_title"],
            draft_content=p_info["draft_content"],
            citations_used=p_info.get("citations_used", []),
            sensitive_items_flagged=p_info.get("sensitive_items_flagged", 0),
            sensitive_flags=p_info.get("sensitive_flags", []),
        )

    for fact in preview_data.get("extracted_facts", []):
        citations.append(Citation(id=f"fact-{len(citations)+1}", label=fact, kind="text"))

    return {
        "plan": preview_data["plan"],
        "previewsByType": preview_data["previewsByType"],
        "previews": formatted_previews,
        "citations": citations,
        "grounding_md": enhanced_md,
        "grounding_json": enhanced_metadata_json,
        "extracted_facts": preview_data.get("extracted_facts", []),
        "session_id": session.id,
    }


@router.post("/api/generate-deliverable")
@router.post("/api/finalize")
async def generate_deliverable_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Phase 3: Core LLM Branching (Gemini)
    Phase 4: Conditional Logic Routing (Enhance-3 & Enhance-4 if organisation)
    Phase 5: Final Deliverable Generation
    Backend Task 3: Persists chat history to database & returns deliverable.
    """
    payload = await request.json()

    platform_key = payload.get("platform_key") or payload.get("outputType") or "linkedin_post"
    approved_draft = payload.get("approved_draft") or payload.get("previewDraft") or ""
    content_md = payload.get("content_md") or payload.get("groundingMd") or payload.get("sourceText") or ""
    metadata_json = payload.get("metadata_json") or payload.get("groundingJson") or {}
    parameters = payload.get("parameters") or payload.get("params") or {}
    is_organisation = bool(
        payload.get("isOrganisation", False) or payload.get("is_organization", False)
    )
    session_id = payload.get("session_id")

    if not isinstance(metadata_json, dict):
        metadata_json = {}
    if not isinstance(parameters, dict):
        parameters = {}

    # Ensure valid session exists
    session = None
    if session_id:
        session = db.query(SessionRecord).filter(SessionRecord.id == session_id).first()
    if not session:
        session = SessionRecord(
            title=f"Final Deliverable: {platform_key}",
            is_organisation=is_organisation,
            source_text=content_md,
            grounding_md=content_md,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id

    # -------------------------------------------------------------------------
    # PHASE 3: Core LLM Branching (Gemini)
    # Combines edited preview + original md + json + newly generated enhanced key points
    # -------------------------------------------------------------------------
    enhanced_points = []
    if isinstance(metadata_json, dict) and "connected_context" in metadata_json:
        conn = metadata_json["connected_context"]
        if conn.get("threat_actor"):
            enhanced_points.append(f"Attributed Threat Actor: {conn['threat_actor']}")
        if conn.get("cves"):
            enhanced_points.append(f"Primary CVEs: {', '.join(conn['cves'])}")

    branch_payload = branching_service.prepare_branch_payload(
        edited_preview=approved_draft,
        original_md=content_md,
        original_json=metadata_json,
        enhanced_key_points=enhanced_points,
        platform_key=platform_key,
        parameters=parameters,
    )
    branched_draft = branching_service.execute_gemini_branch(branch_payload)

    # -------------------------------------------------------------------------
    # PHASE 4: Conditional Logic Routing
    # Condition A: If organisation -> Route sequentially to Enhance-3 & Enhance-4
    # Condition B: Not organisation -> Bypass Enhancers 3 & 4 entirely
    # -------------------------------------------------------------------------
    expected_citations = re.findall(r"\[\^[^\]]+\]", content_md) or ["[^-src-1]"]
    routed_draft, sensitive_flags, was_routed = conditional_routing_service.route_payload(
        draft_text=branched_draft,
        is_organisation=is_organisation,
        expected_citations=expected_citations,
        source_context=content_md,
    )

    # -------------------------------------------------------------------------
    # PHASE 5: Final Deliverable Generation & Backend Task 3 (Persist & Chat History)
    # -------------------------------------------------------------------------
    result = deliverable_service.generate_and_persist_deliverable(
        db=db,
        session_id=session_id,
        platform_key=platform_key,
        routed_draft=routed_draft,
        content_md=content_md,
        metadata_json=metadata_json,
        parameters=parameters,
    )

    return result
