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

## Python dependencies

Install the project and its Python dependencies:

```bash
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

## Usage

```bash
pdf2ppt input.pdf output.pptx
```

Common options:

```bash
pdf2ppt input.pdf output.pptx --ocr auto --ocr-engine paddle --deskew true
pdf2ppt input.pdf output.pptx --pages 1-3,5
pdf2ppt input.pdf output.pptx --debug-layout
```

## Notes

- The default OCR language set is `eng+jpn+chi_sim+chi_tra`.
- Use `--ocr off` if you only want native PDF text and images.
- Use `--ocr-engine hocr` or `--ocr-engine tesseract` if PaddleOCR is unavailable in your environment.
