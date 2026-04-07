import numpy as np

from pdf2ppt.model.elements import ImageElement, Rect, TextBox
from pdf2ppt.pdf import ocr
from pdf2ppt.pdf import extractor
from pdf2ppt.pdf.extractor import _parse_pages


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


def test_extract_document_raster_fallback_for_dominant_failed_image(monkeypatch):
    class FakeRect:
        width = 100
        height = 100
        x0 = 0
        y0 = 0
        x1 = 100
        y1 = 100

    class FakePage:
        number = 4
        rect = FakeRect()

        def get_text(self, kind):
            assert kind == "rawdict"
            return {
                "blocks": [
                    {
                        "type": 0,
                        "bbox": [10, 10, 20, 20],
                        "lines": [
                            {
                                "spans": [
                                    {"text": "Footer", "font": "Arial", "size": 10, "flags": 0, "color": 0},
                                ]
                            }
                        ],
                    },
                    {
                        "type": 1,
                        "image": True,
                        "xref": None,
                        "bbox": [0, 0, 100, 100],
                    },
                ]
            }

        def get_pixmap(self):
            class Pix:
                width = 100
                height = 100
                samples = np.zeros((100, 100, 3), dtype=np.uint8).tobytes()
                n = 3

                def tobytes(self, fmt):
                    return self.samples

            return Pix()

    class FakeDoc:
        page_count = 1

        def __getitem__(self, idx):
            return FakePage()

        def extract_image(self, xref):
            raise RuntimeError("missing image")

    monkeypatch.setattr(extractor.fitz, "open", lambda path: FakeDoc())

    cleaned = np.zeros((100, 100, 3), dtype=np.uint8)
    ocr_boxes = [TextBox(bbox=Rect(1, 1, 5, 5), paragraphs=[], z_index=0)]
    monkeypatch.setattr(extractor, "clean_page_background", lambda **kwargs: (ocr_boxes, cleaned))

    doc = extractor.extract_document("dummy.pdf")

    assert len(doc.pages) == 1
    page = doc.pages[0]
    assert any(isinstance(el, ImageElement) and el.bbox == Rect(0, 0, 100, 100) for el in page.elements)
    assert any(isinstance(el, TextBox) and el.paragraphs[0].runs[0].text == "Footer" for el in page.elements)
    assert not any(getattr(el, "is_ocr", False) for el in page.elements if isinstance(el, TextBox) and el.paragraphs and el.paragraphs[0].runs)
