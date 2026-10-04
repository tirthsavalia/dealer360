"""Data loading: bundled synthetic CSV (default) or user upload (CSV / Excel)."""
from __future__ import annotations

import io

import pandas as pd

from .generate_data import DATA_PATH, generate
from .validation import DataValidationError, validate


def load_default() -> tuple[pd.DataFrame, list[str]]:
    """Load the synthetic dataset; regenerate it if the file is missing or unreadable."""
    df = None
    try:
        if DATA_PATH.exists():
            df = pd.read_csv(DATA_PATH)
    except Exception:
        df = None
    if df is None or df.empty:
        df = generate()
    return validate(df)


def load_uploaded(file_name: str, content: bytes) -> tuple[pd.DataFrame, list[str]]:
    """Parse and validate an uploaded CSV/Excel file. Raises ``DataValidationError`` with a friendly message."""
    name = (file_name or "").lower()
    try:
        if name.endswith((".xlsx", ".xlsm", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        elif name.endswith(".csv") or not name:
            df = pd.read_csv(io.BytesIO(content))
        else:
            raise DataValidationError("Unsupported file type. Please upload a .csv or .xlsx file.")
    except DataValidationError:
        raise
    except Exception:
        raise DataValidationError(
            "The file could not be read. Please check that it is a valid CSV/Excel file with a header row."
        ) from None
    return validate(df)
