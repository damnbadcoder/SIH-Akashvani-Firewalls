import os
import sys
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from .generator import generate_previews
from .types import OutputType

def main():
    parser = argparse.ArgumentParser(description="Standalone CLI test for Preview Pipeline")
    parser.add_argument("--file", type=str, default=None, help="Path to raw source file (PDF, TXT, MD, etc.) to ingest and preview")
    parser.add_argument("--md", type=str, default=None, help="Path to sample markdown file")
    parser.add_argument("--json", type=str, default=None, help="Path to sample JSON metadata file")
    parser.add_argument("--outputs", type=str, required=True, help="Comma separated list of output platforms")
    parser.add_argument("--org", action="store_true", help="Enable organization mode (sensitive data flag/redact)")
    parser.add_argument("--tone", type=str, default="Professional", help="Tone for generation")
    parser.add_argument("--audience", type=str, default="SOC Analysts", help="Target audience")
    parser.add_argument("--detail", type=str, default="High", help="Detail level")
    parser.add_argument("--language", type=str, default="English", help="Output language")
    parser.add_argument("--objective", type=str, default="Generate actionable threat intelligence deliverable", help="Generation objective")
    
    args = parser.parse_args()

    content_md = ""
    metadata_json = {}

    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)

        ext = file_path.suffix.lower()
        if ext in [".pdf", ".txt", ".md", ".log"]:
            from pipelines import ingest_text
            print(f"[preview_pipeline.cli] Ingesting text/document source: {file_path.name}...")
            r = ingest_text(str(file_path), save_outputs=False, enrich=False)
            content_md = r.clean_markdown
            metadata_json = {
                "filename": file_path.name,
                "file_type": "text/pdf" if ext == ".pdf" else "text",
                "files_processed": [file_path.name]
            }
        elif ext in [".png", ".jpg", ".jpeg", ".webp"]:
            from pipelines import ingest_image
            print(f"[preview_pipeline.cli] Ingesting image source: {file_path.name}...")
            r = ingest_image(str(file_path))
            content_md = r.markdown_output
            metadata_json = {"filename": file_path.name, "file_type": "image"}
        elif ext in [".mp3", ".wav", ".m4a"]:
            from pipelines import ingest_audio
            print(f"[preview_pipeline.cli] Ingesting audio source: {file_path.name}...")
            r = ingest_audio(str(file_path))
            content_md = r.markdown_output
            metadata_json = {"filename": file_path.name, "file_type": "audio"}
        elif ext in [".mp4", ".mkv", ".avi", ".mov"]:
            from pipelines import ingest_video
            print(f"[preview_pipeline.cli] Ingesting video source: {file_path.name}...")
            r = ingest_video(str(file_path), save_outputs=False, enrich=False)
            content_md = r.clean_markdown
            metadata_json = {"filename": file_path.name, "file_type": "video"}
        else:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content_md = f.read()
            metadata_json = {"filename": file_path.name}
    elif args.md:
        with open(args.md, "r", encoding="utf-8") as f:
            content_md = f.read()
        if args.json:
            with open(args.json, "r", encoding="utf-8") as f:
                metadata_json = json.load(f)
        else:
            metadata_json = {"filename": Path(args.md).name}
    else:
        print("Error: Either --file or --md must be provided.", file=sys.stderr)
        sys.exit(1)
        
    selected_outputs = [x.strip() for x in args.outputs.split(",")]
    
    # Validate outputs
    valid_outputs = [o.value for o in OutputType]
    invalid = [o for o in selected_outputs if o not in valid_outputs]
    if invalid:
        print(f"Warning: Invalid output types: {invalid}. Valid: {valid_outputs}")
    
    parameters = {
        "tone": args.tone,
        "targetAudience": args.audience,
        "detail": args.detail,
        "language": args.language,
        "objective": args.objective,
    }
    
    print(f"[preview_pipeline.cli] Generating previews for outputs: {selected_outputs} (content length: {len(content_md)} chars)...")
    result = generate_previews(
        content_md=content_md,
        metadata_json=metadata_json,
        selected_outputs=selected_outputs,
        parameters=parameters,
        is_organization=args.org
    )
    
    print(result.model_dump_json(indent=2))

if __name__ == "__main__":
    main()