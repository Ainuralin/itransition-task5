"""Read the formula-generated Output sheet as CSV."""

from __future__ import annotations
import hashlib
import io
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent


def numeric_values(column):
    """Accept decimal commas and grouped numbers from localized Sheets exports."""
    def normalize(value):
        text = re.sub(r"\s", "", str(value))
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
        return text

    return pd.to_numeric(column.map(normalize), errors="coerce")


def parse_csv(text):
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    except Exception as exc:
        raise ValueError("The source is not a readable CSV table.") from exc
    df.columns = [str(c).strip() for c in df.columns]
    if not len(df.columns) or df.columns[0] != "Date":
        raise ValueError(
            "The first column must be Date. Share the spreadsheet and keep its Output tab."
        )
    active = [
        c for c in df.columns[1:] if c and not c.startswith("Unnamed:") and c != "Total"
    ]
    if not (1 <= len(active) <= 10) or len(set(active)) != len(active):
        raise ValueError("The Output sheet needs 1–10 uniquely named mine columns.")
    # pandas renames duplicate CSV headers, so inspect the original header too.
    import csv

    header = next(csv.reader(io.StringIO(text)))
    real = [h.strip() for h in header[1:] if h.strip() and h.strip() != "Total"]
    if len(real) != len(set(real)):
        raise ValueError("Mine names must be unique.")
    df = df[df.Date.str.strip().ne("")].copy()
    if not (5 <= len(df) <= 366):
        raise ValueError("The source must contain 5–366 daily observations.")
    dates = pd.to_datetime(df.Date, format="%Y-%m-%d", errors="coerce")
    if dates.isna().any() or dates.duplicated().any():
        raise ValueError("Dates must be unique and formatted YYYY-MM-DD.")
    clean = pd.DataFrame({"Date": dates})
    for name in active:
        values = numeric_values(df[name])
        if values.isna().any() or not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(
                f"Mine {name} contains a missing, invalid or negative value."
            )
        clean[name] = values.astype(float)
    clean = clean.sort_values("Date").reset_index(drop=True)
    if not clean.Date.diff().dropna().eq(pd.Timedelta(days=1)).all():
        raise ValueError("The source must contain consecutive daily dates.")
    if "Total" in df:
        given = numeric_values(df["Total"]).to_numpy()
        original = clean.set_index("Date").loc[dates, active].sum(axis=1).to_numpy()
        if not np.isfinite(given).all() or not np.allclose(
            given, original, atol=0.011, rtol=0
        ):
            raise ValueError("The Total column does not match the sum of the mines.")
    return clean


def load_source(url=None, demo=False):
    if demo:
        raw = (ROOT / "data/demo_output.csv").read_bytes()
        source = "Workbook example"
        link = None
    else:
        match = re.fullmatch(
            r"https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)(?:/[^\s]*)?",
            str(url or "").strip(),
        )
        if not match:
            raise ValueError(
                "Paste a standard https://docs.google.com/spreadsheets/d/... link."
            )
        sheet_id = match.group(1)
        endpoint = (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?"
            + urlencode({"tqx": "out:csv", "sheet": "Output", "range": "A1:L367"})
        )
        try:
            with urlopen(
                Request(
                    endpoint,
                    headers={
                        "User-Agent": "MiningAnalytics/1.0",
                        "Cache-Control": "no-cache",
                    },
                ),
                timeout=25,
            ) as response:
                raw = response.read(2_000_001)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ValueError(
                "Could not read the spreadsheet. Check its public sharing settings and try again."
            ) from exc
        if len(raw) > 2_000_000:
            raise ValueError("Spreadsheet export is too large.")
        source = "Google Sheets"
        link = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
    text = raw.decode("utf-8-sig")
    if "<html" in text[:500].lower() or "<!doctype" in text[:500].lower():
        raise ValueError(
            "Google returned a web page instead of data. Enable access for anyone with the link."
        )
    data = parse_csv(text)
    canonical = data.to_csv(index=False, date_format="%Y-%m-%d")
    metadata = {
        "label": source,
        "url": link,
        "loaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fingerprint": hashlib.sha256(canonical.encode()).hexdigest()[:12],
        "days": len(data),
        "mines": len(data.columns) - 1,
        "demo": demo,
    }
    return data, metadata
