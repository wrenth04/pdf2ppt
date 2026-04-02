import numpy as np

from pdf2ppt.model.elements import Rect
from pdf2ppt.pdf.extractor import _parse_pages
from pdf2ppt.pdf import ocr


def test_parse_pages_ranges():
    assert _parse_pages("1-3", 5) == [0, 1, 2]
    assert _parse_pages("1-3,5", 6) == [0, 1, 2, 4]
    assert _parse_pages("2,4-5", 7) == [1, 3, 4]
    assert _parse_pages("10", 12) == [9]
    assert _parse_pages("2-2", 3) == [1]


def test_parse_pages_page_one_two():
    assert _parse_pages("1-2", 5) == [0, 1]


def test_notebooklm_watermark_detection_bottom_right():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    assert ocr._is_notebooklm_watermark(image, Rect(82, 82, 98, 96), "NotebookLM")
    assert not ocr._is_notebooklm_watermark(image, Rect(20, 20, 40, 40), "NotebookLM")
    assert not ocr._is_notebooklm_watermark(image, Rect(82, 82, 98, 96), "other text")


def test_clean_page_background_masks_notebooklm_but_excludes_text(monkeypatch):
    image = np.zeros((100, 100, 3), dtype=np.uint8)

    class Pix:
        samples = image.tobytes()
        n = 3
        width = 100
        height = 100

    class PageRect:
        width = 100
        height = 100

    class Page:
        number = 0
        rect = PageRect()

        def get_pixmap(self):
            return Pix()

    raw_boxes = [
        (Rect(80, 80, 96, 96), "NotebookLM", 99.0),
        (Rect(10, 10, 30, 30), "Hello", 99.0),
    ]
    captured = {}

    monkeypatch.setattr(ocr, "_detect_raw_boxes", lambda *args, **kwargs: raw_boxes)
    def fake_inpaint(image, mask, backend):
        captured["mask"] = mask.copy()
        return image

    monkeypatch.setattr(ocr, "_run_inpaint_backend", fake_inpaint)

    boxes, cleaned = ocr.clean_page_background(Page(), "eng", inpaint_backend="heavy")

    assert len(boxes) == 1
    assert boxes[0].paragraphs[0].runs[0].text == "Hello"
    assert cleaned.shape == image.shape
    mask = captured["mask"]
    assert mask[85:96, 85:96].any()
    assert mask[12:28, 12:28].any()
