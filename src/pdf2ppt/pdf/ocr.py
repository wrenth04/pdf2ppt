from __future__ import annotations

from functools import lru_cache
from typing import List, Tuple
import re

import cv2
import numpy as np
import pytesseract
from lxml import html
from PIL import Image

from ..model.elements import Paragraph, Rect, TextBox, TextRun
from ..model.normalize import font_fallback

try:
    from paddleocr import PaddleOCR  # type: ignore
    _PADDLE_AVAILABLE = True
except Exception:
    _PADDLE_AVAILABLE = False

try:
    from simple_lama_inpainting import SimpleLama  # type: ignore
    _SIMPLE_LAMA_AVAILABLE = True
except Exception:
    _SIMPLE_LAMA_AVAILABLE = False

try:
    import torch  # type: ignore
    from diffusers import AutoPipelineForInpainting  # type: ignore
    _DIFFUSERS_AVAILABLE = True
except Exception:
    _DIFFUSERS_AVAILABLE = False


def _clip_rect(rect: Rect, width: int, height: int) -> Rect:
    return Rect(
        x0=max(0, min(width - 1, rect.x0)),
        y0=max(0, min(height - 1, rect.y0)),
        x1=max(0, min(width, rect.x1)),
        y1=max(0, min(height, rect.y1)),
    )


def _sample_color_bgr(image: np.ndarray, rect_px: Rect) -> Tuple[int, int, int]:
    h, w = image.shape[:2]
    r = _clip_rect(rect_px, w, h)
    x0, y0, x1, y1 = map(int, (r.x0, r.y0, r.x1, r.y1))
    if x1 <= x0 or y1 <= y0:
        return (0, 0, 0)
    patch = image[y0:y1, x0:x1]
    # k-means to pick darker cluster as text color
    data = patch.reshape(-1, 3).astype(np.float32)
    if data.shape[0] >= 4:
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, centers = cv2.kmeans(data, 2, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
        centers = centers.astype(np.uint8)
        # choose cluster with lower brightness sum
        sums = centers.sum(axis=1)
        idx = int(np.argmin(sums))
        b, g, r = centers[idx].tolist()
    else:
        mean = patch.reshape(-1, 3).mean(axis=0)
        b, g, r = mean.tolist()
    return int(b), int(g), int(r)


def _inflate_rect(rect_px: Rect, pad_x: int, pad_y: int, width: int, height: int) -> Rect:
    return _clip_rect(
        Rect(rect_px.x0 - pad_x, rect_px.y0 - pad_y, rect_px.x1 + pad_x, rect_px.y1 + pad_y),
        width,
        height,
    )


def _outer_band_pixels(image: np.ndarray, rect_px: Rect, band_px: int = 2) -> np.ndarray:
    h, w = image.shape[:2]
    r = _clip_rect(rect_px, w, h)
    x0, y0, x1, y1 = map(int, (r.x0, r.y0, r.x1, r.y1))
    if x1 <= x0 or y1 <= y0:
        return np.empty((0, 3), dtype=np.uint8)
    parts = []

    def add_patch(xs: int, xe: int, ys: int, ye: int) -> None:
        xs = max(0, min(w, xs))
        xe = max(0, min(w, xe))
        ys = max(0, min(h, ys))
        ye = max(0, min(h, ye))
        if xe <= xs or ye <= ys:
            return
        patch = image[ys:ye, xs:xe]
        if patch.size:
            parts.append(patch.reshape(-1, 3))

    add_patch(x0, x1, y0 - band_px, y0)
    add_patch(x0, x1, y1, y1 + band_px)
    add_patch(x0 - band_px, x0, y0, y1)
    add_patch(x1, x1 + band_px, y0, y1)
    if not parts:
        return np.empty((0, 3), dtype=np.uint8)
    return np.concatenate(parts, axis=0)


def _estimate_background_variance(image: np.ndarray, rect_px: Rect, band_px: int = 2) -> float:
    pixels = _outer_band_pixels(image, rect_px, band_px=band_px)
    if pixels.size == 0:
        return float("inf")
    return float(pixels.astype(np.float32).var(axis=0).mean())


def _sample_background_color_bgr(image: np.ndarray, rect_px: Rect, band_px: int = 2) -> Tuple[int, int, int]:
    pixels = _outer_band_pixels(image, rect_px, band_px=band_px)
    if pixels.size == 0:
        return _sample_color_bgr(image, rect_px)
    median = np.median(pixels.astype(np.float32), axis=0)
    b, g, r = median.tolist()
    return int(b), int(g), int(r)


def _bgr_to_hex(bgr: Tuple[int, int, int]) -> str:
    b, g, r = bgr
    return f"#{r:02x}{g:02x}{b:02x}"


def _normalize_ocr_text(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", text.lower().strip())


def _is_notebooklm_watermark(image: np.ndarray, rect_px: Rect, text: str) -> bool:
    if _normalize_ocr_text(text) != "notebooklm":
        return False
    h, w = image.shape[:2]
    r = _clip_rect(rect_px, w, h)
    center_x = (r.x0 + r.x1) / 2.0
    center_y = (r.y0 + r.y1) / 2.0
    return center_x >= w * 0.75 and center_y >= h * 0.75


def _estimate_bold(image: np.ndarray, rect_px: Rect, ratio_threshold: float = 0.35) -> bool:
    h, w = image.shape[:2]
    r = _clip_rect(rect_px, w, h)
    x0, y0, x1, y1 = map(int, (r.x0, r.y0, r.x1, r.y1))
    if x1 <= x0 or y1 <= y0:
        return False
    patch = image[y0:y1, x0:x1]
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = (binary == 0).sum()
    total = binary.size
    if total == 0:
        return False
    return (dark / total) >= ratio_threshold


def _deskew_image(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.bitwise_not(gray)
    coords = np.column_stack(np.where(gray > 0))
    if coords.size == 0:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated


def _parse_hocr_bbox(el) -> Rect | None:
    title = el.get('title', '')
    parts = title.split(';')
    bbox_part = None
    for p in parts:
        if p.strip().startswith('bbox'):
            bbox_part = p
            break
    if not bbox_part:
        return None
    _, *coords = bbox_part.strip().split()
    if len(coords) < 4:
        return None
    x0, y0, x1, y1 = map(int, coords[:4])
    return Rect(x0, y0, x1, y1)


def _pytesseract_lines_hocr(image: np.ndarray, languages: str) -> List[Tuple[Rect, str, int]]:
    hocr_bytes = pytesseract.image_to_pdf_or_hocr(image, lang=languages, extension='hocr')
    doc = html.fromstring(hocr_bytes)
    results: List[Tuple[Rect, str, int]] = []

    for line_el in doc.xpath('//*[@title and contains(@class, "ocr_line")]'):
        line_bbox = _parse_hocr_bbox(line_el)
        if not line_bbox:
            continue
        words = []
        for w in line_el.xpath('.//*[contains(@class, "ocrx_word")]'):
            text = (w.text_content() or '').strip()
            if text:
                words.append(text)
        content = ' '.join(words).strip()
        if not content:
            continue
        results.append((line_bbox, content, 0))
    return results


def _pytesseract_boxes_hocr(image: np.ndarray, languages: str) -> List[Tuple[Rect, str, int]]:
    hocr_bytes = pytesseract.image_to_pdf_or_hocr(image, lang=languages, extension='hocr')
    doc = html.fromstring(hocr_bytes)
    results: List[Tuple[Rect, str, int]] = []

    # fallback to words if lines not desired
    for el in doc.xpath('//*[@title and contains(@class, "ocrx_word")]'):
        bbox_px = _parse_hocr_bbox(el)
        if not bbox_px:
            continue
        content = (el.text_content() or '').strip()
        if not content:
            continue
        results.append((bbox_px, content, 0))
    return results


def _pytesseract_boxes_data(image: np.ndarray, languages: str) -> List[Tuple[Rect, str, int]]:
    data = pytesseract.image_to_data(image, lang=languages, output_type=pytesseract.Output.DICT)
    n = len(data["text"])
    results: List[Tuple[Rect, str, int]] = []
    for i in range(n):
        text = data["text"][i]
        conf = int(data.get("conf", ["0"])[i]) if data.get("conf") else 0
        if not text.strip():
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        bbox_px = Rect(x, y, x + w, y + h)
        results.append((bbox_px, text, conf))
    return results


def _px_rect_to_pdf(rect_px: Rect, page_width_pt: float, page_height_pt: float, img_width_px: int, img_height_px: int) -> Rect:
    scale_x = page_width_pt / img_width_px
    scale_y = page_height_pt / img_height_px
    x0 = rect_px.x0 * scale_x
    x1 = rect_px.x1 * scale_x
    # Tesseract origin top-left; PDF origin bottom-left
    y0 = (img_height_px - rect_px.y1) * scale_y
    y1 = (img_height_px - rect_px.y0) * scale_y
    return Rect(x0, y0, x1, y1)


def _paddle_ocr_engine(lang: str):
    # PaddleOCR 3.x uses predict/predict_iter; disable doc-level preprocessors for page OCR.
    ocr = PaddleOCR(
        lang=lang,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    return ocr


def _paddle_boxes(image: np.ndarray, languages: str) -> List[Tuple[Rect, str, float]]:
    # map languages string to paddle lang key
    lang_key = "ch" if "chi" in languages else "en"
    ocr = _paddle_ocr_engine(lang_key)
    result = next(
        ocr.predict_iter(
            image,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            return_word_box=False,
        )
    )
    dt_polys = result["dt_polys"]
    rec_texts = result["rec_texts"]
    rec_scores = result["rec_scores"]
    results: List[Tuple[Rect, str, float]] = []
    for bbox, txt, conf in zip(dt_polys, rec_texts, rec_scores):
        pts = np.array(bbox)
        xs = pts[:, 0]
        ys = pts[:, 1]
        rect_px = Rect(float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max()))
        results.append((rect_px, str(txt), float(conf)))
    return results


def _detect_raw_boxes(image: np.ndarray, languages: str, engine: str) -> List[Tuple[Rect, str, float]]:
    if engine == "paddle" and _PADDLE_AVAILABLE:
        try:
            return _paddle_boxes(image, languages)
        except Exception:
            pass
    if engine == "hocr":
        try:
            return _pytesseract_lines_hocr(image, languages)
        except Exception:
            pass
    try:
        return _pytesseract_boxes_data(image, languages)
    except Exception:
        return []


def _build_ocr_textbox(
    image: np.ndarray,
    page,
    rect_px: Rect,
    text: str,
    conf: float,
    pad_x: int,
    pad_y: int,
) -> tuple[TextBox, Rect, float]:
    rect_mask_px = _inflate_rect(rect_px, pad_x, pad_y, image.shape[1], image.shape[0])
    rect_pt = _px_rect_to_pdf(rect_px, page.rect.width, page.rect.height, image.shape[1], image.shape[0])
    height_pt = max(rect_pt.y1 - rect_pt.y0, 1.0)
    font_size = max(height_pt * 0.88, 8)
    color_hex = _bgr_to_hex(_sample_color_bgr(image, rect_px))
    is_bold = _estimate_bold(image, rect_px)
    run = TextRun(
        text=text.lstrip("\n"),
        font_family=font_fallback("Arial"),
        font_size_pt=font_size,
        bold=is_bold,
        italic=False,
        color=color_hex,
    )
    para = Paragraph(runs=[run])
    box = TextBox(
        bbox=rect_pt,
        paragraphs=[para],
        z_index=0,
        is_ocr=True,
        fill_color=None,
        stroke_color=None,
    )
    if _estimate_background_variance(image, rect_px) > 1500.0:
        box.fill_color = None
        box.stroke_color = None
    box.confidence = conf  # type: ignore
    return box, rect_mask_px, float(_estimate_background_variance(image, rect_px))


@lru_cache(maxsize=1)
def _simple_lama_model():
    if not _SIMPLE_LAMA_AVAILABLE:
        return None
    return SimpleLama()


@lru_cache(maxsize=1)
def _diffusers_inpaint_model():
    if not _DIFFUSERS_AVAILABLE:
        return None
    model_id = "stabilityai/stable-diffusion-2-inpainting"
    pipe = AutoPipelineForInpainting.from_pretrained(
        model_id,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        safety_checker=None,
        requires_safety_checker=False,
    )
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipe = pipe.to(device)
    return pipe


def _run_simple_lama_inpaint(image: np.ndarray, mask: np.ndarray) -> np.ndarray | None:
    model = _simple_lama_model()
    if model is None:
        return None
    if mask.max() == 0:
        return image
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    pil_mask = Image.fromarray(mask)
    result = model(pil_image, pil_mask)
    result_arr = np.array(result)
    if result_arr.ndim != 3 or result_arr.shape[:2] != image.shape[:2]:
        return None
    return cv2.cvtColor(result_arr, cv2.COLOR_RGB2BGR)


def _run_diffusers_inpaint(image: np.ndarray, mask: np.ndarray) -> np.ndarray | None:
    pipe = _diffusers_inpaint_model()
    if pipe is None:
        return None
    if mask.max() == 0:
        return image
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    pil_mask = Image.fromarray(mask)
    try:
        generator = None
        if torch.cuda.is_available():
            generator = torch.Generator(device="cuda").manual_seed(0)
        result = pipe(
            prompt="",
            image=pil_image,
            mask_image=pil_mask,
            guidance_scale=1.0,
            num_inference_steps=25,
            generator=generator,
        ).images[0]
    except Exception:
        return None
    result_arr = np.array(result)
    if result_arr.ndim != 3 or result_arr.shape[:2] != image.shape[:2]:
        return None
    return cv2.cvtColor(result_arr, cv2.COLOR_RGB2BGR)


def _run_inpaint_backend(image: np.ndarray, mask: np.ndarray, backend: str) -> np.ndarray | None:
    backend = backend.lower().strip()
    if mask.max() == 0:
        return image
    if backend == "telea":
        return cv2.inpaint(image, mask, 3, cv2.INPAINT_TELEA)
    attempts = []
    if backend in {"auto", "heavy"}:
        attempts.append(_run_diffusers_inpaint)
    if backend == "auto":
        attempts.append(_run_simple_lama_inpaint)
    for attempt in attempts:
        cleaned = attempt(image, mask)
        if cleaned is not None:
            return cleaned
    return cv2.inpaint(image, mask, 3, cv2.INPAINT_TELEA)


def ocr_page_if_needed(page, languages: str, deskew: bool = True, debug: bool = False, engine: str = "paddle") -> List[TextBox]:
    pix = page.get_pixmap()
    buf = np.frombuffer(pix.samples, dtype=np.uint8)
    if pix.n == 4:
        image = buf.reshape(pix.height, pix.width, 4)
        image = cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
    elif pix.n == 3:
        image = buf.reshape(pix.height, pix.width, 3)
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    elif pix.n == 1:
        image = buf.reshape(pix.height, pix.width)
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        image = buf.reshape(pix.height, pix.width, pix.n)
    if deskew and engine != "paddle":  # paddle 有 angle_cls，本身可矯正
        image = _deskew_image(image)

    raw_boxes = _detect_raw_boxes(image, languages, engine)

    boxes: List[TextBox] = []
    for rect_px, text, conf in raw_boxes:
        if _is_notebooklm_watermark(image, rect_px, text):
            continue
        pad_y = max(int((rect_px.y1 - rect_px.y0) * 0.12), 2)
        pad_x = max(int((rect_px.y1 - rect_px.y0) * 0.05), 1)
        rect_mask_px = _inflate_rect(rect_px, pad_x, pad_y, image.shape[1], image.shape[0])
        rect_pt = _px_rect_to_pdf(rect_mask_px, page.rect.width, page.rect.height, image.shape[1], image.shape[0])
        height_pt = max(rect_pt.y1 - rect_pt.y0, 1.0)
        font_size = max(height_pt * 0.88, 8)
        color_hex = _bgr_to_hex(_sample_color_bgr(image, rect_px))
        is_bold = _estimate_bold(image, rect_px)
        run = TextRun(
            text=text.lstrip("\n"),
            font_family=font_fallback("Arial"),
            font_size_pt=font_size,
            bold=is_bold,
            italic=False,
            color=color_hex,
        )
        para = Paragraph(runs=[run])
        box = TextBox(
            bbox=rect_pt,
            paragraphs=[para],
            z_index=0,
            is_ocr=True,
            fill_color=None,
            stroke_color=None,
        )
        if _estimate_background_variance(image, rect_px) > 1500.0:
            box.fill_color = None
            box.stroke_color = None
        box.confidence = conf  # type: ignore
        boxes.append(box)

    if debug:
        print(f"ocr: detected {len(boxes)} boxes on page {page.number} using {engine}")
    return boxes


def clean_page_background(page, languages: str, deskew: bool = True, engine: str = "paddle", inpaint_backend: str = "auto") -> tuple[List[TextBox], np.ndarray]:
    pix = page.get_pixmap()
    buf = np.frombuffer(pix.samples, dtype=np.uint8)
    if pix.n == 4:
        image = buf.reshape(pix.height, pix.width, 4)
        image = cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
    elif pix.n == 3:
        image = buf.reshape(pix.height, pix.width, 3)
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    elif pix.n == 1:
        image = buf.reshape(pix.height, pix.width)
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        image = buf.reshape(pix.height, pix.width, pix.n)
    if deskew and engine != "paddle":
        image = _deskew_image(image)
    image = image.copy()

    raw_boxes = _detect_raw_boxes(image, languages, engine)

    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    boxes: List[TextBox] = []
    for rect_px, text, conf in raw_boxes:
        if conf < 0:
            continue
        is_watermark = _is_notebooklm_watermark(image, rect_px, text)
        pad_y = max(int((rect_px.y1 - rect_px.y0) * 0.10), 2)
        pad_x = max(int((rect_px.x1 - rect_px.x0) * 0.08), 2)
        box, rect_mask_px, _ = _build_ocr_textbox(image, page, rect_px, text, conf, pad_x, pad_y)
        if not is_watermark:
            boxes.append(box)
        x0, y0, x1, y1 = map(int, (rect_mask_px.x0, rect_mask_px.y0, rect_mask_px.x1, rect_mask_px.y1))
        if x1 <= x0 or y1 <= y0:
            continue
        mask[y0:y1, x0:x1] = 255

    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)
    cleaned_image = _run_inpaint_backend(image, mask, inpaint_backend)
    if cleaned_image is None:
        cleaned_image = image
    return boxes, cleaned_image
