"""Create a PDF from the same source snapshot and settings as the dashboard."""

from __future__ import annotations
from io import BytesIO
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xml.sax.saxutils import escape
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    PageBreak,
    KeepTogether,
)

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFontFamily(
    "DejaVu",
    normal="DejaVu",
    bold="DejaVu-Bold",
    italic="DejaVu",
    boldItalic="DejaVu-Bold",
)

PALETTE = [
    "#217C83",
    "#D49A3B",
    "#695D99",
    "#578658",
    "#C16A56",
    "#4A79A0",
    "#9F6B8C",
    "#688473",
    "#967646",
    "#64717E",
]
LABELS = {
    "iqr": "IQR",
    "zscore": "Z-score",
    "moving_average": "Moving average",
    "grubbs": "Grubbs' test",
}


def figure(result, name):
    y = np.asarray(result["series"][name]["values"])
    x = np.arange(len(y))
    series = result["series"][name]
    fig, ax = plt.subplots(figsize=(9, 3.1), layout="constrained")
    kind = result["settings"]["chart_type"]
    if kind == "bar":
        ax.bar(x, y, color="#217C83", width=0.8, alpha=0.75)
    elif kind == "stacked" and name == "Total":
        ax.stackplot(
            x,
            *[result["series"][m]["values"] for m in result["mines"]],
            labels=result["mines"],
            colors=PALETTE[: len(result["mines"])],
            alpha=0.75,
        )
        ax.legend(loc="upper left", fontsize=7, ncol=3, frameon=False)
    elif kind == "stacked":
        ax.fill_between(x, y, color="#217C83", alpha=0.35)
        ax.plot(x, y, color="#217C83", linewidth=1)
    else:
        ax.plot(x, y, color="#217C83", linewidth=1.3, label="Daily output")
    ax.plot(
        x,
        series["trend"],
        color="#CA8E2D",
        linestyle="--",
        linewidth=1.5,
        label=f"Trend, degree {result['settings']['degree']}",
    )
    flagged = np.flatnonzero(series["selected"])
    if len(flagged):
        ax.scatter(
            flagged,
            y[flagged],
            color="#B94D4D",
            edgecolors="white",
            s=35,
            zorder=5,
            label="Flagged output",
        )
    ticks = np.unique(np.linspace(0, len(y) - 1, min(6, len(y)), dtype=int))
    ax.set_xticks(ticks, [result["dates"][i] for i in ticks], fontsize=8)
    ax.set_ylabel("Tonnes / day", fontsize=9)
    ax.grid(axis="y", alpha=0.18)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    if kind != "stacked" or name != "Total":
        ax.legend(loc="upper right", fontsize=7, frameon=False)
    if kind in {"bar", "stacked"}:
        ax.set_ylim(bottom=0)
    image = BytesIO()
    fig.savefig(image, format="png", dpi=155)
    plt.close(fig)
    image.seek(0)
    return Image(image, width=180 * mm, height=62 * mm)


def make_report(result):
    stream = BytesIO()
    doc = SimpleDocTemplate(
        stream,
        pagesize=(210 * mm, 297 * mm),
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=18 * mm,
        bottomMargin=17 * mm,
        title="Mining output analysis",
        author="Ainur Ali",
    )
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = "DejaVu-Bold" if "Heading" in style.name else "DejaVu"
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            fontName="DejaVu-Bold",
            fontSize=23,
            leading=28,
            textColor=colors.HexColor("#213C4A"),
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallText",
            fontName="DejaVu",
            fontSize=8,
            leading=12,
            textColor=colors.HexColor("#526773"),
            spaceAfter=8,
        )
    )
    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 14
    styles["Heading2"].fontSize = 13
    styles["Heading2"].textColor = colors.HexColor("#213C4A")
    styles["Heading2"].spaceBefore = 12
    styles["Heading3"].fontSize = 10
    styles["Heading3"].textColor = colors.HexColor("#213C4A")
    p = lambda text, style="BodyText": Paragraph(escape(str(text)), styles[style])
    source = result["source"]
    settings = result["settings"]
    story = [
        p("WEYLAND-YUTANI CORPORATION", "SmallText"),
        p("Mining output analysis", "ReportTitle"),
        p(
            f"{result['dates'][0]} to {result['dates'][-1]} | {len(result['dates'])} days | {len(result['mines'])} mines"
        ),
        Spacer(1, 5 * mm),
        p("Data source", "Heading2"),
        p(
            f"{source.get('label','Snapshot')} | Snapshot {source.get('fingerprint','-')} | Loaded {source.get('loaded_at','-')}",
            "SmallText",
        ),
    ]
    if source.get("url"):
        story.append(p(source["url"], "SmallText"))
    if source.get("demo"):
        story.append(
            p(
                "Example data exported from the workbook. This report is not linked to a live Google Sheet.",
                "SmallText",
            )
        )
    rows = [["Series", "Mean", "Std. dev.", "Median", "IQR", "Flagged"]]
    for r in result["statistics"]:
        rows.append(
            [
                p(r["name"], "SmallText"),
                *[f"{r[k]:,.2f}" for k in ["mean", "std", "median", "iqr"]],
                str(r["anomalies"]),
            ]
        )
    table = Table(
        rows,
        colWidths=[45 * mm, 27 * mm, 27 * mm, 27 * mm, 27 * mm, 27 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#213C4A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#213C4A")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#F2F6F6")],
                ),
            ]
        )
    )
    story.extend(
        [
            p("Daily statistics (tonnes)", "Heading2"),
            table,
            p(
                "Standard deviation uses the sample formula (n - 1). Quartiles use linear interpolation.",
                "SmallText",
            ),
            p("Analysis settings", "Heading2"),
            p(
                f"IQR multiplier: {settings['iqr_k']}; z-score threshold: {settings['z_threshold']}; moving average: previous {settings['ma_window']} days, {settings['ma_percent']}% threshold; Grubbs alpha: {settings['grubbs_alpha']}; polynomial degree: {settings['degree']}; chart: {settings['chart_type']}; highlighted method: {settings['method']}.",
                "SmallText",
            ),
            p(
                "Grubbs is a two-sided single-outlier test assuming approximately normal, independent observations. Trends, weekly patterns and correlation can violate that assumption; its flags are exploratory for this generated series. No observations are removed.",
                "SmallText",
            ),
            p(
                "Methods: IQR fences are Q1 - k*IQR and Q3 + k*IQR. Z-score is measured from the series mean. The moving-average baseline excludes the current day and starts after a full window. A positive value after a zero baseline is flagged.",
                "SmallText",
            ),
        ]
    )
    for row in result["statistics"]:
        name = row["name"]
        story.extend(
            [
                PageBreak(),
                p(name, "ReportTitle"),
                figure(result, name),
                Spacer(1, 3 * mm),
                p("Detection counts", "Heading2"),
                p(
                    ", ".join(
                        f"{LABELS[k]}: {v}" for k, v in row["method_counts"].items()
                    )
                ),
                p(
                    f"Total output: {row['sum']:,.2f} tonnes. Mean daily output: {row['mean']:,.2f} tonnes."
                ),
            ]
        )
        g = result["series"][name]["grubbs"]
        if g["statistic"] is not None:
            story.append(
                p(
                    f"Grubbs G = {g['statistic']:.4f}; critical value = {g['critical']:.4f}.",
                    "SmallText",
                )
            )
        anomalies = [a for a in result["anomalies"] if a["series"] == name]
        story.append(p(f"Anomaly details ({len(anomalies)})", "Heading2"))
        if not anomalies:
            story.append(p("No observations were flagged by the selected method."))
        for index, a in enumerate(anomalies, 1):
            delta = (
                "undefined (zero baseline)"
                if a["change_percent"] is None
                else f"{a['change_percent']:+.1f}%"
            )
            story.append(
                KeepTogether(
                    [
                        p(f"{index}. {a['date']} - {a['direction']}", "Heading3"),
                        p(
                            f"Observed: {a['value']:,.2f} t. Baseline ({a['baseline_type'].lower()}): {a['baseline']:,.2f} t. Difference: {delta}."
                        ),
                        p(
                            f"Flagged by: {', '.join(LABELS[m] for m in a['methods'])}. Z-score: {a['zscore']:.3f}.",
                            "SmallText",
                        ),
                    ]
                )
            )

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D5DFE1"))
        canvas.line(15 * mm, 13 * mm, 195 * mm, 13 * mm)
        canvas.setFont("DejaVu", 8)
        canvas.setFillColor(colors.HexColor("#657B83"))
        canvas.drawString(15 * mm, 9 * mm, "Mining Analytics | Ainur Ali")
        canvas.drawRightString(195 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    stream.seek(0)
    return stream
