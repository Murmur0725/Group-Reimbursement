import io
import logging
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.errors import DependencyError
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

_CJK_FONT = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(_CJK_FONT))


def is_pdf_file(file_path):
    path = Path(file_path)

    try:
        with path.open("rb") as file_obj:
            return file_obj.read(5) == b"%PDF-"
    except Exception:
        return False


def create_pdf(downloaded_items, output_filename, label_text=None):
    writer = PdfWriter()
    output_path = Path(output_filename)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    a4_width, a4_height = A4

    for item in downloaded_items:
        file_path = Path(item["path"])
        file_type = item["type"]

        if file_type == "image":
            packet = io.BytesIO()
            pdf_canvas = canvas.Canvas(packet, pagesize=A4)

            try:
                image = Image.open(file_path)
                image_width, image_height = image.size

                margin = 20
                max_width = a4_width - 2 * margin
                max_height = a4_height - 2 * margin

                scale_w = max_width / image_width
                scale_h = max_height / image_height
                scale = min(scale_w, scale_h)

                new_width = image_width * scale
                new_height = image_height * scale

                x = (a4_width - new_width) / 2
                y = (a4_height - new_height) / 2

                pdf_canvas.drawImage(str(file_path), x, y, width=new_width, height=new_height)

                if label_text:
                    pdf_canvas.setFont(_CJK_FONT, 10)
                    pdf_canvas.drawString(10, a4_height - 15, str(label_text))

                pdf_canvas.showPage()
                pdf_canvas.save()

                packet.seek(0)
                writer.append_pages_from_reader(PdfReader(packet))
            except Exception as exc:
                logger.error("Error adding image to PDF %s: %s", file_path, exc)

        elif file_type == "pdf":
            try:
                reader = PdfReader(file_path)
                for page in reader.pages:
                    if label_text:
                        packet = io.BytesIO()
                        page_width = float(page.mediabox.width)
                        page_height = float(page.mediabox.height)

                        pdf_canvas = canvas.Canvas(packet, pagesize=(page_width, page_height))
                        pdf_canvas.setFont(_CJK_FONT, 10)
                        pdf_canvas.drawString(10, page_height - 15, str(label_text))
                        pdf_canvas.save()

                        packet.seek(0)
                        watermark_page = PdfReader(packet).pages[0]
                        page.merge_page(watermark_page)

                    writer.add_page(page)
            except DependencyError:
                logger.error(
                    "Error merging PDF %s: encrypted PDF needs 'cryptography' installed.",
                    file_path,
                )
            except Exception as exc:
                logger.error("Error merging PDF %s: %s", file_path, exc)

    with output_path.open("wb") as file_obj:
        writer.write(file_obj)


def merge_pdfs(pdf_paths, output_path):
    """Merge multiple PDF files into a single PDF in the given order."""
    writer = PdfWriter()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for path in pdf_paths:
        path = Path(path)
        if not path.exists():
            logger.warning("PDF not found, skipping merge: %s", path)
            continue

        try:
            reader = PdfReader(str(path))
            for page in reader.pages:
                writer.add_page(page)
        except DependencyError:
            logger.error(
                "Error merging PDF %s: encrypted PDF needs 'cryptography' installed.",
                path,
            )
        except Exception as exc:
            logger.error("Error merging PDF %s: %s", path, exc)

    with output_path.open("wb") as file_obj:
        writer.write(file_obj)
