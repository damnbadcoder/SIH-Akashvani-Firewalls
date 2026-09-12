import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.signing import signing_service
from backend.services.deliverable_service import deliverable_service
from backend.models.deliverable import DeliverableRecord
from backend.models.provenance_registry import ProvenanceRegistryRecord

router = APIRouter(prefix="/api/v1/deliverables", tags=["Deliverable Signing & Tamper Detection"])

class VerifyRequest(BaseModel):
    content: Optional[str] = None
    signature: Optional[str] = None
    signing_key_id: Optional[str] = None
    content_hash: Optional[str] = None
    expected_hash: Optional[str] = None
    deliverable_id: Optional[str] = None

class ReSignRequest(BaseModel):
    content: str
    organization: Optional[str] = None
    tlp_level: Optional[str] = None

@router.post("/verify")
async def verify_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Public Verification Endpoint:
    Validates deliverable authenticity and integrity via Ed25519 signature + SHA-256 digest,
    and cross-checks the Public Provenance Registry.
    Supports JSON body or multipart form (file upload + .sig sidecar).
    """
    content_type = request.headers.get("Content-Type", "")
    content_bytes: Optional[bytes] = None
    signature: Optional[str] = None
    signing_key_id: Optional[str] = None
    expected_hash: Optional[str] = None
    deliverable_id: Optional[str] = None
    meta_from_sidecar: Dict[str, Any] = {}

    if "multipart/form-data" in content_type:
        form = await request.form()
        # 1. Main deliverable document
        file_obj = form.get("file")
        if file_obj and hasattr(file_obj, "read"):
            content_bytes = await file_obj.read()

        # 2. Detached .sig sidecar file
        sig_file_obj = form.get("sig_file") or form.get("sidecar")
        if sig_file_obj and hasattr(sig_file_obj, "read"):
            try:
                sig_bytes = await sig_file_obj.read()
                sidecar_data = json.loads(sig_bytes.decode("utf-8"))
                meta_from_sidecar = sidecar_data
                signature = sidecar_data.get("signature")
                signing_key_id = sidecar_data.get("signing_key_id")
                expected_hash = sidecar_data.get("content_sha256")
                deliverable_id = sidecar_data.get("deliverable_id")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid .sig sidecar file: {e}")

        # Form fallbacks
        if not signature and form.get("signature"):
            signature = str(form.get("signature"))
        if not signing_key_id and form.get("signing_key_id"):
            signing_key_id = str(form.get("signing_key_id"))
        if not expected_hash and form.get("content_hash"):
            expected_hash = str(form.get("content_hash"))
        if not deliverable_id and form.get("deliverable_id"):
            deliverable_id = str(form.get("deliverable_id"))
        if not content_bytes and form.get("content"):
            content_bytes = str(form.get("content")).encode("utf-8")

    else:
        payload = await request.json()
        raw_content = payload.get("content")
        if raw_content is not None:
            content_bytes = str(raw_content).encode("utf-8")
        signature = payload.get("signature")
        signing_key_id = payload.get("signing_key_id")
        expected_hash = payload.get("content_hash") or payload.get("expected_hash")
        deliverable_id = payload.get("deliverable_id")

    # If only deliverable_id was passed and no signature/content, look up directly in registry/db
    if not content_bytes and not signature and deliverable_id:
        reg_entry = (
            db.query(ProvenanceRegistryRecord)
            .filter(ProvenanceRegistryRecord.deliverable_id == deliverable_id)
            .order_by(ProvenanceRegistryRecord.revision.desc())
            .first()
        )
        if reg_entry:
            return {
                "valid": True,
                "status": "AUTHENTIC",
                "in_registry": True,
                "deliverable_id": reg_entry.deliverable_id,
                "revision": reg_entry.revision,
                "computed_hash": reg_entry.content_hash,
                "signing_key_id": reg_entry.signing_key_id,
                "organization": reg_entry.organization,
                "tlp_level": reg_entry.tlp_level,
                "output_type": reg_entry.output_type,
                "timestamp": reg_entry.created_at.isoformat() if reg_entry.created_at else None,
                "details": f"Registered deliverable found in public ledger (Revision {reg_entry.revision}).",
            }
        return {
            "valid": False,
            "status": "NOT_FOUND",
            "in_registry": False,
            "deliverable_id": deliverable_id,
            "details": f"Deliverable ID '{deliverable_id}' not found in public provenance registry.",
        }

    # If only expected_hash or hash lookup is requested without signature
    if (not content_bytes or not signature) and expected_hash:
        reg_entry = (
            db.query(ProvenanceRegistryRecord)
            .filter(ProvenanceRegistryRecord.content_hash == expected_hash)
            .order_by(ProvenanceRegistryRecord.revision.desc())
            .first()
        )
        if reg_entry:
            return {
                "valid": True,
                "status": "AUTHENTIC",
                "in_registry": True,
                "deliverable_id": reg_entry.deliverable_id,
                "revision": reg_entry.revision,
                "computed_hash": reg_entry.content_hash,
                "signing_key_id": reg_entry.signing_key_id,
                "organization": reg_entry.organization,
                "tlp_level": reg_entry.tlp_level,
                "output_type": reg_entry.output_type,
                "timestamp": reg_entry.created_at.isoformat() if reg_entry.created_at else None,
                "details": f"Content hash verified in public provenance registry (Revision {reg_entry.revision}).",
            }
        elif not content_bytes:
            return {
                "valid": False,
                "status": "NOT_FOUND",
                "in_registry": False,
                "computed_hash": expected_hash,
                "details": "Hash was not found in the platform's public provenance registry.",
            }

    if content_bytes is None:
        raise HTTPException(status_code=400, detail="Document content or file is required for verification.")

    # Execute Ed25519 Cryptographic Verification
    verification_res = signing_service.verify_deliverable(
        content=content_bytes,
        signature=signature,
        signing_key_id=signing_key_id,
        expected_hash=expected_hash,
    )

    target_hash = verification_res.get("computed_hash") or signing_service.compute_sha256(content_bytes)
    
    # Query Provenance Registry for platform metadata
    reg_entry = (
        db.query(ProvenanceRegistryRecord)
        .filter(ProvenanceRegistryRecord.content_hash == target_hash)
        .order_by(ProvenanceRegistryRecord.revision.desc())
        .first()
    )

    in_registry = (reg_entry is not None)
    organization = (
        (reg_entry.organization if reg_entry else None)
        or meta_from_sidecar.get("organization")
        or "Transmute Threat Intel CERT"
    )
    tlp_level = (
        (reg_entry.tlp_level if reg_entry else None)
        or meta_from_sidecar.get("tlp_level")
        or "TLP:AMBER+STRICT"
    )
    revision = (reg_entry.revision if reg_entry else None) or meta_from_sidecar.get("revision") or 1
    output_type = (reg_entry.output_type if reg_entry else None) or meta_from_sidecar.get("output_type") or "deliverable"
    timestamp = (
        (reg_entry.created_at.isoformat() if (reg_entry and reg_entry.created_at) else None)
        or meta_from_sidecar.get("timestamp")
    )
    matched_id = (reg_entry.deliverable_id if reg_entry else None) or deliverable_id

    response_payload = {
        "valid": verification_res.get("valid", False),
        "status": verification_res.get("status"),
        "in_registry": in_registry,
        "computed_hash": target_hash,
        "signing_key_id": signing_key_id or verification_res.get("signing_key_id"),
        "deliverable_id": matched_id,
        "revision": revision,
        "organization": organization,
        "tlp_level": tlp_level,
        "output_type": output_type,
        "timestamp": timestamp,
        "details": verification_res.get("details"),
    }
    return response_payload

@router.get("/registry/{hash_or_id}")
def get_registry_entry(hash_or_id: str, db: Session = Depends(get_db)):
    """
    Public Provenance Registry query:
    Allows anyone to check whether a deliverable's hash exists in the public registry,
    proving platform provenance without disclosing document contents.
    """
    query = db.query(ProvenanceRegistryRecord)
    if len(hash_or_id) == 64:  # SHA-256 hash
        query = query.filter(ProvenanceRegistryRecord.content_hash == hash_or_id.lower())
    else:  # Deliverable UUID
        query = query.filter(ProvenanceRegistryRecord.deliverable_id == hash_or_id)

    entry = query.order_by(ProvenanceRegistryRecord.revision.desc()).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found in public provenance registry.")

    return {
        "exists": True,
        "content_hash": entry.content_hash,
        "deliverable_id": entry.deliverable_id,
        "revision": entry.revision,
        "organization": entry.organization,
        "tlp_level": entry.tlp_level,
        "output_type": entry.output_type,
        "signing_key_id": entry.signing_key_id,
        "signature": entry.signature,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }

@router.get("/public-keys")
def list_public_keys():
    """
    Returns list of all active and historical Ed25519 public keys for independent verification.
    """
    return {"keys": signing_service.list_public_keys()}

@router.get("/public-keys/{key_id}")
def get_public_key_pem(key_id: str):
    """
    Returns raw SubjectPublicKeyInfo PEM string for specified key ID.
    """
    pem = signing_service.get_public_key_pem(key_id)
    if not pem:
        raise HTTPException(status_code=404, detail=f"Public key '{key_id}' not found.")
    return PlainTextResponse(content=pem, media_type="text/plain")

@router.get("/{id}/signature")
def get_deliverable_signature(id: str, db: Session = Depends(get_db)):
    """
    Retrieves the signature envelope, QR code data URL, and sidecar metadata for a deliverable.
    """
    deliverable = db.query(DeliverableRecord).filter(DeliverableRecord.id == id).first()
    if not deliverable:
        raise HTTPException(status_code=404, detail="Deliverable not found.")

    if not deliverable.signature:
        # Sign automatically if not yet signed
        envelope = signing_service.sign_deliverable(
            content=deliverable.content,
            deliverable_id=deliverable.id,
            output_type=deliverable.output_type,
            revision=deliverable.revision or 1,
        )
        deliverable.signature = envelope["signature"]
        deliverable.signing_key_id = envelope["signing_key_id"]
        deliverable.content_hash = envelope["content_sha256"]
        deliverable.signature_metadata_json = json.dumps(envelope)
        db.commit()
    else:
        envelope = json.loads(deliverable.signature_metadata_json) if deliverable.signature_metadata_json else {}
        if not envelope.get("qr_data_url"):
            verify_url = envelope.get("verification_url") or f"{settings.VERIFY_BASE_URL}?id={deliverable.id}&hash={deliverable.content_hash}"
            envelope["qr_data_url"] = signing_service.generate_qr_data_url(verify_url)
            envelope["verification_url"] = verify_url

    return envelope

@router.get("/{id}/sidecar")
def download_sidecar(id: str, db: Session = Depends(get_db)):
    """
    Directly downloads the detached .sig sidecar JSON file for a deliverable.
    """
    deliverable = db.query(DeliverableRecord).filter(DeliverableRecord.id == id).first()
    if not deliverable:
        raise HTTPException(status_code=404, detail="Deliverable not found.")

    if deliverable.signature_metadata_json:
        envelope = json.loads(deliverable.signature_metadata_json)
    else:
        envelope = signing_service.sign_deliverable(
            content=deliverable.content,
            deliverable_id=deliverable.id,
            output_type=deliverable.output_type,
            revision=deliverable.revision or 1,
        )

    sidecar_json = signing_service.generate_sidecar_json(envelope)
    filename = f"{deliverable.output_type}_{id[:8]}.sig"
    return Response(
        content=sidecar_json,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.post("/{id}/re-sign")
def re_sign_deliverable_endpoint(id: str, req: ReSignRequest, db: Session = Depends(get_db)):
    """
    Creates a new revision of a deliverable with updated content, recalculates hash,
    and issues an Ed25519 signature registered in the public provenance ledger.
    """
    try:
        result = deliverable_service.create_revision(
            db=db,
            deliverable_id=id,
            updated_content=req.content,
            parameters={"organization": req.organization, "tlp_level": req.tlp_level},
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
