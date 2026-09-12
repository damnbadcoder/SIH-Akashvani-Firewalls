import os
import json
import re
import tempfile
import traceback
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session

import uuid
from backend.database import get_db
from backend.models.user import User
from backend.models.session import SessionRecord
from backend.models.file_record import FileRecord
from backend.models.chat import ChatMessage
from backend.schemas.pipeline import (
    GeneratePlanResponse,
    DeliverableResponse,
    PlatformPreview,
    Citation,
)
from backend.config import settings
from backend.services.storage_service import storage_service
from backend.services.router_service import router_service, ALL_SUPPORTED_EXTENSIONS
from backend.services.context_service import enhancer_1_node
from backend.services.preview_service import preview_service
from backend.services.branching_service import branching_service
from backend.services.conditional_service import conditional_routing_service
from backend.services.deliverable_service import deliverable_service
from final_post_pipeline import strip_preview_wrappers

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
    file_ids: List[str] = []

    user_email = ""
    user_id = ""
    existing_session_id = ""

    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type or "form" in content_type:
        form = await request.form()
        source_text = str(form.get("sourceText", "") or "")
        links_str = str(form.get("sourceLinks", "[]") or "[]")
        outputs_str = str(form.get("outputs", "[]") or "[]")
        is_org_val = form.get("isOrganisation", "false")
        is_organisation = str(is_org_val).lower() in ("true", "1", "yes")
        user_email = str(form.get("email", "") or form.get("userEmail", "") or "")
        user_id = str(form.get("user_id", "") or form.get("userId", "") or "")
        existing_session_id = str(form.get("session_id", "") or form.get("sessionId", "") or "")

        try:
            source_links = json.loads(links_str) if isinstance(links_str, str) else []
        except Exception:
            source_links = [links_str] if links_str and links_str != "[]" else []

        try:
            outputs_raw = json.loads(outputs_str) if isinstance(outputs_str, str) else []
        except Exception:
            outputs_raw = []

        file_ids_str = str(form.get("file_ids", "[]") or form.get("fileIds", "[]") or "[]")
        try:
            file_ids = json.loads(file_ids_str) if isinstance(file_ids_str, str) else []
        except Exception:
            file_ids = []

        for field_name, value in form.multi_items():
            if field_name == "files" and hasattr(value, "filename") and value.filename:
                file_bytes = await value.read()
                uploaded_files.append((value.filename, file_bytes))

    else:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        source_text = payload.get("sourceText") or payload.get("content_md") or payload.get("source_text") or ""
        source_links = payload.get("sourceLinks") or payload.get("source_links") or []
        outputs_raw = payload.get("outputs") or []
        selected_outputs_list = payload.get("selected_outputs") or []
        parameters = payload.get("parameters") or {}
        file_ids = payload.get("file_ids") or payload.get("fileIds") or []
        is_organisation = bool(
            payload.get("isOrganisation", False) or payload.get("is_organization", False)
        )
        user_email = str(payload.get("email") or payload.get("userEmail") or "")
        user_id = str(payload.get("user_id") or payload.get("userId") or "")
        existing_session_id = str(payload.get("session_id") or payload.get("sessionId") or "")

        if not outputs_raw and selected_outputs_list:
            outputs_raw = selected_outputs_list

    # Map output categories and collect parameters
    selected_keys = []
    merged_params = dict(parameters)

    for out in outputs_raw:
        if isinstance(out, dict):
            oid = out.get("id", "")
            if "params" in out and isinstance(out["params"], dict):
                merged_params.update(out["params"])
        elif isinstance(out, str):
            oid = out
            if isinstance(parameters.get(oid), dict):
                merged_params.update(parameters[oid])
        else:
            continue

        pkey = KEY_MAPPING.get(oid, oid)
        if pkey and pkey not in selected_keys:
            selected_keys.append(pkey)

    if not selected_keys:
        selected_keys = ["linkedin_post", "advisory"]

    # 1. Resolve User and Session
    user = None
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
    if not user and user_email:
        user = db.query(User).filter(User.email == user_email).first()
        if not user:
            user = User(
                id=str(uuid.uuid4()),
                name=user_email.split("@")[0].capitalize(),
                email=user_email,
                user_type="Organisation" if is_organisation else "Researcher",
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    session = None
    if existing_session_id:
        session = db.query(SessionRecord).filter(SessionRecord.id == existing_session_id).first()

    if session:
        session.title = f"Transformation: {selected_keys[0]} ({len(selected_keys)} outputs)"
        session.is_organisation = is_organisation
        session.source_text = source_text
        session.source_links_json = json.dumps(source_links)
        session.status = "blueprint_ready"
        session.selected_outputs_json = json.dumps(selected_keys)
        session.parameters_json = json.dumps(merged_params)
        if user and not session.user_id:
            session.user_id = user.id
    else:
        session = SessionRecord(
            user_id=user.id if user else None,
            title=f"Transformation: {selected_keys[0]} ({len(selected_keys)} outputs)",
            is_organisation=is_organisation,
            source_text=source_text,
            source_links_json=json.dumps(source_links),
            status="blueprint_ready",
            selected_outputs_json=json.dumps(selected_keys),
            parameters_json=json.dumps(merged_params),
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

    # If file IDs were provided and no new files uploaded, fetch existing file context
    if not uploaded_files and file_ids:
        existing_files = db.query(FileRecord).filter(FileRecord.id.in_(file_ids)).all()
        for ef in existing_files:
            if ef.extracted_markdown:
                extracted_md_sections.append(ef.extracted_markdown)
            citations.append(Citation(id=f"src-{ef.id[:6]}", label=ef.filename, kind="file"))
            raw_citations_list.append({"id": f"src-{ef.id[:6]}", "label": ef.filename, "kind": "file"})

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

    # Process incoming web links through link_pipeline
    scraped_links_records: List[Dict[str, Any]] = []
    for l_idx, link_url in enumerate(source_links, 1):
        if not link_url or not str(link_url).strip():
            continue
        clean_url = str(link_url).strip()
        link_out_dir = str(settings.STORAGE_DIR / "links" / session.id)
        scraped_link = router_service.process_link_into_context(clean_url, output_dir=link_out_dir)
        scraped_links_records.append(scraped_link)

        link_md = scraped_link.get("markdown", "")
        if link_md:
            extracted_md_sections.append(link_md)

        link_meta = scraped_link.get("metadata", {})
        domain = link_meta.get("domain", "web")
        title = link_meta.get("title", clean_url)
        char_count = link_meta.get("character_count", len(link_md))

        # Save FileRecord for scraped link
        file_rec = FileRecord(
            session_id=session.id,
            filename=f"{domain} - {title[:80]}",
            file_type="link",
            file_format=".url",
            file_size=char_count,
            file_path=scraped_link.get("md_file_path"),
            sha256=link_meta.get("sha256_checksum"),
            extracted_markdown=link_md,
            extracted_json=json.dumps(link_meta),
        )
        db.add(file_rec)

        link_cit_id = f"link-{l_idx}"
        citations.append(Citation(id=link_cit_id, label=f"[{domain}] {title[:70]}", kind="link"))
        raw_citations_list.append({"id": link_cit_id, "label": f"[{domain}] {title[:70]}", "kind": "link"})

        for c in scraped_link.get("citations", []):
            if c.get("id") != link_cit_id:
                citations.append(Citation(id=c["id"], label=c["label"], kind=c.get("kind", "link")))
                raw_citations_list.append(c)

    # Convergence: Merge all pipeline outputs into foundational Context (md + json)
    if extracted_md_sections:
        if source_text and source_text.strip():
            foundational_md = f"{source_text.strip()}\n\n---\n\n" + "\n\n".join(extracted_md_sections)
        else:
            foundational_md = "\n\n".join(extracted_md_sections)
    else:
        foundational_md = source_text

    if not foundational_md or not foundational_md.strip():
        foundational_md = "Comprehensive cyber threat intelligence and advisory overview."

    if not citations and source_text and source_text.strip():
        citations.append(Citation(id="src-1", label="Raw Telemetry & Advisory Input", kind="text"))
        raw_citations_list.append({"id": "src-1", "label": "Raw Telemetry & Advisory Input", "kind": "text"})

    initial_metadata_json = {
        "source_links": source_links,
        "scraped_links_count": len(scraped_links_records),
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
            readability=p_info.get("readability"),
        )

    for fact in preview_data.get("extracted_facts", []):
        citations.append(Citation(id=f"fact-{len(citations)+1}", label=fact, kind="text"))

    # Update session with enhanced grounding and blueprint status
    session.grounding_md = enhanced_md
    session.grounding_json = json.dumps(enhanced_metadata_json) if isinstance(enhanced_metadata_json, dict) else str(enhanced_metadata_json)
    session.status = "blueprint_ready"
    session.selected_outputs_json = json.dumps(selected_keys)
    session.parameters_json = json.dumps(merged_params)
    db.commit()

    return {
        "plan": preview_data["plan"],
        "previewsByType": preview_data["previewsByType"],
        "previews": formatted_previews,
        "citations": citations,
        "grounding_md": enhanced_md,
        "grounding_json": enhanced_metadata_json,
        "extracted_facts": preview_data.get("extracted_facts", []),
        "session_id": session.id,
        "sessionId": session.id,
        "status": "blueprint_ready",
        "selectedOutputs": selected_keys,
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
    if approved_draft:
        approved_draft = strip_preview_wrappers(approved_draft)
    content_md = payload.get("content_md") or payload.get("groundingMd") or payload.get("sourceText") or ""
    metadata_json = payload.get("metadata_json") or payload.get("groundingJson") or {}
    parameters = payload.get("parameters") or payload.get("params") or {}
    is_organisation = bool(
        payload.get("isOrganisation", False) or payload.get("is_organization", False)
    )
    session_id = payload.get("session_id") or payload.get("sessionId")
    user_email = payload.get("email") or payload.get("userEmail")
    user_id = payload.get("user_id") or payload.get("userId")

    if not isinstance(metadata_json, dict):
        metadata_json = {}
    if not isinstance(parameters, dict):
        parameters = {}

    # Ensure valid session exists
    session = None
    if session_id:
        session = db.query(SessionRecord).filter(SessionRecord.id == session_id).first()

    if not session and (user_id or user_email):
        user = None
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
        if not user and user_email:
            user = db.query(User).filter(User.email == user_email).first()
        if user:
            # Check for latest blueprint_ready session for this user
            session = (
                db.query(SessionRecord)
                .filter(SessionRecord.user_id == user.id, SessionRecord.status == "blueprint_ready")
                .order_by(SessionRecord.created_at.desc())
                .first()
            )

    if not session:
        user = None
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
        if not user and user_email:
            user = db.query(User).filter(User.email == user_email).first()
        session = SessionRecord(
            user_id=user.id if user else None,
            title=f"Final Deliverable: {platform_key}",
            is_organisation=is_organisation,
            source_text=content_md,
            grounding_md=content_md,
            status="completed",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id
    else:
        session_id = session.id
        if not session.grounding_md and content_md:
            session.grounding_md = content_md

    if isinstance(metadata_json, dict) and "original_preview_draft" not in metadata_json:
        orig_d = (
            payload.get("original_preview_draft")
            or payload.get("originalDraft")
            or payload.get("preview_draft")
            or payload.get("original_draft")
        )
        if not orig_d and session_id:
            from backend.models.preview import PreviewRecord
            prev_rec = (
                db.query(PreviewRecord)
                .filter(
                    PreviewRecord.session_id == session_id,
                    PreviewRecord.output_type == platform_key,
                )
                .first()
            )
            if prev_rec and prev_rec.original_preview_content:
                orig_d = prev_rec.original_preview_content
        if orig_d:
            metadata_json["original_preview_draft"] = orig_d

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

    if session:
        session.status = "completed"
        db.commit()

    result["sessionId"] = session_id
    result["session_id"] = session_id
    result["status"] = "completed"

    return result


@router.post("/api/pipeline/scrape-link")
@router.post("/api/link-pipeline/scrape")
async def scrape_link_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Independent Web Link Scraping Pipeline Endpoint.
    Ingests target URL, scrapes webpage content, extracts IOCs & metadata,
    and returns both the normalized Markdown (.md) and structured metadata (.json) paths/contents.
    """
    content_type = request.headers.get("Content-Type", "")
    url = ""
    session_id = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        url = str(form.get("url", "") or "")
        session_id = form.get("sessionId") or form.get("session_id")
    else:
        try:
            body = await request.json()
            url = str(body.get("url", "") or "")
            session_id = body.get("sessionId") or body.get("session_id")
        except Exception:
            url = ""

    url = url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="A valid 'url' parameter is required.")

    # Route through link_pipeline
    output_dir = str(settings.STORAGE_DIR / "links" / session_id) if session_id else str(settings.STORAGE_DIR / "links" / "standalone")
    res = router_service.process_link_into_context(url, output_dir=output_dir)

    md_path = res.get("md_file_path")
    json_path = res.get("json_file_path")
    md_name = Path(md_path).name if md_path else None
    json_name = Path(json_path).name if json_path else None

    # Persist in DB FileRecord if session exists
    if session_id and res.get("success"):
        domain = res.get("metadata", {}).get("domain", "web")
        title = res.get("metadata", {}).get("title", url)[:80]
        char_count = res.get("metadata", {}).get("character_count", len(res.get("markdown", "")))
        file_rec = FileRecord(
            session_id=str(session_id),
            filename=f"{domain} - {title}",
            file_type="link",
            file_format=".url",
            file_size=char_count,
            file_path=md_path,
            sha256=res.get("metadata", {}).get("sha256_checksum"),
            extracted_markdown=res.get("markdown"),
            extracted_json=json.dumps(res.get("metadata", {})),
        )
        db.add(file_rec)
        db.commit()

    return JSONResponse({
        "success": res.get("success", False),
        "url": url,
        "domain": res.get("metadata", {}).get("domain", ""),
        "title": res.get("metadata", {}).get("title", "Web Document"),
        "author": res.get("metadata", {}).get("author"),
        "published_time": res.get("metadata", {}).get("published_time"),
        "description": res.get("metadata", {}).get("description"),
        "markdown": res.get("markdown", ""),
        "metadata": res.get("metadata", {}),
        "iocs": res.get("iocs", {}),
        "citations": res.get("citations", []),
        "md_file_path": md_path,
        "json_file_path": json_path,
        "md_filename": md_name,
        "json_filename": json_name,
        "word_count": res.get("metadata", {}).get("word_count", 0),
        "character_count": res.get("metadata", {}).get("character_count", 0),
        "error_message": res.get("error_message"),
    })


@router.get("/api/pipeline/download-link-artifact")
async def download_link_artifact(path: str):
    """
    Allows downloading or viewing the generated .md and .json files safely.
    """
    target = Path(path).resolve()
    storage_root = settings.STORAGE_DIR.resolve()
    ingest_root = (settings.BASE_DIR / "ingestion_outputs").resolve()

    if not (target.is_relative_to(storage_root) or target.is_relative_to(ingest_root)):
        raise HTTPException(status_code=403, detail="Forbidden file access path.")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Requested link context artifact not found.")

    media_type = "application/json" if target.suffix == ".json" else "text/markdown; charset=utf-8"
    return FileResponse(
        path=str(target),
        media_type=media_type,
        filename=target.name,
    )

