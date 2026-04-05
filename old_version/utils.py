import os
import requests
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from pypdf import PdfWriter, PdfReader
from pypdf.errors import DependencyError
import io

DOWNLOAD_DIR = "downloads"


def is_pdf_file(file_path):
    """
    Detect a PDF by its file signature so encrypted PDFs are not skipped.
    """
    try:
        with open(file_path, "rb") as f:
            return f.read(5) == b"%PDF-"
    except Exception:
        return False


def download_media(media_items):
    """
    Downloads media files from the list of URLs.
    Returns a list of dictionaries with 'path' and 'type' (image/pdf).
    """
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    downloaded_files = []

    for item in media_items:
        url = item["url"]
        item_id = item["id"]

        try:
            filename = url.split("?")[0].split("/")[-1]
            if not filename:
                filename = f"{item_id}"

            local_path = os.path.join(DOWNLOAD_DIR, f"{item_id}_{filename}")

            print(f"Downloading {url[:50]}... to {local_path}")

            response = requests.get(url, stream=True)
            response.raise_for_status()

            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_type = "unknown"
            try:
                img = Image.open(local_path)
                img.verify()
                file_type = "image"
            except Exception:
                if is_pdf_file(local_path):
                    file_type = "pdf"
                else:
                    try:
                        PdfReader(local_path)
                        file_type = "pdf"
                    except Exception:
                        print(f"Skipping unknown file type: {local_path}")
                        continue

            downloaded_files.append({
                "path": local_path,
                "type": file_type
            })

        except Exception as e:
            print(f"Failed to download {url}: {e}")

    return downloaded_files


def create_pdf(downloaded_items, output_filename, label_text=None):
    """
    Creates a single PDF from a list of downloaded items (images or PDFs).
    Images are placed on A4 pages. Existing PDFs are appended.
    If label_text is provided, it is drawn on the top-left corner of every page.
    """
    writer = PdfWriter()
    a4_width, a4_height = A4

    for item in downloaded_items:
        file_path = item["path"]
        file_type = item["type"]

        if file_type == "image":
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=A4)

            try:
                img = Image.open(file_path)
                img_width, img_height = img.size

                margin = 20
                max_width = a4_width - 2 * margin
                max_height = a4_height - 2 * margin

                scale_w = max_width / img_width
                scale_h = max_height / img_height
                scale = min(scale_w, scale_h)

                new_w = img_width * scale
                new_h = img_height * scale

                x = (a4_width - new_w) / 2
                y = (a4_height - new_h) / 2

                c.drawImage(file_path, x, y, width=new_w, height=new_h)

                if label_text:
                    c.setFont("Helvetica", 10)
                    c.drawString(10, a4_height - 15, str(label_text))

                c.showPage()
                c.save()

                packet.seek(0)
                new_pdf = PdfReader(packet)
                writer.append_pages_from_reader(new_pdf)

            except Exception as e:
                print(f"Error adding image to PDF {file_path}: {e}")

        elif file_type == "pdf":
            try:
                reader = PdfReader(file_path)
                for page in reader.pages:
                    if label_text:
                        packet = io.BytesIO()
                        page_width = float(page.mediabox.width)
                        page_height = float(page.mediabox.height)

                        c = canvas.Canvas(packet, pagesize=(page_width, page_height))
                        c.setFont("Helvetica", 10)
                        c.drawString(10, page_height - 15, str(label_text))
                        c.save()

                        packet.seek(0)
                        watermark_pdf = PdfReader(packet)
                        watermark_page = watermark_pdf.pages[0]
                        page.merge_page(watermark_page)

                    writer.add_page(page)
            except DependencyError:
                print(
                    f"Error merging PDF {file_path}: encrypted PDF needs "
                    "'cryptography' installed. Run 'pip install cryptography'."
                )
            except Exception as e:
                print(f"Error merging PDF {file_path}: {e}")

    with open(output_filename, "wb") as f:
        writer.write(f)
