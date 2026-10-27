# Mining Analytics

My solution for Itransition Data Engineering task 5. The data source is a spreadsheet of daily production at Weyland-Yutani mines. The web application reads its Output tab, calculates statistics, marks unusual observations and exports a PDF report.

## Run locally

Python 3.10 or later is required.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. The application starts with an example exported from the generator. Paste the shared Google Sheets link and click **Connect / refresh** to read current spreadsheet values. No API key is needed.

## Generator

`generator/mining_generator.xlsx` is the formula workbook used to create the Google Sheets generator. Import it as a native Google spreadsheet, keep the four tab names, and allow anyone with the link to edit. The native spreadsheet is the data source for the submitted application; the example CSV is only for trying the dashboard before connecting it.

The amber cells on **Controls** change the start date, number of days (5–366), number of mines (1–10), mine names and capacity multipliers, distribution, correlation, daily growth, weekday factors, seed, and four events. Mine names must be unique and must not be Date or Total. Normal and Uniform have separate parameter cells. Each event has a start date, duration, peak multiplier and probability of affecting each mine.

**Random** calculates a seeded Park–Miller sequence and converts its values into normal innovations with Box–Muller or uniform innovations. **Smooth** applies a first-order autoregressive formula around the distribution mean. **Output** combines the smoothed values with capacity, weekday factors, compound daily growth and event multipliers, then rounds to two decimal places and clips negative production to zero. All generation happens in cell formulas; there are no scripts. Changing the seed produces another reproducible scenario.

Events have a Gaussian-shaped rise or fall within their configured duration. The probability is drawn once for each event and mine, so an event does not switch on and off randomly each day. A multiplier below 1 reduces production; above 1 increases it. The distribution settings describe the innovations before smoothing and other effects, rather than the final output distribution.

The Output chart refers to formula-generated date labels and mine columns. Inactive mine columns and dates are blank. Keep the Output table headers and date format (YYYY-MM-DD) when editing the workbook.

## Analysis

The dashboard provides mean, sample standard deviation, median and interquartile range for every mine and for Total. Total is recalculated from the mine columns and checked against the spreadsheet. Quartiles use linear interpolation.

- **IQR:** values outside Q1 − k × IQR and Q3 + k × IQR.
- **Z-score:** absolute distance from the series mean divided by sample standard deviation, above the chosen threshold.
- **Moving average:** percentage distance from the previous full window of days, excluding the current observation. A positive value after a zero baseline is flagged; the percentage itself is undefined.
- **Grubbs:** the classic two-sided test for one most extreme observation, using the selected significance level. Constant series have no Grubbs flag.

Grubbs assumes approximately normal, independent data. The generator deliberately includes correlation, weekday effects and trends, so its flags are exploratory. The application does not remove observations or repeatedly apply Grubbs after removing points. The formula follows the [NIST Engineering Statistics Handbook](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h1.htm).

Line, grouped bar and stacked area views are available. The stacked view shows mine contributions together with the Total trend and Total flags. Polynomial trends support degrees 1–4. All four detectors are calculated; the method selector controls which flags are highlighted and included in anomaly details.

## PDF report

The report includes source details, the loaded data fingerprint, settings, all statistics, a chart for each mine and Total, detector counts, and an individual subsection for every highlighted anomaly. Analysis and PDF export use the same in-memory snapshot. A spreadsheet edit becomes visible only after refreshing the source. Snapshots expire after two hours or when the server restarts.

## Deploy on Render

Create a Python web service from this repository, or use `render.yaml`.

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --workers 1 --threads 2 --bind 0.0.0.0:$PORT --timeout 180`
- Environment variable `GOOGLE_SHEET_URL`: the native shared spreadsheet URL.

A single worker keeps analysis and PDF requests on the same snapshot store. The application also accepts a spreadsheet link directly in the dashboard. The spreadsheet needs public link access because the server reads the Output tab as CSV without signing in.

## Checks

```bash
python -m pytest -q
```

The checks cover statistics, a published Grubbs example, constant and zero-baseline series, polynomial fitting, CSV validation, and the load → analyze → PDF flow.
