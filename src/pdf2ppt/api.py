from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

app = FastAPI(title="pdf2ppt API", version="0.1.0")
_convert_lock = Lock()
run_pipeline = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/convert")
async def convert(
    file: UploadFile = File(..., description="PDF file to convert"),
    pages: str | None = Form(None, description="Pages to include, e.g. 1-3,5"),
    debug_layout: bool = Form(False, description="Enable verbose layout debug logs"),
    image_mode: Literal["auto", "extract", "rasterize-page"] = Form(
        "auto",
        description="Image handling mode: auto, extract, or rasterize-page",
    ),
    textbox_merge: Literal["on", "off"] = Form(
        "off",
        description="Textbox merge heuristics: on or off",
    ),
    strict: bool = Form(False, description="Fail on unsupported content instead of degrading"),
    ocr: Literal["off", "on", "auto"] = Form(
        "on",
        description="OCR mode: off, on, or auto",
    ),
    ocr_lang: str = Form(
        "eng+jpn+chi_sim+chi_tra",
        description="OCR languages for Tesseract/Paddle, e.g. eng+jpn+chi_sim+chi_tra",
    ),
    ocr_engine: Literal["paddle", "hocr", "tesseract"] = Form(
        "paddle",
        description="OCR engine: paddle, hocr, or tesseract",
    ),
    deskew: bool = Form(True, description="Auto-detect rotation and deskew before OCR"),
    ocr_inpaint_backend: Literal["auto", "heavy", "telea"] = Form(
        "telea",
        description="Background cleanup backend: auto, heavy, or telea",
    ),
):
    if not _convert_lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Only one PDF can be converted at a time")

    temp_dir = Path(tempfile.mkdtemp(prefix="pdf2ppt-"))
    input_path = temp_dir / (Path(file.filename or "input.pdf").name or "input.pdf")
    output_path = temp_dir / "output.pptx"

    try:
        if file.content_type not in {"application/pdf", "application/octet-stream"}:
            raise HTTPException(status_code=400, detail="Uploaded file must be a PDF")

        with input_path.open("wb") as dst:
            shutil.copyfileobj(file.file, dst)

        global run_pipeline
        if run_pipeline is None:
            try:
                from .pipeline import run_pipeline as _run_pipeline
            except Exception as exc:
                raise HTTPException(status_code=500, detail="Conversion failed") from exc
            run_pipeline = _run_pipeline

        await run_in_threadpool(
            run_pipeline,
            input_pdf=str(input_path),
            output_pptx=str(output_path),
            pages=pages,
            font_map=None,
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
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Conversion failed")
    finally:
        _convert_lock.release()
        await file.close()

    if not output_path.exists():
        raise HTTPException(status_code=500, detail="Conversion did not produce a PPTX file")

    return FileResponse(
        path=str(output_path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=(Path(file.filename or "output.pdf").stem + ".pptx"),
    )
