"""Generate a delivery-order-style Excel sheet from invoice PDFs.

The output format mirrors ``data/线下发货单_已上传.xls``:

    课题号, *产品分类, *货号, *商品名称, *品牌, *包装单位, *规格,
    *单价, *数量, *供应商名称, *收货人, 收货地址, 使用用途, 发票号, 备注

The project number (课题号) is prefilled as ``Y01656113``.
Other fields not present on the invoice (收货人, 收货地址, 使用用途, 备注)
are left blank so the user can fill them in later.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from app.invoice_parser import InvoiceItem, parse_all_invoices


# Column headers exactly matching the reference delivery-order sheet.
COLUMNS = [
    "课题号",
    "*产品分类",
    "*货号",
    "*商品名称",
    "*品牌",
    "*包装单位",
    "*规格",
    "*单价",
    "*数量",
    "*供应商名称",
    "*收货人",
    "收货地址",
    "使用用途",
    "发票号",
    "备注",
]


def item_to_row(invoice_no: str | None, seller: str | None, item: InvoiceItem) -> list:
    """Convert one invoice item into a delivery-order row."""
    # Use the tax-inclusive unit price so that 单价 * 数量 == 价税合计.
    unit_price = item.tax_inclusive_unit_price
    return [
        "Y01656113",  # 课题号
        "实验耗材",  # *产品分类
        "无",  # *货号
        item.name,  # *商品名称
        "无",  # *品牌
        item.unit,  # *包装单位
        item.spec,  # *规格
        unit_price,  # *单价
        item.qty,  # *数量
        seller or "",  # *供应商名称
        "mirna zordan",  # *收货人
        "",  # 收货地址
        "",  # 使用用途
        invoice_no or "",  # 发票号
        "",  # 备注
    ]


def default_delivery_excel_path(pdf_dir: str | os.PathLike) -> Path:
    """Return the default date-and-time-stamped Excel path inside ``pdf_dir``."""
    pdf_dir = Path(pdf_dir)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return pdf_dir / f"发票发货单整理_{timestamp}.xlsx"


# Filename prefix shared by generated delivery-order workbooks.
_DELIVERY_FILENAME_PREFIX = "发票发货单整理_"


def remove_previous_delivery_files(directory: str | os.PathLike) -> int:
    """Remove previously generated delivery-order Excel/CSV files.

    PDF invoices and other unrelated files are left untouched.
    """
    directory = Path(directory)
    removed = 0
    if not directory.exists():
        return removed

    for path in directory.iterdir():
        if not path.is_file():
            continue
        if path.name.startswith(_DELIVERY_FILENAME_PREFIX) and path.suffix.lower() in (
            ".xlsx",
            ".xls",
            ".csv",
        ):
            try:
                path.unlink()
                print(f"  Removed old delivery file: {path.name}")
                removed += 1
            except Exception as exc:
                print(f"  Warning: Could not remove old delivery file {path}: {exc}")
    return removed


def generate_delivery_excel(
    pdf_dir: str | os.PathLike,
    output_path: str | os.PathLike,
) -> Path:
    """Parse all invoices in ``pdf_dir`` and write the delivery-order Excel."""
    pdf_dir = Path(pdf_dir)
    output_path = Path(output_path)

    invoices = parse_all_invoices(pdf_dir)

    workbook = Workbook()
    worksheet = workbook.active
    if worksheet is None:
        raise RuntimeError("Failed to create worksheet")
    worksheet.title = "发票发货单"

    # Header row
    worksheet.append(COLUMNS)
    header_font = Font(bold=True)
    for cell in worksheet[1]:
        cell.font = header_font

    # Data rows
    for invoice in invoices:
        for item in invoice.items:
            worksheet.append(item_to_row(invoice.invoice_no, invoice.seller, item))

    # Auto-adjust column widths for readability.
    for column in worksheet.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            value = cell.value
            if value is not None:
                max_length = max(max_length, len(str(value)))
        worksheet.column_dimensions[column_letter].width = min(max_length + 2, 60)

    # Remove previously generated delivery-order files so only the latest one remains.
    remove_previous_delivery_files(output_path.parent)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(str(output_path))
    return output_path


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    project_root = Path(__file__).resolve().parents[1]
    pdf_dir = project_root / "data" / "fapiao"

    if argv:
        pdf_dir = Path(argv[0])

    output_path = default_delivery_excel_path(pdf_dir)
    if len(argv) >= 2:
        output_path = Path(argv[1])

    if not pdf_dir.exists():
        print(f"Error: invoice directory not found: {pdf_dir}")
        return 1

    try:
        result = generate_delivery_excel(pdf_dir, output_path)
        print(f"Generated delivery order: {result}")
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
