"""Extract structured data from Chinese electronic VAT invoice PDFs.

This module parses the text layer of ``.pdf`` files produced by Chinese tax
authorities and returns header fields (invoice number, date, buyer, seller) as
well as line-item details (category, name, spec, unit, quantity, price, etc.).
"""

from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import pdfplumber


def normalize_spaces(text: str) -> str:
    """Collapse consecutive whitespace into a single space and strip."""
    return re.sub(r"\s+", " ", text).strip()


def clean_name(name: str | None) -> str | None:
    """Remove all whitespace from a party name (buyer/seller)."""
    if not name:
        return name
    return re.sub(r"\s+", "", name).strip()


def clean_product_name(name: str) -> str:
    """Remove spaces between adjacent Chinese characters in product names."""
    return re.sub(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])", "", name)


@dataclass
class InvoiceItem:
    category: str
    name: str
    spec: str
    unit: str
    qty: float
    unit_price: float
    amount: float
    tax_rate: float
    tax: float

    @property
    def total(self) -> float:
        """Total amount including tax (价税合计)."""
        return self.amount + self.tax

    @property
    def tax_inclusive_unit_price(self) -> float:
        """Unit price that includes tax so unit_price * qty == total."""
        return self.total / self.qty


@dataclass
class Invoice:
    invoice_no: str | None
    date: str | None
    buyer: str | None
    seller: str | None
    items: List[InvoiceItem] = field(default_factory=list)


def parse_invoice(pdf_path: str | os.PathLike) -> Invoice:
    """Parse a single invoice PDF and return an ``Invoice`` object."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        text = pdf.pages[0].extract_text()

    lines = [normalize_spaces(line) for line in text.split("\n") if normalize_spaces(line)]
    full_text = normalize_spaces(text)

    invoice_no = _extract_invoice_no(full_text)
    date = _extract_date(full_text)
    buyer, seller = _extract_parties(full_text)
    buyer = clean_name(buyer)
    seller = clean_name(seller)
    items = _extract_items(lines)

    return Invoice(
        invoice_no=invoice_no,
        date=date,
        buyer=buyer,
        seller=seller,
        items=items,
    )


def _extract_invoice_no(text: str) -> str | None:
    match = re.search(r"\b(\d{20})\b", text)
    return match.group(1) if match else None


def _extract_date(text: str) -> str | None:
    match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if not match:
        return None
    return f"{match.group(1)}年{match.group(2).zfill(2)}月{match.group(3).zfill(2)}日"


def _extract_parties(text: str) -> tuple[str | None, str | None]:
    """Extract buyer and seller names from the invoice header."""
    buyer: str | None = None
    seller: str | None = None

    # Common layout: 购 名称：X 销 名称：Y
    match = re.search(
        r"购\s*名称[：:]\s*([^销]+?)\s+销\s*名称[：:]\s*(.+?)(?=\s+[买售方信]|\s+统一社会信用代码|$)",
        text,
    )
    if match:
        buyer = match.group(1).strip()
        seller = match.group(2).strip()

    # Fallback for invoices where buyer/seller are laid out differently.
    if not buyer or not seller:
        if "南方科技大学" in text:
            buyer = "南方科技大学"
            match = re.search(
                r"南方科技大学(?:\s+124403005521093031)?\s+"
                r"([\u4e00-\u9fa5]+(?:公司|经营部|厂|店|部|中心|研究院|所))",
                text,
            )
            if match:
                seller = match.group(1).strip()

    return buyer, seller


def _extract_items(lines: list[str]) -> list[InvoiceItem]:
    """Locate and parse the item table between the header and 合 计."""
    start_idx: int | None = None
    end_idx: int | None = None

    for idx, line in enumerate(lines):
        if "项目名称" in line and "规格型号" in line:
            start_idx = idx + 1
        if start_idx is not None and "合 计" in line:
            end_idx = idx
            break

    if start_idx is None or end_idx is None:
        return []

    item_lines = lines[start_idx:end_idx]
    grouped: list[list[str]] = []
    current: list[str] = []

    for line in item_lines:
        if line.startswith("*") or re.search(r"%\s*-?\d+(?:\.\d+)?$", line):
            if current:
                grouped.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        grouped.append(current)

    items: list[InvoiceItem] = []
    for group in grouped:
        parsed = _parse_item_group(group)
        if parsed is not None:
            items.append(parsed)
    return items


def _parse_item_group(lines: list[str]) -> InvoiceItem | None:
    """Parse a single invoice line item, including multi-line product names."""
    first_line = lines[0]
    continuations = lines[1:]

    # Tax rate and tax amount always appear at the end of the first line.
    tax_match = re.search(r"(\d+(?:\.\d+)?%\s+-?\d+(?:\.\d+)?)\s*$", first_line)
    if not tax_match:
        return None

    tax_part = tax_match.group(1)
    prefix = first_line[: tax_match.start()].strip()

    tax_rate_str, tax_str = re.split(r"\s+", tax_part.strip())
    tax_rate = float(tax_rate_str.replace("%", ""))
    tax = float(tax_str)

    tokens = prefix.split()
    if len(tokens) < 4:
        # Discount rows and malformed lines are skipped.
        return None

    try:
        amount = float(tokens[-1])
        unit_price = float(tokens[-2])
        qty = float(tokens[-3])
        unit = tokens[-4]
    except ValueError:
        return None

    spec = "无"
    if len(tokens) >= 5:
        candidate = tokens[-5]
        is_category = candidate.startswith("*") and "*" in candidate[1:]
        looks_like_spec = (
            bool(re.search(r"[0-9a-zA-Z*×xX\-/_\.（）()米]", candidate))
            and len(candidate) <= 25
        )
        if looks_like_spec and not is_category:
            spec = candidate
            name_parts = tokens[:-5]
        else:
            name_parts = tokens[:-4]
    else:
        name_parts = tokens[:-4]

    name_parts.extend(continuations)
    name = " ".join(name_parts).strip()
    name = re.sub(r"\s+", " ", name)
    name = clean_product_name(name)

    category = ""
    match = re.match(r"\*([^*]+)\*(.*)", name)
    if match:
        category = match.group(1)
        name = f"*{category}*{match.group(2).strip()}"

    return InvoiceItem(
        category=category,
        name=name,
        spec=spec,
        unit=unit,
        qty=qty,
        unit_price=unit_price,
        amount=amount,
        tax_rate=tax_rate,
        tax=tax,
    )


def parse_all_invoices(pdf_dir: str | os.PathLike) -> list[Invoice]:
    """Parse every PDF in ``pdf_dir`` and return a list of ``Invoice`` objects."""
    pdf_dir = Path(pdf_dir)
    pdf_paths = sorted(
        p for p in pdf_dir.glob("*.pdf")
        if p.name != ".DS_Store"
    )

    results: list[Invoice] = []
    for pdf_path in pdf_paths:
        try:
            results.append(parse_invoice(pdf_path))
        except Exception as exc:
            raise RuntimeError(f"Failed to parse {pdf_path}: {exc}") from exc
    return results
