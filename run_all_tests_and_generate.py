#!/usr/bin/env python3
"""
End-to-end Test Orchestration Script:
1. Ingests all test files from tests/ (PDF, MP3, MP4, PNGs 1-9) through multimodal pipelines.
2. Combines multimodal extractions and grounding citations.
3. Runs the Preview Pipeline to generate separated previews for:
   - LinkedIn Post (linkedin_post)
   - Technical Advisory (advisory)
   - Twitter/X Thread (social_thread)
   - Video Script (video_script)
4. Audits operational sensitivity with the Organisation toggle.
5. Synthesizes final, copy-paste ready posts via the Final Post Pipeline with platform-specific prompts.
6. Saves comprehensive outputs to test_pipeline_outputs.md and test_pipeline_outputs.json.
"""

import os
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from pipelines import ingest_text, ingest_image, ingest_audio, ingest_video
from preview_pipeline import generate_previews, scan_and_redact
from final_post_pipeline import generate_final_deliverable

TESTS_DIR = REPO_ROOT / "tests"
OUTPUT_MD = REPO_ROOT / "test_pipeline_outputs.md"
OUTPUT_JSON = REPO_ROOT / "test_pipeline_outputs.json"


def run_pipeline_suite():
    print("=" * 80)
    print("🚀 STARTING MULTIMODAL PIPELINE & SYNTHESIS EXECUTION")
    print(f"Directory: {TESTS_DIR}")
    print("=" * 80)

    start_total_time = time.time()
    extracted_results = {}
    all_citations = []
    combined_grounding_sections = []

    # -------------------------------------------------------------------------
    # 1. Ingest PDF Document
    # -------------------------------------------------------------------------
    pdf_path = TESTS_DIR / "MediaPublish_AutomotiveCyberSecurity.pdf"
    if pdf_path.exists():
        print(f"\n[1/4] 📄 Ingesting Document: {pdf_path.name}...")
        t0 = time.time()
        try:
            res_text = ingest_text(str(pdf_path), save_outputs=False, enrich=False)
            dt = time.time() - t0
            extracted_results["document"] = {
                "filename": pdf_path.name,
                "type": "text/pdf",
                "length_chars": len(res_text.clean_markdown),
                "execution_seconds": round(dt, 2),
                "markdown": res_text.clean_markdown,
            }
            combined_grounding_sections.append(
                f"# SOURCE DOCUMENT: {pdf_path.name}\n\n{res_text.clean_markdown}"
            )
            print(f"   ✅ Done in {dt:.2f}s ({len(res_text.clean_markdown)} chars extracted)")
            
            # Extract IOC citations
            if hasattr(res_text, "iocs") and res_text.iocs:
                for cve in getattr(res_text.iocs, "cves", []):
                    all_citations.append({"id": f"cve-{cve}", "claim": f"Vulnerability: {cve}", "source": pdf_path.name})
                for ip in getattr(res_text.iocs, "ipv4_addresses", []):
                    all_citations.append({"id": f"ip-{ip}", "claim": f"Suspicious IP: {ip}", "source": pdf_path.name})
        except Exception as e:
            print(f"   ❌ Failed: {e}")

    # -------------------------------------------------------------------------
    # 2. Ingest Audio Recording
    # -------------------------------------------------------------------------
    audio_path = TESTS_DIR / "10090.mp3"
    if audio_path.exists():
        print(f"\n[2/4] 🎙️ Ingesting Audio: {audio_path.name}...")
        t0 = time.time()
        try:
            res_audio = ingest_audio(str(audio_path))
            dt = time.time() - t0
            extracted_results["audio"] = {
                "filename": audio_path.name,
                "type": "audio/mp3",
                "length_chars": len(res_audio.markdown_output),
                "execution_seconds": round(dt, 2),
                "anchors_count": len(res_audio.grounding_sources),
                "markdown": res_audio.markdown_output,
            }
            combined_grounding_sections.append(
                f"# SOURCE AUDIO TRANSCRIPTION: {audio_path.name}\n\n{res_audio.markdown_output}"
            )
            for anchor in res_audio.grounding_sources:
                all_citations.append({
                    "id": anchor.id,
                    "claim": f"[{anchor.temporal_anchor}] {anchor.extracted_verbatim[:120]}",
                    "source": audio_path.name
                })
            print(f"   ✅ Done in {dt:.2f}s ({len(res_audio.markdown_output)} chars, {len(res_audio.grounding_sources)} temporal anchors)")
        except Exception as e:
            print(f"   ❌ Failed: {e}")

    # -------------------------------------------------------------------------
    # 3. Ingest Images (1.png to 9.png)
    # -------------------------------------------------------------------------
    print(f"\n[3/4] 🖼️ Ingesting Threat Diagrams & Forensics (1.png - 9.png)...")
    images_results = []
    image_files = sorted(list(TESTS_DIR.glob("*.png")))
    for img_p in image_files:
        print(f"   -> Processing {img_p.name}...")
        t0 = time.time()
        try:
            res_img = ingest_image(str(img_p))
            dt = time.time() - t0
            images_results.append({
                "filename": img_p.name,
                "length_chars": len(res_img.markdown_output),
                "execution_seconds": round(dt, 2),
                "anchors_count": len(res_img.grounding_sources),
            })
            combined_grounding_sections.append(
                f"# DIAGRAM/IMAGE FORENSICS: {img_p.name}\n\n{res_img.markdown_output}"
            )
            for anchor in res_img.grounding_sources:
                all_citations.append({
                    "id": anchor.id,
                    "claim": f"[{anchor.visual_anchor}] {anchor.extracted_verbatim[:120]}",
                    "source": img_p.name
                })
            print(f"      ✅ {img_p.name}: {len(res_img.markdown_output)} chars in {dt:.2f}s")
        except Exception as e:
            print(f"      ❌ {img_p.name} Failed: {e}")
    extracted_results["images"] = images_results

    # -------------------------------------------------------------------------
    # 4. Ingest Incident Briefing Video
    # -------------------------------------------------------------------------
    video_path = TESTS_DIR / "FBI CYD STRATEGY 2026 VIDEO 1080P HD.mp4"
    if video_path.exists():
        print(f"\n[4/4] 🎬 Ingesting Video: {video_path.name}...")
        t0 = time.time()
        try:
            res_vid = ingest_video(str(video_path), save_outputs=False, enrich=False)
            dt = time.time() - t0
            extracted_results["video"] = {
                "filename": video_path.name,
                "type": "video/mp4",
                "length_chars": len(res_vid.clean_markdown),
                "execution_seconds": round(dt, 2),
                "scenes_count": len(res_vid.scenes),
                "markdown": res_vid.clean_markdown,
            }
            combined_grounding_sections.append(
                f"# SOURCE VIDEO TRANSCRIPT & SCENE ANALYSIS: {video_path.name}\n\n{res_vid.clean_markdown}"
            )
            for sc in res_vid.scenes[:6]:
                all_citations.append({
                    "id": f"vid-scene-{sc.scene_id}",
                    "claim": f"[{sc.timestamp_display}] {sc.spoken_transcript[:120]}",
                    "source": video_path.name
                })
            print(f"   ✅ Done in {dt:.2f}s ({len(res_vid.clean_markdown)} chars, {len(res_vid.scenes)} aligned scenes)")
        except Exception as e:
            print(f"   ❌ Failed: {e}")

    # Build Consolidated Grounding Context
    consolidated_grounding_md = "\n\n" + ("=" * 50) + "\n\n".join(combined_grounding_sections)
    print(f"\n📊 TOTAL MULTIMODAL CORPUS EXTRACTED: {len(consolidated_grounding_md)} characters across {len(all_citations)} grounding citations.")

    # -------------------------------------------------------------------------
    # 5. Run Preview Pipeline (4 Target Platforms)
    # -------------------------------------------------------------------------
    selected_platforms = ["linkedin_post", "advisory", "social_thread", "video_script"]
    platform_labels = {
        "linkedin_post": "LinkedIn Strategic Post",
        "advisory": "Technical Security Advisory",
        "social_thread": "X / Twitter Threat Thread",
        "video_script": "Video Briefing Script",
    }
    parameters = {
        "audienceCategory": "Technical Leadership & Security Operations",
        "targetAudience": "CISOs, CERT analysts, SOC leads, automotive security architects",
        "tone": "Authoritative, urgent, and technically precise",
        "detail": "High",
        "objective": "Warn against active threat vectors and deliver immediate remediation actions",
        "language": "English",
    }

    print("\n" + "=" * 80)
    print("🔍 RUNNING PREVIEW PIPELINE (Separated Platform Previews + Sensitive Proofcheck)")
    print(f"Selected Platforms: {selected_platforms}")
    print("Organisation Mode: ACTIVE (Flags sensitive internal data in red)")
    print("=" * 80)

    t0 = time.time()
    preview_bundle = generate_previews(
        content_md=consolidated_grounding_md,
        metadata_json={
            "citations_extracted": len(all_citations),
            "files_processed": [f.name for f in TESTS_DIR.glob("*") if not f.name.startswith(".")],
        },
        selected_outputs=selected_platforms,
        parameters=parameters,
        is_organization=True,
    )
    dt_prev = time.time() - t0
    print(f"✅ Previews Generated in {dt_prev:.2f}s!")

    # -------------------------------------------------------------------------
    # 6. Run Final Post Pipeline (Copy-Paste Ready Deliverables)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("✍️ RUNNING FINAL POST GENERATION (Hyper-Realistic Copy-Paste Material)")
    print("=" * 80)

    final_deliverables = {}
    for pkey in selected_platforms:
        p_obj = preview_bundle.previews.get(pkey)
        draft = p_obj.draft_content if p_obj else "Initial threat overview and technical indicators."
        print(f"\n-> Generating final deliverable for: [{platform_labels.get(pkey, pkey)}]...")
        t0 = time.time()
        final_res = generate_final_deliverable(
            platform_key=pkey,
            approved_draft=draft,
            content_md=consolidated_grounding_md,
            metadata_json={"platform": pkey, "title": p_obj.draft_title if p_obj else ""},
            parameters=parameters,
        )
        dt_fin = time.time() - t0
        final_deliverables[pkey] = {
            "platform_key": pkey,
            "display_name": platform_labels.get(pkey, pkey),
            "final_content": final_res.final_content,
            "provenance": [p.model_dump() for p in final_res.provenance],
            "execution_seconds": round(dt_fin, 2),
        }
        print(f"   ✅ Done in {dt_fin:.2f}s ({len(final_res.final_content)} characters)")

    # -------------------------------------------------------------------------
    # 7. Format Output Files (Markdown & JSON)
    # -------------------------------------------------------------------------
    total_execution_time = round(time.time() - start_total_time, 2)
    print(f"\nWriting comprehensive outputs to:")
    print(f"  - Markdown: {OUTPUT_MD}")
    print(f"  - JSON:     {OUTPUT_JSON}")

    # Build Markdown Document
    md_lines = []
    md_lines.append("# Multimodal Pipeline & Intelligence Deliverables Report")
    md_lines.append(f"**Execution Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
    md_lines.append(f"**Total Run Time:** {total_execution_time} seconds\n")
    md_lines.append("## 1. Test Ingestion Summary\n")
    md_lines.append("| Test File | Modality | Status | Length (Chars) | Exec Time |")
    md_lines.append("|---|---|---|---|---|")
    
    if "document" in extracted_results:
        d = extracted_results["document"]
        md_lines.append(f"| `{d['filename']}` | PDF Document | ✅ Ingested | {d['length_chars']} | {d['execution_seconds']}s |")
    if "audio" in extracted_results:
        a = extracted_results["audio"]
        md_lines.append(f"| `{a['filename']}` | Audio Broadcast | ✅ Ingested | {a['length_chars']} | {a['execution_seconds']}s |")
    for img in extracted_results.get("images", []):
        md_lines.append(f"| `{img['filename']}` | Visual Diagram | ✅ Ingested | {img['length_chars']} | {img['execution_seconds']}s |")
    if "video" in extracted_results:
        v = extracted_results["video"]
        md_lines.append(f"| `{v['filename']}` | Briefing Video | ✅ Ingested | {v['length_chars']} | {v['execution_seconds']}s |")

    md_lines.append("\n---\n")
    md_lines.append("## 2. Separated Platform Previews (with Organisation Sensitivity Audit)\n")

    for pkey in selected_platforms:
        p_obj = preview_bundle.previews.get(pkey)
        label = platform_labels.get(pkey, pkey)
        md_lines.append(f"### Platform Preview: {label} (`{pkey}`)\n")
        if p_obj:
            flag_count = len(p_obj.sensitive_flags)
            md_lines.append(f"**Draft Title:** {p_obj.draft_title}  ")
            md_lines.append(f"**Sensitive Items Flagged:** {flag_count}  ")
            md_lines.append(f"**Citations Anchored:** {', '.join(p_obj.citations_used) if p_obj.citations_used else 'None'}\n")
            md_lines.append("```markdown")
            md_lines.append(p_obj.draft_content)
            md_lines.append("```\n")

    md_lines.append("\n---\n")
    md_lines.append("## 3. Final Generated Posts (Ready to Copy-Paste)\n")

    for pkey in selected_platforms:
        f_data = final_deliverables[pkey]
        label = f_data["display_name"]
        md_lines.append(f"### 🚀 Final Deliverable: {label} (`{pkey}`)\n")
        md_lines.append(f"**Generation Time:** {f_data['execution_seconds']}s  ")
        md_lines.append(f"**Character Count:** {len(f_data['final_content'])}\n")
        md_lines.append("#### Copy-Paste Content:\n")
        md_lines.append("````markdown")
        md_lines.append(f_data["final_content"])
        md_lines.append("````\n")
        if f_data["provenance"]:
            md_lines.append("**Provenance Trail:**")
            for prov in f_data["provenance"]:
                md_lines.append(f"- `{prov.get('citation_marker')}`: {prov.get('source_reference')}")
            md_lines.append("")

    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    # Build JSON Document
    json_data = {
        "execution_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_execution_seconds": total_execution_time,
        "test_files_processed": {
            "document": extracted_results.get("document", {}).get("filename"),
            "audio": extracted_results.get("audio", {}).get("filename"),
            "images": [img["filename"] for img in extracted_results.get("images", [])],
            "video": extracted_results.get("video", {}).get("filename"),
        },
        "previews": {
            k: {
                "display_name": platform_labels.get(k, k),
                "draft_title": preview_bundle.previews[k].draft_title if k in preview_bundle.previews else "",
                "draft_content": preview_bundle.previews[k].draft_content if k in preview_bundle.previews else "",
                "sensitive_flags_count": len(preview_bundle.previews[k].sensitive_flags) if k in preview_bundle.previews else 0,
                "citations_used": preview_bundle.previews[k].citations_used if k in preview_bundle.previews else [],
            }
            for k in selected_platforms
        },
        "final_deliverables": final_deliverables,
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)

    print("\n" + "=" * 80)
    print(f"🎉 COMPLETED SUCCESSFULLY IN {total_execution_time}s!")
    print(f"Outputs saved to:\n  -> {OUTPUT_MD}\n  -> {OUTPUT_JSON}")
    print("=" * 80)


if __name__ == "__main__":
    run_pipeline_suite()
