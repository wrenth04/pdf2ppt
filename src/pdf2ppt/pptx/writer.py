from __future__ import annotations

import io
from typing import Optional

from pptx import Presentation
from pptx.util import Emu, Pt

from ..model.elements import DocumentModel, TextBox, ImageElement

EMU_PER_PT = 12700


def _pt_to_emu(value: float) -> Emu:
    return Emu(int(value * EMU_PER_PT))


def _pt_to_pt(value: float) -> Pt:
    return Pt(value)


def _invert_y(pdf_y: float, page_height_pt: float) -> float:
    return page_height_pt - pdf_y


def _bbox_to_ppt_coords(bbox, page_height_pt: float):
    x0 = bbox.x0
    y1 = _invert_y(bbox.y1, page_height_pt)  # top
    width = bbox.x1 - bbox.x0
    height = bbox.y1 - bbox.y0
    return x0, y1, width, height


def _add_textbox(slide, textbox: TextBox, page_height_pt: float):
    x0, y_top, width_pt, height_pt = _bbox_to_ppt_coords(textbox.bbox, page_height_pt)
    left = _pt_to_emu(x0)
    top = _pt_to_emu(y_top)
    width = _pt_to_emu(width_pt)
    height = _pt_to_emu(height_pt)
    shape = slide.shapes.add_textbox(left, top, width, height)
    txf = shape.text_frame
    txf.clear()
    for i, para in enumerate(textbox.paragraphs):
        p = txf.paragraphs[0] if i == 0 else txf.add_paragraph()
        for run in para.runs:
            r = p.add_run()
            r.text = run.text
            r.font.name = run.font_family
            r.font.size = _pt_to_pt(run.font_size_pt)
            r.font.bold = run.bold
            r.font.italic = run.italic
            r.font.underline = run.underline
            if run.color:
                r.font.color.rgb = _hex_to_rgb(run.color)
    if getattr(textbox, "rotation", 0):
        shape.rotation = textbox.rotation


def _hex_to_rgb(hex_color: str):
    from pptx.dml.color import RGBColor
    hex_color = hex_color.lstrip('#')
    return RGBColor(int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))


def _add_image(slide, image: ImageElement, images_store: dict, page_height_pt: float):
    img_bytes = images_store.get(image.image_ref, b"")
    if not img_bytes:
        return
    x0, y_top, width_pt, height_pt = _bbox_to_ppt_coords(image.bbox, page_height_pt)
    left = _pt_to_emu(x0)
    top = _pt_to_emu(y_top)
    width = _pt_to_emu(width_pt)
    height = _pt_to_emu(height_pt)
    pic = slide.shapes.add_picture(io.BytesIO(img_bytes), left, top, width=width, height=height)
    if getattr(image, "rotation", 0):
        pic.rotation = image.rotation


def render_pptx(document: DocumentModel, output_path: str, font_map_path: Optional[str] = None, strict: bool = False):
    prs = Presentation()
    images_store = document.metadata.get("images", {}) if document.metadata else {}

    # set slide size from first page (assume consistent)
    if document.pages:
        prs.slide_width = _pt_to_emu(document.pages[0].width_pt)
        prs.slide_height = _pt_to_emu(document.pages[0].height_pt)

    for page in document.pages:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        page_h = page.height_pt
        for element in sorted(page.elements, key=lambda e: getattr(e, "z_index", 0)):
            if isinstance(element, ImageElement):
                _add_image(slide, element, images_store, page_h)
            elif isinstance(element, TextBox):
                _add_textbox(slide, element, page_h)

    prs.save(output_path)
