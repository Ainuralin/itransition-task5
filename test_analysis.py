from io import BytesIO
import numpy as np
import pandas as pd
import pytest
from pypdf import PdfReader
from analysis import analyze, grubbs, Settings
from sources import load_source, parse_csv
from app import app


def frame(values):
    return pd.DataFrame(
        {"Date": pd.date_range("2026-01-01", periods=len(values)), "Mine A": values}
    )


def test_constant_series_has_no_false_flags():
    result = analyze(frame([20] * 15))
    assert result["statistics"][0]["std"] == 0
    assert result["statistics"][0]["iqr"] == 0
    assert result["anomalies"] == []
    assert np.allclose(result["series"]["Total"]["trend"], 20)


def test_quartiles_sample_deviation_and_total():
    data = frame([1, 2, 3, 4, 5])
    data["Mine B"] = [2, 4, 6, 8, 10]
    result = analyze(data)
    a, b, total = result["statistics"]
    assert a["mean"] == a["median"] == 3
    assert a["std"] == pytest.approx(np.sqrt(2.5))
    assert a["q1"] == 2 and a["q3"] == 4 and a["iqr"] == 2
    assert total["mean"] == 9
    assert total["sum"] == a["sum"] + b["sum"]


def test_grubbs_nist_uranium_example():
    # NIST Engineering Statistics Handbook, section 1.3.5.17.1.
    values = [199.31, 199.53, 200.19, 200.82, 201.92, 201.95, 202.18, 245.57]
    result = grubbs(values, 0.05)
    assert result["index"] == 7
    assert result["statistic"] == pytest.approx(2.4687, abs=0.001)
    assert result["critical"] == pytest.approx(2.1266, abs=0.001)
    assert grubbs([1] * 8, 0.05)["index"] is None


def test_moving_average_excludes_current_and_handles_zero():
    result = analyze(frame([0] * 7 + [100] + [0] * 4), {"method": "moving_average"})
    series = result["series"]["Mine A"]
    assert series["moving_average"][:7] == [None] * 7
    assert series["moving_average"][7] == 0
    assert series["selected"][7]
    assert series["moving_average"][8] == pytest.approx(100 / 7)
    assert result["anomalies"][0]["change_percent"] is None


def test_degree_four_recovers_polynomial():
    x = np.arange(12, dtype=float)
    y = 50 + 0.02 * x**4 - 0.2 * x**2
    result = analyze(frame(y), {"degree": 4})
    assert np.allclose(result["series"]["Mine A"]["trend"], y)


@pytest.mark.parametrize(
    "settings",
    [
        {"degree": 5},
        {"ma_window": 1},
        {"grubbs_alpha": 0},
        {"z_threshold": float("nan")},
        {"method": "missing"},
    ],
)
def test_invalid_parameters(settings):
    with pytest.raises(ValueError):
        Settings.parse(settings)


def test_workbook_export_and_csv_validation():
    data, metadata = load_source(demo=True)
    assert len(data) == 90 and metadata["mines"] == 3
    assert metadata["demo"] is True
    text = "Date,A,Total\n" + "\n".join(f"2026-01-0{i},{i},{i}" for i in range(1, 6))
    assert parse_csv(text)["A"].sum() == 15
    for broken in [
        text.replace(",5,5", ",5,6"),
        text.replace("2026-01-03", "2026-01-02"),
        text.replace(",3,3", ",-3,-3"),
        text.replace("Date,A,Total", "Date,A,A"),
    ]:
        with pytest.raises(ValueError):
            parse_csv(broken)
    with pytest.raises(ValueError):
        load_source("https://example.com/anything")


def test_snapshot_analysis_and_pdf_match():
    client = app.test_client()
    response = client.post("/api/load", json={"demo": True})
    assert response.status_code == 200
    identity = response.json["snapshot_id"]
    payload = {
        "snapshot_id": identity,
        "settings": {"method": "grubbs", "degree": 4, "chart_type": "stacked"},
    }
    result = client.post("/api/analyze", json=payload)
    assert result.status_code == 200
    report = client.post("/api/report", json=payload)
    assert report.status_code == 200 and report.mimetype == "application/pdf"
    pages = PdfReader(BytesIO(report.data)).pages
    text = "\n".join(page.extract_text() for page in pages)
    assert result.json["source"]["fingerprint"] in text
    assert "Daily statistics" in text and "Grubbs" in text
    assert all(row["name"] in text for row in result.json["statistics"])
    assert (
        client.post("/api/analyze", json={"snapshot_id": "missing"}).status_code == 400
    )
    assert client.post("/api/load", json={"demo": "true"}).status_code == 400
