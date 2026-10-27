"""Statistics and outlier detection for daily mine production."""

from __future__ import annotations
from dataclasses import dataclass, asdict
import math
import numpy as np
import pandas as pd
from scipy.stats import t


@dataclass(frozen=True)
class Settings:
    iqr_k: float = 1.5
    z_threshold: float = 3.0
    ma_window: int = 7
    ma_percent: float = 40.0
    grubbs_alpha: float = 0.05
    degree: int = 1
    chart_type: str = "line"
    method: str = "any"

    @classmethod
    def parse(cls, values=None):
        values = values or {}
        if not isinstance(values, dict):
            raise ValueError("Analysis settings must be an object.")
        s = cls(
            float(values.get("iqr_k", 1.5)),
            float(values.get("z_threshold", 3)),
            int(values.get("ma_window", 7)),
            float(values.get("ma_percent", 40)),
            float(values.get("grubbs_alpha", 0.05)),
            int(values.get("degree", 1)),
            values.get("chart_type", "line"),
            values.get("method", "any"),
        )
        if not all(
            math.isfinite(v)
            for v in [s.iqr_k, s.z_threshold, s.ma_percent, s.grubbs_alpha]
        ):
            raise ValueError("Settings must contain finite numbers.")
        if not (
            0 <= s.iqr_k <= 10
            and 0 < s.z_threshold <= 10
            and 2 <= s.ma_window <= 60
            and 0 < s.ma_percent <= 1000
            and 0 < s.grubbs_alpha < 1
            and 1 <= s.degree <= 4
        ):
            raise ValueError("An analysis parameter is outside its allowed range.")
        if s.chart_type not in {"line", "bar", "stacked"} or s.method not in {
            "any",
            "iqr",
            "zscore",
            "moving_average",
            "grubbs",
        }:
            raise ValueError("Unknown chart type or outlier method.")
        return s


def grubbs(values, alpha):
    """Classic two-sided test for one most extreme observation."""
    y = np.asarray(values, dtype=float)
    n = len(y)
    if n < 3 or np.std(y, ddof=1) <= 1e-12:
        return {
            "index": None,
            "statistic": None,
            "critical": None,
            "significant": False,
        }
    index = int(np.argmax(np.abs(y - y.mean())))
    statistic = float(abs(y[index] - y.mean()) / np.std(y, ddof=1))
    quantile = float(t.isf(alpha / (2 * n), n - 2))
    critical = float(
        (n - 1) / np.sqrt(n) * np.sqrt(quantile**2 / (n - 2 + quantile**2))
    )
    return {
        "index": index if statistic > critical else None,
        "statistic": statistic,
        "critical": critical,
        "significant": statistic > critical,
    }


def analyze(frame, settings=None, metadata=None):
    s = settings if isinstance(settings, Settings) else Settings.parse(settings)
    mines = [c for c in frame if c != "Date" and c != "Total"]
    data = frame.copy()
    data["Total"] = data[mines].sum(axis=1)
    dates = data["Date"].dt.strftime("%Y-%m-%d").tolist()
    x = np.linspace(-1, 1, len(data))
    result = {
        "dates": dates,
        "mines": mines,
        "settings": asdict(s),
        "source": metadata or {},
        "series": {},
        "statistics": [],
        "anomalies": [],
    }
    for name in [*mines, "Total"]:
        y = data[name].to_numpy(dtype=float)
        if len(y) < s.degree + 1:
            raise ValueError(
                f"Trend degree {s.degree} requires at least {s.degree+1} days."
            )
        q1, q3 = np.quantile(y, [0.25, 0.75], method="linear")
        mean = float(y.mean())
        std = float(y.std(ddof=1)) if len(y) > 1 else 0.0
        iqr = float(q3 - q1)
        lower = float(q1 - s.iqr_k * iqr)
        upper = float(q3 + s.iqr_k * iqr)
        z = (y - mean) / std if std > 1e-12 else np.zeros(len(y))
        # The current observation is excluded from its trailing baseline.
        ma = (
            pd.Series(y)
            .shift(1)
            .rolling(s.ma_window, min_periods=s.ma_window)
            .mean()
            .to_numpy()
        )
        ma_flags = np.isfinite(ma) & (np.abs(y - ma) > s.ma_percent / 100 * np.abs(ma))
        g = grubbs(y, s.grubbs_alpha)
        flags = {
            "iqr": (y < lower) | (y > upper),
            "zscore": np.abs(z) > s.z_threshold,
            "moving_average": ma_flags,
            "grubbs": (
                np.arange(len(y)) == g["index"]
                if g["index"] is not None
                else np.zeros(len(y), dtype=bool)
            ),
        }
        trend = np.polynomial.polynomial.polyval(
            x, np.polynomial.polynomial.polyfit(x, y, s.degree)
        )
        selected = (
            np.logical_or.reduce(list(flags.values()))
            if s.method == "any"
            else flags[s.method]
        )
        count_by_method = {k: int(v.sum()) for k, v in flags.items()}
        row = {
            "name": name,
            "days": len(y),
            "mean": mean,
            "std": std,
            "median": float(np.median(y)),
            "iqr": iqr,
            "q1": float(q1),
            "q3": float(q3),
            "sum": float(y.sum()),
            "anomalies": int(selected.sum()),
            "method_counts": count_by_method,
        }
        result["statistics"].append(row)
        result["series"][name] = {
            "values": y.tolist(),
            "trend": trend.tolist(),
            "moving_average": [float(v) if np.isfinite(v) else None for v in ma],
            "flags": {k: v.tolist() for k, v in flags.items()},
            "selected": selected.tolist(),
            "iqr_bounds": [lower, upper],
            "grubbs": g,
        }
        for i in np.flatnonzero(selected):
            baseline = float(ma[i]) if np.isfinite(ma[i]) else mean
            methods = [k for k, v in flags.items() if v[i]]
            change = (
                None
                if abs(baseline) < 1e-12
                else float(100 * (y[i] - baseline) / abs(baseline))
            )
            result["anomalies"].append(
                {
                    "series": name,
                    "index": int(i),
                    "date": dates[i],
                    "value": float(y[i]),
                    "direction": "Spike" if y[i] >= baseline else "Drop",
                    "baseline": baseline,
                    "baseline_type": (
                        f"Previous {s.ma_window} days"
                        if np.isfinite(ma[i])
                        else "Series mean"
                    ),
                    "change_percent": change,
                    "zscore": float(z[i]),
                    "methods": methods,
                }
            )
    result["anomalies"].sort(key=lambda a: (a["date"], a["series"]))
    return result
