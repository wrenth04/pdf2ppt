import typer

app = typer.Typer(add_completion=False, help="Convert PDF or image to editable PPTX with optional OCR")


@app.command()
def main(
    input_path: str = typer.Argument(..., help="Path to input PDF or image"),
    output_pptx: str = typer.Argument(..., help="Path to output PPTX"),
    pages: str = typer.Option(None, help="Pages to include, e.g., 1-3,5 (PDF only)"),
    font_map: str = typer.Option(None, help="Path to font map JSON"),
    debug_layout: bool = typer.Option(False, help="Enable verbose layout debug logs"),
    image_mode: str = typer.Option("auto", help="auto|extract|rasterize-page"),
    textbox_merge: str = typer.Option("off", help="on|off for textbox merge heuristics"),
    strict: bool = typer.Option(False, help="Fail on unsupported content instead of degrading"),
    ocr: str = typer.Option("on", help="off|on|auto for OCR"),
    ocr_lang: str = typer.Option("eng+jpn+chi_sim+chi_tra", help="Tesseract languages"),
    ocr_engine: str = typer.Option("paddle", help="paddle|hocr|tesseract (paddle recommended)"),
    deskew: bool = typer.Option(True, help="Auto-detect rotation/deskew before OCR"),
    ocr_inpaint_backend: str = typer.Option("openai", help="auto|openai|heavy|telea for background cleanup"),
):
    from .pipeline import run_pipeline
    run_pipeline(
        input_path=input_path,
        output_pptx=output_pptx,
        pages=pages,
        font_map=font_map,
        debug_layout=debug_layout,
        image_mode=image_mode,
        textbox_merge=textbox_merge,
        strict=strict,
        ocr=ocr,
        ocr_lang=ocr_lang,
        ocr_engine=ocr_engine,
        deskew=deskew,
        inpaint_backend=ocr_inpaint_backend,
    )


def entrypoint():
    app()


if __name__ == "__main__":
    entrypoint()
