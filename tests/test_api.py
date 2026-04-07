from __future__ import annotations

from pathlib import Path
import threading

from fastapi.testclient import TestClient

from pdf2ppt.api import app

client = TestClient(app)


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_convert_success(monkeypatch, tmp_path):
    captured = {}

    def fake_run_pipeline(**kwargs):
        captured.update(kwargs)
        Path(kwargs["output_pptx"]).write_bytes(b"pptx-bytes")

    monkeypatch.setattr("pdf2ppt.api.run_pipeline", fake_run_pipeline)

    response = client.post(
        "/convert",
        files={"file": ("input.pdf", _pdf_bytes(), "application/pdf")},
        data={"pages": "1-2", "ocr": "on", "ocr_engine": "paddle"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    assert response.content == b"pptx-bytes"
    assert captured["pages"] == "1-2"
    assert captured["ocr"] == "on"
    assert captured["ocr_engine"] == "paddle"


def test_convert_rejects_second_request(monkeypatch):
    release = threading.Event()
    started = threading.Event()

    def fake_run_pipeline(**kwargs):
        started.set()
        release.wait(timeout=5)
        Path(kwargs["output_pptx"]).write_bytes(b"pptx-bytes")

    monkeypatch.setattr("pdf2ppt.api.run_pipeline", fake_run_pipeline)

    first_response = {}

    def first_request():
        first_response["response"] = client.post(
            "/convert",
            files={"file": ("first.pdf", _pdf_bytes(), "application/pdf")},
        )

    thread = threading.Thread(target=first_request)
    thread.start()
    assert started.wait(timeout=5)

    second = client.post(
        "/convert",
        files={"file": ("second.pdf", _pdf_bytes(), "application/pdf")},
    )

    assert second.status_code == 429
    release.set()
    thread.join(timeout=5)
    assert first_response["response"].status_code == 200


def test_convert_rejects_non_pdf(monkeypatch):
    monkeypatch.setattr("pdf2ppt.api.run_pipeline", lambda **kwargs: None)

    response = client.post(
        "/convert",
        files={"file": ("input.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
