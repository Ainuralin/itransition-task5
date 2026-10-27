"use strict";
const $ = (s) => document.querySelector(s),
  fmt = (v, d = 2) =>
    Number(v).toLocaleString("en-US", {
      minimumFractionDigits: d,
      maximumFractionDigits: d,
    });
const esc = (v) =>
  String(v).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const labels = {
  iqr: "IQR",
  zscore: "Z-score",
  moving_average: "Moving average",
  grubbs: "Grubbs",
};
const colors = [
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
];
let result = null,
  snapshot = null,
  backend = false,
  page = 0;
const ids = [
  "iqr_k",
  "z_threshold",
  "ma_window",
  "ma_percent",
  "grubbs_alpha",
  "degree",
  "chart_type",
  "method",
];
function settings() {
  return Object.fromEntries(
    ids.map((id) => [
      id,
      ["chart_type", "method"].includes(id)
        ? $("#" + id).value
        : Number($("#" + id).value),
    ]),
  );
}
function error(text) {
  $("#error").hidden = !text;
  $("#error").textContent = text || "";
}
function busy(value) {
  for (const id of ["refresh", "example", "apply", "report"])
    $("#" + id).disabled =
      value ||
      (!backend && ["apply", "report", "refresh", "example"].includes(id));
}
async function api(path, payload) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let data;
  try {
    data = await r.json();
  } catch {
    throw Error("The server returned an unreadable response.");
  }
  if (!r.ok) throw Error(data.error || "Request failed");
  return data;
}
function table(headers, rows, classes = []) {
  return `<table><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((row, i) => `<tr class="${classes[i] || ""}">${row.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}
function draw() {
  if (!result) return;
  const chosen = $("#series").value;
  const kind = result.settings.chart_type;
  $("#series").disabled = kind === "stacked";
  const names = chosen === "all" ? result.mines : [chosen];
  const traces = [];
  if (kind === "stacked") {
    for (const [i, name] of result.mines.entries())
      traces.push({
        x: result.dates,
        y: result.series[name].values,
        name,
        mode: "lines",
        line: { width: 0.8, color: colors[i % colors.length] },
        stackgroup: "mines",
        type: "scatter",
      });
    const total = result.series.Total;
    traces.push({
      x: result.dates,
      y: total.trend,
      name: `Total trend · degree ${result.settings.degree}`,
      type: "scatter",
      mode: "lines",
      line: { color: "#b68634", width: 2, dash: "dash" },
    });
    const points = total.selected
      .map((v, i) => (v ? i : -1))
      .filter((i) => i >= 0);
    traces.push({
      x: points.map((i) => result.dates[i]),
      y: points.map((i) => total.values[i]),
      name: "Total anomalies",
      mode: "markers",
      type: "scatter",
      marker: { size: 8, color: "#B94D4D", line: { color: "white", width: 1 } },
    });
    $("#chart-title").textContent = "Mine contributions and total trend";
  } else {
    for (const [j, name] of names.entries()) {
      const s = result.series[name],
        color = colors[j % colors.length];
      traces.push({
        x: result.dates,
        y: s.values,
        name,
        type: kind === "bar" ? "bar" : "scatter",
        mode: "lines",
        line: { color, width: 1.5 },
        marker: { color },
        opacity: kind === "bar" ? 0.8 : 1,
      });
      traces.push({
        x: result.dates,
        y: s.trend,
        name: name + " trend",
        type: "scatter",
        mode: "lines",
        line: {
          color: chosen === "all" ? color : "#D49A3B",
          width: 1.7,
          dash: "dash",
        },
      });
      const points = s.selected
        .map((v, i) => (v ? i : -1))
        .filter((i) => i >= 0);
      traces.push({
        x: points.map((i) => result.dates[i]),
        y: points.map((i) => s.values[i]),
        name: name + " anomalies",
        type: "scatter",
        mode: "markers",
        marker: {
          color: "#B94D4D",
          size: 8,
          line: { color: "#fff", width: 1 },
        },
      });
    }
    $("#chart-title").textContent =
      chosen === "all" ? "Production by mine" : chosen + " · daily output";
  }
  Plotly.react(
    "chart",
    traces,
    {
      margin: { l: 55, r: 15, t: 12, b: 46 },
      paper_bgcolor: "transparent",
      plot_bgcolor: "white",
      font: { family: "Arial, sans-serif", size: 10, color: "#71818a" },
      showlegend: chosen === "all" || kind === "stacked",
      legend: { orientation: "h", y: -0.25, font: { size: 9 } },
      hovermode: "x unified",
      xaxis: { type: "date", nticks: 6, gridcolor: "#eff2f3", zeroline: false },
      yaxis: {
        title: { text: "Tonnes / day", font: { size: 10 } },
        gridcolor: "#e9eef0",
        zeroline: false,
        rangemode: kind === "line" ? "normal" : "tozero",
      },
      barmode: "group",
    },
    {
      responsive: true,
      displaylogo: false,
      modeBarButtonsToRemove: ["select2d", "lasso2d"],
    },
  );
}
function render() {
  page = 0;
  const total = result.statistics.find((r) => r.name === "Total");
  const cards = [
    ["Total production", fmt(total.sum), "tonnes across all mines"],
    ["Mean daily output", fmt(total.mean), "tonnes / day · total"],
    [
      "Flagged total days",
      fmt(total.anomalies, 0),
      "selected detection method",
    ],
    [
      "Monitoring period",
      fmt(result.dates.length, 0),
      `${result.mines.length} mines · daily observations`,
    ],
  ];
  $("#metrics").innerHTML = cards
    .map(
      ([label, value, note]) =>
        `<article class="metric"><div class="label">${label}</div><div class="value">${value}</div><small>${esc(note)}</small></article>`,
    )
    .join("");
  const selected = $("#series").value;
  $("#series").innerHTML = ["Total", "all", ...result.mines]
    .map(
      (n) =>
        `<option value="${esc(n)}">${n === "all" ? "All mines" : esc(n)}</option>`,
    )
    .join("");
  if (["Total", "all", ...result.mines].includes(selected))
    $("#series").value = selected;
  $("#anomaly-series").innerHTML =
    '<option value="all">All series</option>' +
    [...result.mines, "Total"]
      .map((n) => `<option>${esc(n)}</option>`)
      .join("");
  $("#statistics").innerHTML = table(
    ["Series", "Mean", "Std. dev.", "Median", "IQR", "Flagged"],
    result.statistics.map((r) => [
      esc(r.name),
      fmt(r.mean),
      fmt(r.std),
      fmt(r.median),
      fmt(r.iqr),
      String(r.anomalies),
    ]),
    result.statistics.map((r) => (r.name === "Total" ? "total" : "")),
  );
  const src = result.source;
  $("#source-status").textContent =
    `${src.demo ? "EXAMPLE DATA" : "GOOGLE SHEETS"} · ${result.dates[0]} — ${result.dates.at(-1)} · loaded ${src.loaded_at || "preview"} · snapshot ${src.fingerprint || "example"}`;
  $("#notice").hidden = !src.demo;
  $("#notice").textContent =
    "Example dataset from the generator workbook. Connect your Google Sheet to analyze current parameter values.";
  $("#snapshot-label").textContent =
    "Snapshot " + (src.fingerprint || "example");
  $("#anomaly-count").textContent = result.anomalies.length;
  renderAnomalies();
  draw();
  busy(false);
}
function renderAnomalies() {
  const filter = $("#anomaly-series").value;
  const rows = result.anomalies.filter(
    (a) => filter === "all" || a.series === filter,
  );
  const pages = Math.max(1, Math.ceil(rows.length / 15));
  page = Math.max(0, Math.min(page, pages - 1));
  const shown = rows.slice(page * 15, page * 15 + 15);
  $("#anomalies").innerHTML = shown.length
    ? table(
        [
          "Date",
          "Series",
          "Type",
          "Output (t)",
          "Baseline (t)",
          "Difference",
          "Methods",
        ],
        shown.map((a) => [
          esc(a.date),
          esc(a.series),
          `<span class="tag ${a.direction === "Drop" ? "drop" : ""}">${a.direction}</span>`,
          fmt(a.value),
          fmt(a.baseline),
          a.change_percent === null
            ? "Zero baseline"
            : fmt(a.change_percent, 1) + "%",
          esc(a.methods.map((k) => labels[k]).join(", ")),
        ]),
      )
    : '<p class="small-note">No observations were flagged for this selection.</p>';
  $("#page-label").textContent =
    `${rows.length} observations · page ${page + 1} of ${pages}`;
  $("#prev").disabled = page === 0;
  $("#next").disabled = page >= pages - 1;
}
async function load(demo) {
  busy(true);
  error("");
  try {
    const loaded = await api("/api/load", {
      demo,
      sheet_url: $("#sheet-url").value,
    });
    snapshot = loaded.snapshot_id;
    result = await api("/api/analyze", {
      snapshot_id: snapshot,
      settings: settings(),
    });
    render();
  } catch (e) {
    error(e.message);
    busy(false);
  }
}
$("#source-form").addEventListener("submit", (e) => {
  e.preventDefault();
  load(false);
});
$("#example").addEventListener("click", () => {
  if (backend) load(true);
});
$("#settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!backend || !snapshot) return;
  busy(true);
  error("");
  try {
    result = await api("/api/analyze", {
      snapshot_id: snapshot,
      settings: settings(),
    });
    render();
  } catch (err) {
    error(err.message);
    busy(false);
  }
});
$("#chart_type").addEventListener("change", () =>
  $("#settings-form").requestSubmit(),
);
$("#series").addEventListener("change", draw);
$("#anomaly-series").addEventListener("change", () => {
  page = 0;
  renderAnomalies();
});
$("#prev").addEventListener("click", () => {
  page--;
  renderAnomalies();
});
$("#next").addEventListener("click", () => {
  page++;
  renderAnomalies();
});
$("#report").addEventListener("click", async () => {
  if (!snapshot || !backend) return;
  busy(true);
  error("");
  try {
    const r = await fetch("/api/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        snapshot_id: snapshot,
        settings: result.settings,
      }),
    });
    if (!r.ok) {
      const body = await r.json();
      throw Error(body.error || "Report generation failed");
    }
    const blob = await r.blob(),
      url = URL.createObjectURL(blob),
      link = document.createElement("a");
    link.href = url;
    link.download = `mining_report_${result.source.fingerprint}.pdf`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    error(e.message);
  } finally {
    busy(false);
  }
});
(async () => {
  try {
    const r = await fetch("/api/config");
    if (!r.ok) throw Error();
    const config = await r.json();
    backend = true;
    $("#sheet-url").value = config.sheet_url || "";
    await load(!config.sheet_url);
  } catch {
    backend = false;
    try {
      const r = await fetch("preview.json");
      result = await r.json();
      render();
      $("#notice").hidden = false;
      $("#notice").textContent =
        "Static preview with workbook example data. Source refresh, analysis settings and PDF export run in the Python application.";
      for (const el of document.querySelectorAll(
        "#settings-form input,#settings-form select,#chart_type,#sheet-url,#example",
      ))
        el.disabled = true;
      busy(false);
    } catch {
      error("Could not load the dashboard data.");
    }
  }
})();
