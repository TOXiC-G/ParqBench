"""
Parquet Diff / Compare Tool for Parquet Editor.
Compares two DataFrames (base vs target) and produces a color-coded diff view
showing added, deleted, and modified rows, plus a schema diff summary.
"""
from __future__ import annotations

from typing import Optional, List
import os
import pandas as pd
import numpy as np
from PySide6.QtCore import Qt, Signal, QAbstractTableModel, QModelIndex
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSplitter, QTableView, QFileDialog, QMessageBox, QComboBox,
    QHeaderView, QAbstractItemView, QFrame, QTextEdit, QTabWidget,
    QWidget, QFormLayout, QCheckBox,
)
from PySide6.QtGui import QColor, QBrush
from PySide6.QtGui import QFont

from src.engine.parquet_handler import ParquetHandler


_COLOR_ADDED   = QColor(56, 142, 60, 120)    # Green tint – added rows
_COLOR_DELETED = QColor(211, 47, 47, 120)    # Red tint  – deleted rows
_COLOR_CHANGED = QColor(245, 127, 23, 120)   # Amber tint – changed cells
_COLOR_SAME    = QColor(0, 0, 0, 0)          # Transparent – unchanged


class DiffTableModel(QAbstractTableModel):
    """Read-only model showing the diff result with row-level color coding."""

    def __init__(self, df: pd.DataFrame, row_status: pd.Series, changed_cells: set, parent=None):
        """
        Args:
            df: The combined diff DataFrame.
            row_status: Series with same index, values: 'added'|'deleted'|'changed'|'same'.
            changed_cells: Set of (row_iloc, col_iloc) that have cell-level changes.
        """
        super().__init__(parent)
        self._df = df.reset_index(drop=True)
        self._row_status = row_status.reset_index(drop=True)
        self._changed_cells = changed_cells
        self._cols = [str(c) for c in df.columns]

    def rowCount(self, parent=QModelIndex()):
        return len(self._df)

    def columnCount(self, parent=QModelIndex()):
        return len(self._cols)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        if r >= len(self._df):
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            val = self._df.iat[r, c]
            if pd.isna(val):
                return "<null>"
            return str(val)

        elif role == Qt.ItemDataRole.BackgroundRole:
            status = self._row_status.iloc[r] if r < len(self._row_status) else "same"
            if status == "added":
                return QBrush(_COLOR_ADDED)
            elif status == "deleted":
                return QBrush(_COLOR_DELETED)
            elif status == "changed" and (r, c) in self._changed_cells:
                return QBrush(_COLOR_CHANGED)
            return None

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal and section < len(self._cols):
                return self._cols[section]
            elif orientation == Qt.Orientation.Vertical:
                return str(section + 1)
        return None

    def get_summary(self) -> dict:
        counts = self._row_status.value_counts().to_dict()
        return {
            "added":   counts.get("added", 0),
            "deleted": counts.get("deleted", 0),
            "changed": counts.get("changed", 0),
            "same":    counts.get("same", 0),
            "total":   len(self._df),
        }


def _diff_dataframes(
    base_df: pd.DataFrame,
    target_df: pd.DataFrame,
    key_col: Optional[str] = None,
) -> tuple[pd.DataFrame, pd.Series, set]:
    """
    Produces a combined diff DataFrame.
    Returns (combined_df, row_status_series, changed_cells_set).
    """
    if key_col and key_col in base_df.columns and key_col in target_df.columns:
        # Key-based merge diff
        merged = pd.merge(
            base_df, target_df, on=key_col, how="outer",
            suffixes=("__base", "__target"), indicator=True
        )
        statuses = []
        changed_cells = set()

        # Rebuild a clean unified df with base/target columns interleaved
        common_cols = [c for c in base_df.columns if c != key_col and c in target_df.columns]
        result_rows = []

        for i, row in merged.iterrows():
            ind = row["_merge"]
            rec = {key_col: row[key_col]}
            if ind == "left_only":
                status = "deleted"
                for c in common_cols:
                    rec[c] = row.get(f"{c}__base", np.nan)
            elif ind == "right_only":
                status = "added"
                for c in common_cols:
                    rec[c] = row.get(f"{c}__target", np.nan)
            else:
                # Both: check cell-level changes
                status = "same"
                for c_idx, c in enumerate(common_cols):
                    bval = row.get(f"{c}__base")
                    tval = row.get(f"{c}__target")
                    both_null = pd.isna(bval) and pd.isna(tval)
                    if not both_null and bval != tval:
                        status = "changed"
                        changed_cells.add((len(result_rows), c_idx + 1))  # +1 for key col
                    rec[c] = tval  # show target values
            statuses.append(status)
            result_rows.append(rec)

        result_df = pd.DataFrame(result_rows, columns=[key_col] + common_cols) if result_rows else pd.DataFrame(columns=[key_col] + common_cols)
        return result_df, pd.Series(statuses), changed_cells

    else:
        # Row-position based diff (pad shorter with NaN)
        n = max(len(base_df), len(target_df))
        base_pad = base_df.reindex(range(n))
        target_pad = target_df.reindex(range(n))

        common_cols = [c for c in base_df.columns if c in target_df.columns]
        if not common_cols:
            common_cols = list(base_df.columns)

        base_pad = base_pad.reset_index(drop=True)
        target_pad = target_pad.reset_index(drop=True)

        statuses = []
        changed_cells = set()
        result_rows = []

        for i in range(n):
            b_null = i >= len(base_df)
            t_null = i >= len(target_df)
            if b_null:
                status = "added"
                rec = {c: target_pad.at[i, c] if c in target_pad.columns else np.nan for c in common_cols}
            elif t_null:
                status = "deleted"
                rec = {c: base_pad.at[i, c] if c in base_pad.columns else np.nan for c in common_cols}
            else:
                status = "same"
                rec = {}
                for c_idx, c in enumerate(common_cols):
                    bval = base_pad.at[i, c] if c in base_pad.columns else np.nan
                    tval = target_pad.at[i, c] if c in target_pad.columns else np.nan
                    both_null = pd.isna(bval) and pd.isna(tval)
                    if not both_null and bval != tval:
                        status = "changed"
                        changed_cells.add((i, c_idx))
                    rec[c] = tval
            statuses.append(status)
            result_rows.append(rec)

        result_df = pd.DataFrame(result_rows, columns=common_cols) if result_rows else pd.DataFrame(columns=common_cols)
        return result_df, pd.Series(statuses), changed_cells


def _schema_diff_text(base_df: pd.DataFrame, target_df: pd.DataFrame) -> str:
    lines = ["=== Schema Diff ===\n"]
    base_cols = dict(zip(base_df.columns, base_df.dtypes))
    target_cols = dict(zip(target_df.columns, target_df.dtypes))

    all_cols = list(dict.fromkeys(list(base_cols) + list(target_cols)))
    for c in all_cols:
        in_base = c in base_cols
        in_target = c in target_cols
        if in_base and in_target:
            if str(base_cols[c]) != str(target_cols[c]):
                lines.append(f"  ~ {c}: {base_cols[c]} → {target_cols[c]}  (type changed)")
            else:
                lines.append(f"    {c}: {base_cols[c]}")
        elif in_base:
            lines.append(f"  - {c}: {base_cols[c]}  (removed)")
        else:
            lines.append(f"  + {c}: {target_cols[c]}  (added)")

    lines.append(f"\nBase rows: {len(base_df):,}   |   Target rows: {len(target_df):,}")
    return "\n".join(lines)


class ParquetDiffDialog(QDialog):
    """Dialog to compare two Parquet files and display a color-coded diff."""

    def __init__(self, current_df: Optional[pd.DataFrame] = None,
                 current_file: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parquet Diff & Compare")
        self.resize(1100, 700)
        self._base_df: Optional[pd.DataFrame] = current_df
        self._target_df: Optional[pd.DataFrame] = None
        self._base_file = current_file or "(current file)"

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # File selectors
        file_bar = QFrame()
        file_bar.setStyleSheet("background: #1c1c28; border-bottom: 1px solid #2d2d3a;")
        fb_layout = QHBoxLayout(file_bar)
        fb_layout.setContentsMargins(10, 8, 10, 8)

        fb_layout.addWidget(QLabel("🅱 Base:"))
        self.lbl_base = QLabel(os.path.basename(self._base_file) if self._base_file else "Not set")
        self.lbl_base.setStyleSheet("color: #e36262; font-weight: bold;")
        fb_layout.addWidget(self.lbl_base)

        btn_base = QPushButton("Browse…")
        btn_base.clicked.connect(self._pick_base)
        fb_layout.addWidget(btn_base)

        fb_layout.addSpacing(20)
        fb_layout.addWidget(QLabel("🅣 Target:"))
        self.lbl_target = QLabel("Not selected")
        self.lbl_target.setStyleSheet("color: #62b462; font-weight: bold;")
        fb_layout.addWidget(self.lbl_target)

        btn_target = QPushButton("Browse…")
        btn_target.clicked.connect(self._pick_target)
        fb_layout.addWidget(btn_target)

        fb_layout.addSpacing(20)
        fb_layout.addWidget(QLabel("Key Column (optional):"))
        self.cmb_key = QComboBox()
        self.cmb_key.addItem("(row position)")
        self.cmb_key.setMinimumWidth(180)
        fb_layout.addWidget(self.cmb_key)

        fb_layout.addStretch(1)
        self.btn_run = QPushButton("⚡ Compare")
        self.btn_run.setStyleSheet(
            "background:#107c41; color:white; border-radius:4px; padding:5px 16px; font-weight:bold;"
        )
        self.btn_run.clicked.connect(self._run_diff)
        fb_layout.addWidget(self.btn_run)

        layout.addWidget(file_bar)

        # Legend
        legend = QLabel(
            "  🟢 Added (in Target)   🔴 Deleted (in Base)   🟡 Modified cell   ⬜ Unchanged"
        )
        legend.setStyleSheet("padding: 4px 10px; color: #9090a0; font-size: 11px;")
        layout.addWidget(legend)

        # Main area: summary + diff table
        self.tabs = QTabWidget()

        # Tab 1: Diff Table
        self.diff_view = QTableView()
        self.diff_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.diff_view.setAlternatingRowColors(False)
        self.diff_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.diff_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabs.addTab(self.diff_view, "🔍 Diff View")

        # Tab 2: Schema diff
        self.txt_schema = QTextEdit()
        self.txt_schema.setReadOnly(True)
        self.txt_schema.setFont(QFont("Consolas", 10))
        self.tabs.addTab(self.txt_schema, "📐 Schema Diff")

        layout.addWidget(self.tabs, 1)

        # Summary bar
        self.lbl_summary = QLabel("Run a comparison to see results.")
        self.lbl_summary.setStyleSheet("padding: 6px 12px; color: #a0c0a0; font-size: 11px;")
        layout.addWidget(self.lbl_summary)

        # Export button
        btn_row = QHBoxLayout()
        btn_export = QPushButton("📤 Export Diff to CSV")
        btn_export.clicked.connect(self._export_diff)
        btn_row.addWidget(btn_export)
        btn_row.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._last_diff_model: Optional[DiffTableModel] = None

    def _pick_base(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Base Parquet File", "", "Parquet Files (*.parquet)")
        if path:
            df, _, _ = ParquetHandler.read_parquet(path)
            self._base_df = df
            self._base_file = path
            self.lbl_base.setText(os.path.basename(path))
            self._refresh_key_combo()

    def _pick_target(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Target Parquet File", "", "Parquet Files (*.parquet)")
        if path:
            df, _, _ = ParquetHandler.read_parquet(path)
            self._target_df = df
            self.lbl_target.setText(os.path.basename(path))
            self._refresh_key_combo()

    def _refresh_key_combo(self):
        self.cmb_key.clear()
        self.cmb_key.addItem("(row position)")
        if self._base_df is not None:
            for c in self._base_df.columns:
                self.cmb_key.addItem(str(c))

    def _run_diff(self):
        if self._base_df is None:
            QMessageBox.warning(self, "Missing File", "Please select a Base Parquet file.")
            return
        if self._target_df is None:
            QMessageBox.warning(self, "Missing File", "Please select a Target Parquet file.")
            return

        key = self.cmb_key.currentText()
        key_col = None if key == "(row position)" else key

        try:
            diff_df, row_status, changed_cells = _diff_dataframes(
                self._base_df, self._target_df, key_col
            )
        except Exception as ex:
            QMessageBox.critical(self, "Diff Error", str(ex))
            return

        model = DiffTableModel(diff_df, row_status, changed_cells)
        self.diff_view.setModel(model)
        self.diff_view.resizeColumnsToContents()
        self._last_diff_model = model

        summary = model.get_summary()
        self.lbl_summary.setText(
            f"Total: {summary['total']:,} rows   |   "
            f"🟢 Added: {summary['added']:,}   "
            f"🔴 Deleted: {summary['deleted']:,}   "
            f"🟡 Modified: {summary['changed']:,}   "
            f"⬜ Same: {summary['same']:,}"
        )

        # Schema diff
        self.txt_schema.setPlainText(_schema_diff_text(self._base_df, self._target_df))
        self.tabs.setCurrentIndex(0)

    def _export_diff(self):
        if self._last_diff_model is None:
            QMessageBox.information(self, "Export", "Run a comparison first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Diff", "", "CSV Files (*.csv)")
        if path:
            self._last_diff_model._df.to_csv(path, index=False)
            QMessageBox.information(self, "Export Complete", f"Diff exported to:\n{path}")
