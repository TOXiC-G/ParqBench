"""
Data Profiler Widget for Parquet Editor.
Generates per-column distribution summaries (numeric histograms, categorical top-10,
datetime spans) using only pandas/numpy — rendered as styled text and ASCII-art bars.
"""
from __future__ import annotations

from typing import Optional
import pandas as pd
import numpy as np
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QComboBox, QSizePolicy, QProgressBar,
)
from PySide6.QtGui import QFont


# Max bars in ASCII histogram
_HIST_BARS = 10
_BAR_WIDTH = 20  # max chars per bar


def _ascii_bar(fraction: float, width: int = _BAR_WIDTH) -> str:
    filled = int(round(fraction * width))
    return "█" * filled + "░" * (width - filled)


class _ProfileWorker(QObject):
    finished = Signal(dict)

    def __init__(self, df: pd.DataFrame, col_name: str):
        super().__init__()
        self._df = df
        self._col = col_name

    def run(self):
        result = _compute_profile(self._df, self._col)
        self.finished.emit(result)


def _compute_profile(df: pd.DataFrame, col_name: str) -> dict:
    series = df[col_name]
    total = len(series)
    null_count = int(series.isna().sum())
    null_pct = null_count / total * 100 if total else 0
    unique_count = int(series.nunique(dropna=True))
    base = {
        "col_name": col_name,
        "dtype": str(series.dtype),
        "total": total,
        "null_count": null_count,
        "null_pct": null_pct,
        "unique_count": unique_count,
    }

    non_null = series.dropna()

    if pd.api.types.is_bool_dtype(series.dtype):
        base["kind"] = "bool"
        vc = series.value_counts(dropna=False)
        base["value_counts"] = [(str(k), int(v)) for k, v in vc.items()]

    elif pd.api.types.is_numeric_dtype(series.dtype):
        base["kind"] = "numeric"
        if not non_null.empty:
            arr = non_null.astype(float)
            base["min"] = float(arr.min())
            base["max"] = float(arr.max())
            base["mean"] = float(arr.mean())
            base["median"] = float(arr.median())
            base["std"] = float(arr.std())
            base["p25"] = float(arr.quantile(0.25))
            base["p75"] = float(arr.quantile(0.75))
            # Histogram
            counts, edges = np.histogram(arr, bins=_HIST_BARS)
            base["hist_counts"] = counts.tolist()
            base["hist_edges"] = edges.tolist()

    elif pd.api.types.is_datetime64_any_dtype(series.dtype):
        base["kind"] = "datetime"
        if not non_null.empty:
            base["min_dt"] = str(non_null.min())
            base["max_dt"] = str(non_null.max())
            span = non_null.max() - non_null.min()
            base["span_days"] = span.days
            # Frequency by year
            freq = non_null.dt.year.value_counts().sort_index()
            base["year_counts"] = [(int(k), int(v)) for k, v in freq.items()]

    else:
        # Categorical / string
        base["kind"] = "categorical"
        vc = series.value_counts(dropna=True).head(10)
        base["top_values"] = [(str(k), int(v)) for k, v in vc.items()]
        if len(vc):
            base["top_value"] = str(vc.index[0])
            base["top_count"] = int(vc.iloc[0])

    return base


class DataProfilerWidget(QWidget):
    """Side panel showing statistical profile for each column of the loaded dataset."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: Optional[pd.DataFrame] = None
        self._worker: Optional[_ProfileWorker] = None
        self._thread: Optional[QThread] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setStyleSheet("background: #18181f; border-bottom: 1px solid #2d2d3a;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 6, 10, 6)
        lbl = QLabel("📊 Data Profiler")
        lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #c0d0ff;")
        h_layout.addWidget(lbl)
        h_layout.addStretch(1)
        self.btn_profile_all = QPushButton("Profile All Columns")
        self.btn_profile_all.clicked.connect(self._profile_all)
        h_layout.addWidget(self.btn_profile_all)
        layout.addWidget(header)

        # Column selector
        sel_bar = QFrame()
        sel_bar.setStyleSheet("background: #1e1e28; padding: 4px;")
        sel_layout = QHBoxLayout(sel_bar)
        sel_layout.setContentsMargins(8, 4, 8, 4)
        sel_layout.addWidget(QLabel("Column:"))
        self.cmb_col = QComboBox()
        self.cmb_col.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sel_layout.addWidget(self.cmb_col)
        btn_go = QPushButton("▶ Profile")
        btn_go.clicked.connect(self._profile_selected)
        sel_layout.addWidget(btn_go)
        layout.addWidget(sel_bar)

        # Progress bar (hidden when idle)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setVisible(False)
        self.progress.setMaximumHeight(4)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        # Scroll area with profile content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.content_layout.setSpacing(8)
        self.content_layout.addStretch(1)

        scroll.setWidget(self.content)
        layout.addWidget(scroll, 1)

    def set_dataframe(self, df: Optional[pd.DataFrame]):
        self._df = df
        self.cmb_col.clear()
        # Clear profile content
        self._clear_cards()
        if df is not None:
            for c in df.columns:
                self.cmb_col.addItem(str(c))

    def _clear_cards(self):
        while self.content_layout.count() > 1:
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _profile_selected(self):
        if self._df is None:
            return
        col = self.cmb_col.currentText()
        if col and col in self._df.columns:
            self._clear_cards()
            self._run_worker(col)

    def _profile_all(self):
        if self._df is None:
            return
        self._clear_cards()
        # Profile all synchronously in order (fast enough for display)
        for c in self._df.columns:
            profile = _compute_profile(self._df, str(c))
            card = self._make_card(profile)
            self.content_layout.insertWidget(self.content_layout.count() - 1, card)

    def _run_worker(self, col_name: str):
        self.progress.setVisible(True)
        self._thread = QThread()
        self._worker = _ProfileWorker(self._df, col_name)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_profile_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _on_profile_done(self, profile: dict):
        self.progress.setVisible(False)
        card = self._make_card(profile)
        self.content_layout.insertWidget(self.content_layout.count() - 1, card)

    def _make_card(self, p: dict) -> QFrame:
        """Build a profile card widget from a profile dict."""
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #22223a; border: 1px solid #3a3a58; border-radius: 6px; }"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(4)

        mono = QFont("Consolas", 10)
        mono.setStyleHint(QFont.StyleHint.Monospace)

        # Title
        title = QLabel(f"<b>{p['col_name']}</b>  <span style='color:#778899;font-size:10px;'>({p['dtype']})</span>")
        title.setStyleSheet("font-size: 13px; color: #e0e0ff;")
        cl.addWidget(title)

        # Common stats
        info = (
            f"Rows: {p['total']:,}   |   "
            f"Nulls: {p['null_count']:,} ({p['null_pct']:.1f}%)   |   "
            f"Unique: {p['unique_count']:,}"
        )
        info_lbl = QLabel(info)
        info_lbl.setStyleSheet("color: #aaaacc; font-size: 11px;")
        cl.addWidget(info_lbl)

        kind = p.get("kind", "")
        txt = QLabel()
        txt.setFont(mono)
        txt.setStyleSheet("color: #d0e8d0; font-size: 10px; padding-top:4px;")
        txt.setWordWrap(False)
        txt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        lines = []
        if kind == "numeric":
            lines.append(f"Min: {p.get('min', 'N/A'):g}   Max: {p.get('max', 'N/A'):g}   Mean: {p.get('mean', 'N/A'):g}")
            lines.append(f"Median: {p.get('median', 'N/A'):g}   Std: {p.get('std', 'N/A'):g}   P25: {p.get('p25', 'N/A'):g}   P75: {p.get('p75', 'N/A'):g}")
            # ASCII histogram
            counts = p.get("hist_counts", [])
            edges = p.get("hist_edges", [])
            if counts:
                max_c = max(counts) if counts else 1
                lines.append("")
                lines.append("Distribution:")
                for i, c in enumerate(counts):
                    frac = c / max_c if max_c else 0
                    lo = f"{edges[i]:g}"
                    hi = f"{edges[i+1]:g}"
                    bar = _ascii_bar(frac)
                    lines.append(f"  {lo:>8} – {hi:<8} {bar} {c:,}")

        elif kind == "categorical":
            top = p.get("top_values", [])
            if top:
                max_c = top[0][1] if top else 1
                lines.append("Top 10 values:")
                for val, cnt in top:
                    frac = cnt / max_c if max_c else 0
                    bar = _ascii_bar(frac, width=15)
                    pct = cnt / p["total"] * 100 if p["total"] else 0
                    lines.append(f"  {str(val)[:20]:<20} {bar} {cnt:,} ({pct:.1f}%)")

        elif kind == "datetime":
            lines.append(f"Earliest: {p.get('min_dt', 'N/A')}")
            lines.append(f"Latest:   {p.get('max_dt', 'N/A')}")
            lines.append(f"Span:     {p.get('span_days', 0):,} days")
            year_counts = p.get("year_counts", [])
            if year_counts:
                max_c = max(v for _, v in year_counts) if year_counts else 1
                lines.append("")
                lines.append("By Year:")
                for yr, cnt in year_counts[-15:]:  # last 15 years
                    frac = cnt / max_c if max_c else 0
                    bar = _ascii_bar(frac, width=15)
                    lines.append(f"  {yr}  {bar} {cnt:,}")

        elif kind == "bool":
            vc = p.get("value_counts", [])
            for val, cnt in vc:
                pct = cnt / p["total"] * 100 if p["total"] else 0
                bar = _ascii_bar(pct / 100, width=15)
                lines.append(f"  {val:<10} {bar} {cnt:,} ({pct:.1f}%)")

        txt.setText("\n".join(lines))
        cl.addWidget(txt)
        return card
