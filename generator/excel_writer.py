"""
Excel export utility.
Writes customers / accounts / transactions to a multi-sheet XLSX file
matching the exact layout of CUST-ML-TEST-001_ml_dataset.xlsx.
"""

import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Column order exactly as in the reference file
CUSTOMER_COLS = [
    "customer_id", "full_name", "email", "phone", "date_of_birth",
    "country", "residency_country", "kyc_status", "kyc_last_review",
    "pep_flag", "sanctions_flag", "adverse_media_flag", "risk_level",
    "risk_score", "customer_type", "customer_metadata",
]

ACCOUNT_COLS = [
    "account_id", "customer_id", "account_type", "account_status",
    "currency", "balance", "opened_date", "account_metadata",
]

TRANSACTION_COLS = [
    "transaction_id", "customer_id", "account_id", "transaction_date",
    "transaction_type", "amount", "currency", "risk_flags",
    "source_system", "meta_counterparty", "meta_counterparty_type",
    "meta_location", "meta_country", "meta_country_code",
    "meta_destination_country", "meta_origin_country", "meta_source",
]

DATA_DICT = [
    ("Customer", "customer_id", "String (Categorical/Text)", "object"),
    ("Customer", "full_name", "String (Categorical/Text)", "object"),
    ("Customer", "email", "String (Categorical/Text)", "object"),
    ("Customer", "phone", "String (Categorical/Text)", "object"),
    ("Customer", "date_of_birth", "String (Categorical/Text)", "object"),
    ("Customer", "country", "String (Categorical/Text)", "object"),
    ("Customer", "residency_country", "String (Categorical/Text)", "object"),
    ("Customer", "kyc_status", "String (Categorical/Text)", "object"),
    ("Customer", "kyc_last_review", "String (Categorical/Text)", "object"),
    ("Customer", "pep_flag", "Boolean", "bool"),
    ("Customer", "sanctions_flag", "Boolean", "bool"),
    ("Customer", "adverse_media_flag", "Boolean", "bool"),
    ("Customer", "risk_level", "String (Categorical/Text)", "object"),
    ("Customer", "risk_score", "Float", "float64"),
    ("Customer", "customer_type", "String (Categorical/Text)", "object"),
    ("Customer", "customer_metadata", "String (Categorical/Text)", "object"),
    ("Accounts", "account_id", "String (Categorical/Text)", "object"),
    ("Accounts", "customer_id", "String (Categorical/Text)", "object"),
    ("Accounts", "account_type", "String (Categorical/Text)", "object"),
    ("Accounts", "account_status", "String (Categorical/Text)", "object"),
    ("Accounts", "currency", "String (Categorical/Text)", "object"),
    ("Accounts", "balance", "Float", "float64"),
    ("Accounts", "opened_date", "String (Categorical/Text)", "object"),
    ("Accounts", "account_metadata", "String (Categorical/Text)", "object"),
    ("Transactions", "transaction_id", "String (Categorical/Text)", "object"),
    ("Transactions", "customer_id", "String (Categorical/Text)", "object"),
    ("Transactions", "account_id", "String (Categorical/Text)", "object"),
    ("Transactions", "transaction_date", "String (Categorical/Text)", "object"),
    ("Transactions", "transaction_type", "String (Categorical/Text)", "object"),
    ("Transactions", "amount", "Float", "float64"),
    ("Transactions", "currency", "String (Categorical/Text)", "object"),
    ("Transactions", "risk_flags", "String (Categorical/Text)", "object"),
    ("Transactions", "source_system", "String (Categorical/Text)", "object"),
    ("Transactions", "meta_counterparty", "String (Categorical/Text)", "object"),
    ("Transactions", "meta_counterparty_type", "String (Categorical/Text)", "object"),
    ("Transactions", "meta_location", "String (Categorical/Text)", "object"),
    ("Transactions", "meta_country", "String (Categorical/Text)", "object"),
    ("Transactions", "meta_country_code", "String (Categorical/Text)", "object"),
    ("Transactions", "meta_destination_country", "String (Categorical/Text)", "object"),
    ("Transactions", "meta_origin_country", "String (Categorical/Text)", "object"),
    ("Transactions", "meta_source", "String (Categorical/Text)", "object"),
]


def _style_header(ws, num_cols: int):
    """Apply header styling: bold white text on dark blue background."""
    header_fill = PatternFill("solid", fgColor="1F3864")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    thin = Side(style="thin", color="B0B0B0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for col in range(1, num_cols + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border


def _auto_width(ws):
    """Auto-fit column widths (capped at 60)."""
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 4, 60)


def _write_sheet(wb: Workbook, sheet_name: str, columns: list, rows: list):
    ws = wb.create_sheet(sheet_name)
    ws.append(columns)
    _style_header(ws, len(columns))
    for row in rows:
        ws.append([row.get(col) for col in columns])
    _auto_width(ws)
    ws.freeze_panes = "A2"


def build_workbook(dataset: dict) -> Workbook:
    """Build an openpyxl Workbook from a dataset dict."""
    wb = Workbook()
    wb.remove(wb.active)  # remove default sheet

    _write_sheet(wb, "Customer", CUSTOMER_COLS, dataset["customers"])
    _write_sheet(wb, "Accounts", ACCOUNT_COLS, dataset["accounts"])
    _write_sheet(wb, "Transactions", TRANSACTION_COLS, dataset["transactions"])

    # Data Dictionary sheet
    ws_dict = wb.create_sheet("Data_Dictionary")
    ws_dict.append(["Table Name", "Column Name", "Required Data Type", "Pandas Dtype"])
    _style_header(ws_dict, 4)
    for row in DATA_DICT:
        ws_dict.append(list(row))
    _auto_width(ws_dict)
    ws_dict.freeze_panes = "A2"

    return wb


def workbook_to_bytes(wb: Workbook) -> bytes:
    """Serialize workbook to bytes for HTTP response."""
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
