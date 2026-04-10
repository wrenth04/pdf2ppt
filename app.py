import gradio as gr
import os
import tempfile
import sys
import uuid
import shutil
from pathlib import Path

# Add src directory to sys.path so pdf2ppt can be found
sys.path.append(os.path.join(os.getcwd(), "src"))

from pdf2ppt.pipeline import run_pipeline

def convert_to_pptx(
    input_file,
    pages=None,
    ocr="on",
    ocr_lang="eng+jpn+chi_sim+chi_tra",
    ocr_engine="paddle",
    deskew=True,
    inpaint_backend="telea",
    image_mode="auto",
    textbox_merge="off",
    strict=False,
):
    if input_file is None:
        return None, "Please upload a file."

    request_id = uuid.uuid4().hex

    # Create a dedicated outputs directory in the current working directory
    # This is often more reliable than /tmp in Hugging Face Spaces
    output_dir = Path("outputs")
    try:
        output_dir.mkdir(exist_ok=True)
    except Exception as e:
        return None, f"Failed to create output directory: {str(e)}"

    # Use a unique filename
    output_filename = f"pdf2ppt_{request_id}.pptx"
    final_output_path = output_dir / output_filename

    # Use a temporary directory only for the input file
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / Path(input_file.name).name
        with open(input_file.name, "rb") as f_in, open(input_path, "wb") as f_out:
            f_out.write(f_in.read())

        try:
            run_pipeline(
                input_path=str(input_path),
                output_pptx=str(final_output_path),
                pages=pages,
                ocr=ocr,
                ocr_lang=ocr_lang,
                ocr_engine=ocr_engine,
                deskew=deskew,
                inpaint_backend=inpaint_backend,
                image_mode=image_mode,
                textbox_merge=textbox_merge,
                strict=strict,
            )

            if not final_output_path.exists():
                return None, "Conversion failed: Output file was not created."

            file_size = final_output_path.stat().st_size
            if file_size == 0:
                return None, "Conversion failed: Generated file is empty."

            return str(final_output_path), f"Conversion successful! ({file_size / 1024:.1f} KB)"

        except Exception as e:
            if final_output_path.exists():
                final_output_path.unlink()
            return None, f"Error during conversion: {str(e)}"

# Gradio UI Definition
with gr.Blocks(title="PDF to PPTX Converter") as demo:
    gr.Markdown("# 📄 PDF to PPTX Converter")
    gr.Markdown("Convert PDFs or images into editable PowerPoint presentations using OCR.")

    with gr.Row():
        with gr.Column():
            input_file = gr.File(label="Upload PDF or Image", file_types=[".pdf", ".jpg", ".jpeg", ".png"])

            with gr.Accordion("Advanced Settings", open=False):
                pages = gr.Textbox(label="Pages (PDF only)", placeholder="e.g., 1-3,5", value=None)
                ocr = gr.Dropdown(choices=["on", "off", "auto"], value="on", label="OCR Mode")
                ocr_engine = gr.Dropdown(choices=["paddle", "hocr", "tesseract"], value="paddle", label="OCR Engine")
                ocr_lang = gr.Textbox(label="OCR Languages", value="eng+jpn+chi_sim+chi_tra")
                deskew = gr.Checkbox(label="Auto-deskew", value=True)
                inpaint_backend = gr.Dropdown(choices=["telea", "auto", "heavy"], value="telea", label="Inpaint Backend")
                image_mode = gr.Dropdown(choices=["auto", "extract", "rasterize-page"], value="auto", label="Image Mode")
                textbox_merge = gr.Dropdown(choices=["on", "off"], value="off", label="Textbox Merge")
                strict = gr.Checkbox(label="Strict Mode", value=False)

            convert_btn = gr.Button("Convert to PPTX", variant="primary")

        with gr.Column():
            output_file = gr.File(label="Download PPTX")
            status_msg = gr.Textbox(label="Status", interactive=False)

    convert_btn.click(
        fn=convert_to_pptx,
        inputs=[
            input_file,
            pages,
            ocr,
            ocr_lang,
            ocr_engine,
            deskew,
            inpaint_backend,
            image_mode,
            textbox_merge,
            strict,
        ],
        outputs=[output_file, status_msg],
    )

if __name__ == "__main__":
    demo.launch()
