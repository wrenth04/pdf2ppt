# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## Common commands

Use the repo root as the working directory.

### Install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -e .
```

### Run the CLI
```bash
PYTHONPATH=src .venv/bin/python -m pdf2ppt.cli input.pdf output.pptx
PYTHONPATH=src .venv/bin/python -m pdf2ppt.cli test1.pdf out.pptx --pages 1-2 --ocr auto --ocr-engine paddle
```

### Run tests
```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_units.py
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_units.py -k parse_pages
```

If `pytest` is not installed in the active environment, install it into `.venv` first:
```bash
.venv/bin/python -m pip install pytest
```

### Quick syntax check
```bash
PYTHONPATH=src python3 -m compileall src/pdf2ppt
```

## Big-picture architecture

The conversion flow is:

1. `src/pdf2ppt/cli.py` parses CLI flags.
2. `src/pdf2ppt/pipeline.py` passes those flags into extraction and PPTX rendering.
3. `src/pdf2ppt/pdf/extractor.py` reads the PDF with PyMuPDF, builds the in-memory document model, and decides whether a page is native-text, image-heavy, or image-only.
4. `src/pdf2ppt/pdf/ocr.py` handles OCR for image-only pages, builds editable OCR `TextBox` objects, and also performs raster background cleanup for those pages.
5. `src/pdf2ppt/pptx/writer.py` renders the document model into PowerPoint slides using `python-pptx`.

The core data model lives in `src/pdf2ppt/model/elements.py`:
- `TextRun` -> text formatting for one run
- `Paragraph` -> grouped runs
- `TextBox` -> editable text regions with bbox/rotation/fill/stroke metadata
- `ImageElement` -> placed page images or extracted embedded images
- `PageModel` / `DocumentModel` -> slide-level containers

## Important implementation details

- OCR page handling is currently centered in `src/pdf2ppt/pdf/ocr.py`.
  - PaddleOCR, hOCR, and Tesseract word boxes are all supported.
  - OCR boxes are converted from pixel coordinates back into PDF-space rectangles for PPT placement.
  - Background cleanup uses OCR-derived masks and can fall back from `simple-lama-inpainting` to OpenCV inpainting.

- `src/pdf2ppt/pdf/extractor.py` is where the page branch is chosen.
  - Native text blocks become `TextBox` objects.
  - Image-only pages are rasterized, cleaned, and then stored in `DocumentModel.metadata["images"]` for the writer.

- `src/pdf2ppt/pptx/writer.py` is intentionally simple.
  - It only places images and text boxes.
  - Any pixel manipulation should happen before this stage.

- Font names are normalized in `src/pdf2ppt/model/normalize.py` and textbox grouping lives in `src/pdf2ppt/model/grouping.py`.

## Environment notes

- The working OCR stack is sensitive to package versions.
- The validated Paddle versions are:
  - `paddlepaddle==3.2.0`
  - `paddleocr==3.3.3`
  - `paddlex==3.3.13`
- PaddleOCR model files are cached under `~/.paddlex/official_models/` (for example `~/.paddlex/official_models/PP-OCRv5_server_det` and `~/.paddlex/official_models/PP-OCRv5_server_rec`). Remove those directories to force a redownload.
- The repo has been exercised successfully with both the system Python and `.venv`, but the most reliable execution path is the `.venv` interpreter.
- `requirements.txt` includes the OCR and background-cleanup dependencies used by the current implementation.
