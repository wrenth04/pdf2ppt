# pdf2ppt

Convert PDF files with mixed text and images into editable PPTX slides while preserving layout as much as possible.

## Features

- Extract text and images from PDFs
- Preserve page layout in PPTX output
- Keep images as slide elements
- OCR support for image-only or flattened text pages
- Optional deskew / rotation handling for OCR

## Requirements

- Python 3.10+
- Linux or macOS
- Tesseract OCR for the `tesseract` / `hocr` OCR paths
- Optional: PaddleOCR for the `paddle` OCR path

## System packages

### Ubuntu / Debian

```bash
sudo apt-get update
sudo apt-get install -y \
  tesseract-ocr \
  tesseract-ocr-eng \
  tesseract-ocr-jpn \
  tesseract-ocr-chi-sim \
  tesseract-ocr-chi-tra \
  libgl1 \
  libglib2.0-0
```

If your system is missing font rendering or PDF utilities, these can also help:

```bash
sudo apt-get install -y fontconfig fonts-dejavu-core
```

### Optional PaddleOCR runtime

If you want to use the `paddle` OCR engine, install the Paddle stack in your virtual environment:

```bash
pip install paddlepaddle paddleocr
```

Depending on your environment, Paddle may also require extra runtime libraries such as OpenCV and OpenVINO-compatible components. The repo already depends on OpenCV through Python packages.

PaddleOCR model files are cached under `~/.paddlex/official_models/` (for example `PP-OCRv5_server_det` and `PP-OCRv5_server_rec`). Delete those directories if you want to force a fresh model download.

### Optional AI background cleanup

The image-only page path can use a mask-guided inpainting backend to remove baked-in text from the raster background before inserting it into PPTX.

The default mode is `auto`, which prefers the local AI backend and falls back to OpenCV inpainting if needed. You can also force a backend with `--ocr-inpaint-backend`:

- `auto` — prefer the AI backend, then fall back to OpenCV
- `heavy` — force the stronger local AI backend
- `telea` — force OpenCV inpainting

```bash
pip install simple-lama-inpainting Pillow
```

The cleanup mask now covers OCR text regions more aggressively so the filled background looks continuous instead of leaving flat color blocks. OCR text boxes themselves are transparent, so they no longer draw a colored rectangle behind the text. The bottom-right `notebooklm` watermark is removed from the background image, but it is not added as editable PPTX text.

## Python dependencies

### With a virtual environment

Recommended installation:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -e .
```

### Without a virtual environment

```bash
pip install -r requirements.txt
pip install -e .
```

Core Python packages used by this project:

- `PyMuPDF` (`pymupdf`)
- `python-pptx`
- `typer`
- `pytesseract`
- `opencv-python`
- `lxml`
- `numpy`
- `diffusers` / `torch` for the heavier AI inpainting backend

## Usage

```bash
pdf2ppt input.pdf output.pptx
```

Common options:

```bash
pdf2ppt input.pdf output.pptx --ocr on --ocr-engine paddle --deskew true
pdf2ppt input.pdf output.pptx --pages 1-3,5
pdf2ppt input.pdf output.pptx --ocr on --ocr-engine paddle --ocr-inpaint-backend heavy
pdf2ppt input.pdf output.pptx --debug-layout
```

To convert a full PDF in the current directory:

```bash
PYTHONPATH=/project/pdf2ppt/src /project/pdf2ppt/.venv/bin/python -m pdf2ppt.cli input.pdf out.pptx --ocr on --ocr-engine paddle
```

## REST API

Start the API server with Uvicorn:

```bash
PYTHONPATH=src .venv/bin/uvicorn pdf2ppt.api:app --reload
```

Open Swagger UI in your browser:

```text
http://127.0.0.1:8000/docs
```

Available endpoints:

- `GET /health` — health check
- `POST /convert` — upload a PDF and download the converted PPTX

`POST /convert` form fields:

- `file` — PDF file upload
- `pages` — page selection string, e.g. `1-3,5`
- `debug_layout` — `true` or `false`
- `image_mode` — `auto`, `extract`, or `rasterize-page`
- `textbox_merge` — `on` or `off`
- `strict` — `true` or `false`
- `ocr` — `off`, `on`, or `auto`
- `ocr_lang` — OCR languages, e.g. `eng+jpn+chi_sim+chi_tra`
- `ocr_engine` — `paddle`, `hocr`, or `tesseract`
- `deskew` — `true` or `false`
- `ocr_inpaint_backend` — `auto`, `heavy`, or `telea` (default: `telea` for both CLI and API)

The API allows only one active conversion at a time. If another PDF is already being processed, `POST /convert` returns `429 Too Many Requests`.

Default API OCR settings:

- `ocr=on`
- `ocr_engine=paddle`

Example request with `curl`:

```bash
curl -X POST "http://127.0.0.1:8000/convert" \
  -F "file=@input.pdf;type=application/pdf" \
  -F "pages=1-2" \
  -F "ocr=on" \
  -F "ocr_engine=paddle" \
  --output output.pptx
```

## Notes

- The default OCR language set is `eng+jpn+chi_sim+chi_tra`.
- Use `--ocr off` if you only want native PDF text and images.
- Use `--ocr-engine hocr` or `--ocr-engine tesseract` if PaddleOCR is unavailable in your environment.
