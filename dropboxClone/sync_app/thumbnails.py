import os
import io
import tempfile
from PIL import Image
import ffmpeg
from pdf2image import convert_from_bytes
from typing import Optional

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
PDF_EXTENSIONS = {".pdf"}


def get_file_category(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    elif ext in VIDEO_EXTENSIONS:
        return "video"
    elif ext in PDF_EXTENSIONS:
        return "pdf"
    else:
        return "other"


def generate_thumbnail(file_data: bytes, path: str) -> Optional[bytes]:
    category = get_file_category(path)
    if category == "image":
        return _thumbnail_from_image(file_data)
    elif category == "video":
        return _thumbnail_from_video(file_data)
    elif category == "pdf":
        return _thumbnail_from_pdf(file_data)
    return None


def _thumbnail_from_image(file_data: bytes) -> bytes:
    img = Image.open(io.BytesIO(file_data))
    img.thumbnail((200, 200))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    output = io.BytesIO()
    img.save(output, format="JPEG")
    return output.getvalue()


def _thumbnail_from_pdf(file_data: bytes) -> bytes:
    pages = convert_from_bytes(file_data, first_page=1, last_page=1)
    img = pages[0]
    img.thumbnail((200, 200))
    output = io.BytesIO()
    img.save(output, format="JPEG")
    return output.getvalue()


def _thumbnail_from_video(file_data: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(file_data)
        tmp_path = tmp.name

    out, _ = (
        ffmpeg.input(tmp_path, ss=1)
        .output("pipe:", vframes=1, format="image2", vcodec="mjpeg")
        .run(capture_stdout=True, quiet=True)
    )

    os.remove(tmp_path)
    return out
