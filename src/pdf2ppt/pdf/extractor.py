from __future__ import annotations

import cv2
import fitz
from typing import Dict, List, Optional

from ..model.elements import (
    DocumentModel,
    ImageElement,
    PageModel,
    Paragraph,
    Rect,
    TextBox,
    TextRun,
)
from ..model.normalize import font_fallback, normalize_font_name
from ..model.grouping import merge_spans_into_lines
from .ocr import clean_page_background, ocr_page_if_needed

__all__ = ["extract_document", "_parse_pages"]


def _parse_pages(pages: Optional[str], page_count: int) -> List[int]:
    if not pages:
        return list(range(page_count))
    selected: List[int] = []
    for part in pages.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            a, b = part.split('-', 1)
            start = int(a) - 1
            end = int(b) - 1
            selected.extend(list(range(start, end + 1)))
        else:
            selected.append(int(part) - 1)
    return [i for i in selected if 0 <= i < page_count]


def _span_to_run(span: dict) -> TextRun:
    font = normalize_font_name(span.get("font", ""))
    return TextRun(
        text=span.get("text", ""),
        font_family=font_fallback(font),
        font_size_pt=span.get("size", 12),
        bold=bool(span.get("flags", 0) & 2),
        italic=bool(span.get("flags", 0) & 1),
        color=_rgb_from_int(span.get("color", 0)),
    )


def _rgb_from_int(color_int: int) -> str:
    r = (color_int >> 16) & 0xFF
    g = (color_int >> 8) & 0xFF
    b = color_int & 0xFF
    return f"#{r:02x}{g:02x}{b:02x}"


def _block_to_textbox(block: dict, z_index: int) -> TextBox:
    bbox = Rect(*block["bbox"])
    paragraphs: List[Paragraph] = []
    for line in block.get("lines", []):
        runs = [_span_to_run(span) for span in line.get("spans", [])]
        paragraphs.append(Paragraph(runs=runs))
    return TextBox(bbox=bbox, paragraphs=paragraphs, z_index=z_index)


def extract_document(
    input_pdf: str,
    pages: str | None = None,
    debug_layout: bool = False,
    image_mode: str = "auto",
    textbox_merge: str = "off",
    ocr: str = "auto",
    ocr_lang: str = "eng+jpn+chi_sim+chi_tra",
    ocr_engine: str = "hocr",
    deskew: bool = True,
    inpaint_backend: str = "auto",
) -> DocumentModel:
    doc = fitz.open(input_pdf)
    page_indices = _parse_pages(pages, doc.page_count)
    images_store: Dict[str, bytes] = {}
    page_models: List[PageModel] = []

    for page_no in page_indices:
        page = doc[page_no]
        width, height = page.rect.width, page.rect.height
        elements = []
        text_boxes = []
        z_counter = 0

        raw = page.get_text("rawdict")
        for block in raw.get("blocks", []):
            btype = block.get("type", 0)
            if btype == 0 and block.get("lines"):
                tb = _block_to_textbox(block, z_index=z_counter)
                text_boxes.append(tb)
                z_counter += 1
            elif btype == 1 and "image" in block:
                xref = block.get("xref")
                bbox = Rect(*block.get("bbox", [0, 0, 0, 0]))
                ref = f"p{page_no}_xref{xref}"
                try:
                    img = doc.extract_image(xref)
                    images_store[ref] = img.get("image", b"")
                    elements.append(
                        ImageElement(
                            bbox=bbox,
                            image_ref=ref,
                            mime_type=img.get("ext"),
                            pixel_width=img.get("width", 0),
                            pixel_height=img.get("height", 0),
                            transform=block.get("transform"),
                            alpha=img.get("colorspace", "") == "rgba",
                            rotation=block.get("rotation", 0.0) or 0.0,
                            z_index=z_counter,
                        )
                    )
                    z_counter += 1
                except Exception:
                    if debug_layout:
                        print(f"warn: failed to extract image xref {xref} on page {page_no}")
                    continue

        if text_boxes:
            if textbox_merge == "on":
                merged = group_textboxes(text_boxes)
                elements.extend(merged)
            else:
                elements.extend(text_boxes)
        else:
            # image-only page; try OCR if allowed
            if ocr != "off":
                # render page as background image to preserve appearance
                bg_ref = f"p{page_no}_bg"
                try:
                    ocr_boxes, cleaned_image = clean_page_background(
                        page=page,
                        languages=ocr_lang,
                        deskew=deskew,
                        engine=ocr_engine,
                        inpaint_backend=inpaint_backend,
                    )
                    images_store[bg_ref] = cv2.imencode(".png", cleaned_image)[1].tobytes()
                    elements.append(
                        ImageElement(
                            bbox=Rect(0, 0, width, height),
                            image_ref=bg_ref,
                            mime_type="png",
                            pixel_width=cleaned_image.shape[1],
                            pixel_height=cleaned_image.shape[0],
                            transform=None,
                            alpha=True,
                            rotation=0.0,
                            z_index=z_counter,
                        )
                    )
                    z_counter += 1
                except Exception:
                    if debug_layout:
                        print(f"warn: failed to render background for page {page_no}")
                    bg_pix = page.get_pixmap()
                    images_store[bg_ref] = bg_pix.tobytes("png")
                    elements.append(
                        ImageElement(
                            bbox=Rect(0, 0, width, height),
                            image_ref=bg_ref,
                            mime_type="png",
                            pixel_width=bg_pix.width,
                            pixel_height=bg_pix.height,
                            transform=None,
                            alpha=True,
                            rotation=0.0,
                            z_index=z_counter,
                        )
                    )
                    z_counter += 1
                    ocr_boxes = ocr_page_if_needed(
                        page=page,
                        languages=ocr_lang,
                        deskew=deskew,
                        debug=debug_layout,
                        engine=ocr_engine,
                    )

                for tb in ocr_boxes:
                    tb.z_index = z_counter
                    tb.is_ocr = True
                    z_counter += 1
                elements.extend(ocr_boxes)

        page_models.append(PageModel(index=page_no, width_pt=width, height_pt=height, elements=elements))

    return DocumentModel(source_path=input_pdf, pages=page_models, metadata={"images": images_store})
