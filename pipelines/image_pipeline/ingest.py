"""
Image Pipeline Ingestion Orchestrator.
Standardized interface matching the multimodal pipeline layout.
"""
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Union, Optional

try:
    from pipelines.base import BasePipeline
except (ImportError, ValueError):
    from ..base import BasePipeline
from .schema import PipelineResult, ImageProvenance, GroundingAnchor, BoundingBox
from .extractors.preprocessor import ImagePreprocessor
from .extractors.ocr_utils import ImageOCRUtils
from .interpreters.interpreter import ImageVisionInterpreter
from .formatter import format_to_markdown
from .mock import get_mock_pipeline_result


class ImagePipeline(BasePipeline):
    """Unified Image Ingestion & Visual Grounding Pipeline."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.interpreter = ImageVisionInterpreter(api_key=api_key, model=model)

    def process(
        self,
        image_input: Union[str, Path, bytes],
        image_name: Optional[str] = None,
        force_mock: bool = False,
    ) -> PipelineResult:
        start_time = time.time()

        processed_bytes, resolved_name, file_size_kb, resolution = ImagePreprocessor.load_and_preprocess(
            image_input=image_input,
            default_name="diagram.jpg",
        )
        final_image_name = image_name or resolved_name

        # Extract OCR word and line bounding boxes from the image tensor
        ocr_result = ImageOCRUtils.detect_ocr_boxes(processed_bytes)
        detected_boxes = ocr_result.get("boxes", [])

        if force_mock or not self.interpreter.is_available:
            exec_time = int((time.time() - start_time) * 1000)
            mock_res = get_mock_pipeline_result(
                image_name=final_image_name,
                file_size_kb=file_size_kb,
                resolution=resolution,
                execution_time_ms=exec_time,
            )
            # If real image had OCR boxes detected, dynamically calibrate mock anchors to real boxes
            if detected_boxes and len(detected_boxes) > 3:
                for a in mock_res.grounding_sources:
                    matched_box = ImageOCRUtils.match_phrase_to_bbox(
                        target_text=a.extracted_verbatim,
                        detected_boxes=detected_boxes,
                        default_anchor=a.visual_anchor,
                    )
                    a.bbox = BoundingBox(**matched_box)
                    a.all_boxes = detected_boxes
                mock_res.all_boxes = detected_boxes
            return mock_res

        try:
            parsed_data, anchors, entities, used_model = self.interpreter.interpret(
                image_bytes=processed_bytes,
                image_name=final_image_name,
                resolution=resolution,
            )

            title = parsed_data.get("title") or "Cybersecurity Diagram Advisory"
            overview = parsed_data.get("overview") or parsed_data.get("summary") or f"Analysis of `{final_image_name}`."
            section_title = parsed_data.get("section_title") or "Key Benefits"
            key_points = parsed_data.get("key_points", [])
            grounding_score = float(parsed_data.get("grounding_score_percent") or 99.0)

            # Ground each anchor with exact 2D bounding box from OCR detection
            for anchor in anchors:
                if not anchor.bbox:
                    matched_box = ImageOCRUtils.match_phrase_to_bbox(
                        target_text=anchor.extracted_verbatim,
                        detected_boxes=detected_boxes,
                        default_anchor=anchor.visual_anchor,
                    )
                    anchor.bbox = BoundingBox(**matched_box)
                anchor.all_boxes = detected_boxes

            exec_time = int((time.time() - start_time) * 1000)

            provenance = ImageProvenance(
                source_image_name=final_image_name,
                source_file_size_kb=file_size_kb,
                total_extracted_nodes=len(anchors),
                extraction_timestamp=datetime.now(timezone.utc).isoformat(),
                grounding_score_percent=grounding_score,
                resolution=resolution,
                total_detected_boxes=len(detected_boxes),
            )

            markdown_output = format_to_markdown(
                image_name=final_image_name,
                title=title,
                overview=overview,
                anchors=anchors,
                section_title=section_title,
                key_points=key_points,
                entities=entities,
                provenance=provenance,
            )

            extracted_text_raw = "\n".join(
                f"[{a.id}] ({a.visual_anchor}): {a.extracted_verbatim}" for a in anchors
            )

            return PipelineResult(
                metadata=provenance,
                title=title,
                summary=overview,
                extracted_text_raw=extracted_text_raw,
                grounding_sources=anchors,
                markdown_output=markdown_output,
                entities_detected=entities,
                execution_time_ms=exec_time,
                mode="live",
                model=used_model,
                all_boxes=detected_boxes,
            )

        except Exception as e:
            print(f"[ImagePipeline Notice] Live extraction fallback triggered: {e}")
            exec_time = int((time.time() - start_time) * 1000)
            mock_res = get_mock_pipeline_result(
                image_name=final_image_name,
                file_size_kb=file_size_kb,
                resolution=resolution,
                execution_time_ms=exec_time,
            )
            if detected_boxes and len(detected_boxes) > 3:
                for a in mock_res.grounding_sources:
                    matched_box = ImageOCRUtils.match_phrase_to_bbox(
                        target_text=a.extracted_verbatim,
                        detected_boxes=detected_boxes,
                        default_anchor=a.visual_anchor,
                    )
                    a.bbox = BoundingBox(**matched_box)
                    a.all_boxes = detected_boxes
                mock_res.all_boxes = detected_boxes
            return mock_res


def ingest_image(
    image_input: Union[str, Path, bytes],
    image_name: Optional[str] = None,
    force_mock: bool = False,
) -> PipelineResult:
    """Convenience procedural entry point for image ingestion."""
    pipeline = ImagePipeline()
    return pipeline.process(image_input=image_input, image_name=image_name, force_mock=force_mock)
