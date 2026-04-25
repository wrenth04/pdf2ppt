import numpy as np
from PIL import Image
import io

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


def test_build_ocr_textbox_uses_inflated_bbox():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    box, rect_mask_px, _ = ocr._build_ocr_textbox(
        image=image,
        page_width_pt=100,
        page_height_pt=100,
        rect_px=Rect(10, 10, 20, 20),
        text="Hello",
        conf=99.0,
        pad_x=4,
        pad_y=2,
    )

    assert box.bbox.x1 - box.bbox.x0 == rect_mask_px.x1 - rect_mask_px.x0
    assert box.bbox.x1 - box.bbox.x0 > 10


def test_extract_image_document_builds_editable_text(monkeypatch, tmp_path):
    image_path = tmp_path / "sample.png"
    image = Image.new("RGB", (100, 60), "white")
    image.save(image_path)

    from pdf2ppt.image import extractor as image_extractor

    cleaned = np.zeros((60, 100, 3), dtype=np.uint8)
    ocr_boxes = [
        TextBox(
            bbox=Rect(10, 10, 30, 30),
            paragraphs=[
                extractor.Paragraph(runs=[extractor.TextRun(text="Hello", font_family="Arial", font_size_pt=10)]),
            ],
            z_index=0,
            is_ocr=True,
        )
    ]

    monkeypatch.setattr(image_extractor, "clean_image_background", lambda **kwargs: (ocr_boxes, cleaned))

    doc = image_extractor.extract_document(str(image_path))

    assert len(doc.pages) == 1
    page = doc.pages[0]
    assert any(isinstance(el, ImageElement) and el.bbox == Rect(0, 0, 100.0, 60.0) for el in page.elements)
    assert any(isinstance(el, TextBox) and el.paragraphs[0].runs[0].text == "Hello" for el in page.elements)


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
    ocr_boxes = [
        TextBox(
            bbox=Rect(1, 1, 5, 5),
            paragraphs=[
                extractor.Paragraph(runs=[extractor.TextRun(text="OCR text", font_family="Arial", font_size_pt=10)]),
            ],
            z_index=0,
            is_ocr=True,
        )
    ]
    monkeypatch.setattr(extractor, "clean_page_background", lambda **kwargs: (ocr_boxes, cleaned))

    doc = extractor.extract_document("dummy.pdf")

    assert len(doc.pages) == 1
    page = doc.pages[0]
    assert any(isinstance(el, ImageElement) and el.bbox == Rect(0, 0, 100, 100) for el in page.elements)
    assert any(isinstance(el, TextBox) and el.paragraphs[0].runs[0].text == "Footer" for el in page.elements)
    assert any(
        isinstance(el, TextBox)
        and getattr(el, "is_ocr", False)
        and el.paragraphs
        and el.paragraphs[0].runs
        and el.paragraphs[0].runs[0].text == "OCR text"
        for el in page.elements
    )


def test_openai_backend_dispatch_success(monkeypatch):
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[10:20, 10:20] = 255
    mock_result = np.ones((100, 100, 3), dtype=np.uint8)

    monkeypatch.setattr(ocr, "_run_openai_inpaint", lambda img, msk: mock_result)

    result = ocr._run_inpaint_backend(image, mask, "openai")

    assert np.array_equal(result, mock_result)


def test_openai_backend_dispatch_fallback(monkeypatch):
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[10:20, 10:20] = 255

    monkeypatch.setattr(ocr, "_run_openai_inpaint", lambda img, msk: None)

    result = ocr._run_inpaint_backend(image, mask, "openai")

    assert result is not None
    assert result.shape == image.shape


def test_openai_backend_empty_mask(monkeypatch):
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    mask = np.zeros((100, 100), dtype=np.uint8)
    called = []

    def fake_openai(img, msk):
        called.append(True)
        return img

    monkeypatch.setattr(ocr, "_run_openai_inpaint", fake_openai)

    result = ocr._run_inpaint_backend(image, mask, "openai")

    assert np.array_equal(result, image)
    assert not called


def test_openai_mask_conversion_semantics():
    mask = np.array([[0, 255], [255, 0]], dtype=np.uint8)
    mask_bytes = ocr._encode_openai_mask_png_bytes(mask)

    pil_mask = Image.open(io.BytesIO(mask_bytes)).convert("RGBA")
    alpha = np.array(pil_mask)[:, :, 3]

    assert alpha[0, 0] == 255
    assert alpha[0, 1] == 0
    assert alpha[1, 0] == 0
    assert alpha[1, 1] == 255
