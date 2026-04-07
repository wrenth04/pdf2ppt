from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import cv2
import numpy as np
from PIL import Image

from ..model.elements import DocumentModel, ImageElement, PageModel, Rect
from ..pdf.ocr import clean_image_background


def _load_image(path: str) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def extract_document(
    input_image: str,
    pages: str | None = None,
    debug_layout: bool = False,
    image_mode: str = "auto",
    textbox_merge: str = "off",
    ocr: str = "on",
    ocr_lang: str = "eng+jpn+chi_sim+chi_tra",
    ocr_engine: str = "paddle",
    deskew: bool = True,
    inpaint_backend: str = "telea",
) -> DocumentModel:
    if pages:
        raise ValueError("pages is only supported for PDF input")

    image = _load_image(input_image)
    height_px, width_px = image.shape[:2]
    page_width_pt = float(width_px)
    page_height_pt = float(height_px)

    images_store: Dict[str, bytes] = {}
    elements: List[ImageElement] = []
    bg_ref = "p0_bg"

    if ocr != "off":
        boxes, bg_image = clean_image_background(
            image=image,
            page_width_pt=page_width_pt,
            page_height_pt=page_height_pt,
            languages=ocr_lang,
            deskew=deskew,
            engine=ocr_engine,
            inpaint_backend=inpaint_backend,
        )
    else:
        bg_image = image
        boxes = []

    images_store[bg_ref] = cv2.imencode(".png", bg_image)[1].tobytes()
    elements.append(
        ImageElement(
            bbox=Rect(0, 0, page_width_pt, page_height_pt),
            image_ref=bg_ref,
            mime_type="png",
            pixel_width=bg_image.shape[1],
            pixel_height=bg_image.shape[0],
            transform=None,
            alpha=True,
            rotation=0.0,
            z_index=0,
        )
    )

    for index, tb in enumerate(boxes, start=1):
        tb.is_ocr = True
        tb.z_index = index
        elements.append(tb)

    return DocumentModel(
        source_path=str(Path(input_image)),
        pages=[PageModel(index=0, width_pt=page_width_pt, height_pt=page_height_pt, elements=elements)],
        metadata={"images": images_store},
    )
