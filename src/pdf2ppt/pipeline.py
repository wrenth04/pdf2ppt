from .pdf import extractor, ocr as ocr_mod
from .pptx import writer

def run_pipeline(
    input_pdf: str,
    output_pptx: str,
    pages: str | None = None,
    font_map: str | None = None,
    debug_layout: bool = False,
    image_mode: str = "auto",
    textbox_merge: str = "off",
    strict: bool = False,
    ocr: str = "on",
    ocr_lang: str = "eng+jpn+chi_sim+chi_tra",
    ocr_engine: str = "paddle",
    deskew: bool = True,
    inpaint_backend: str = "telea",
):
    doc = extractor.extract_document(
        input_pdf=input_pdf,
        pages=pages,
        debug_layout=debug_layout,
        image_mode=image_mode,
        textbox_merge=textbox_merge,
        ocr=ocr,
        ocr_lang=ocr_lang,
        ocr_engine=ocr_engine,
        deskew=deskew,
        inpaint_backend=inpaint_backend,
    )
    writer.render_pptx(
        document=doc,
        output_path=output_pptx,
        font_map_path=font_map,
        strict=strict,
    )
