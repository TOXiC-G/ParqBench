"""
Parquet Diff / Compare Tool for Parquet Editor.
Provides visual Git-like diff capabilities for comparing:
1. Working copy (current unsaved changes) vs Baseline (loaded/saved state).
2. Two arbitrary Parquet files from disk.

Features:
- Fast vectorized delta calculation (scales to 100k+ rows).
- Color-coded visual diff grid (green=added, red=deleted, amber=modified).
- Rich tooltips on modified cells showing 'Before → After'.
- Toggle to filter view to only changed rows ('Delta View').
- Pagination support for fast and smooth UI interaction.
- Detailed Audit Log of all modifications with search and CSV/JSON export.
- Schema drift summary.
"""
from __future__ import annotations

from typing import Optional, List, Dict, Tuple, Any, Set
import os
import json
import pandas as pd
import numpy as np
from PySide6.QtCore import Qt, Signal, QAbstractTableModel, QModelIndex
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSplitter, QTableView, QFileDialog, QMessageBox, QComboBox,
    QHeaderView, QAbstractItemView, QFrame, QTextEdit, QTabWidget,
    QWidget, QFormLayout, QCheckBox, QLineEdit,
)
from PySide6.QtGui import QColor, QBrush, QFont, QCursor

from src.engine.parquet_handler import ParquetHandler


_COLOR_ADDED   = QColor(46, 125, 50, 140)    # Green tint – added rows
_COLOR_DELETED = QColor(198, 40, 40, 140)    # Red tint  – deleted rows
_COLOR_CHANGED = QColor(239, 108, 0, 140)    # Amber tint – changed cells
_COLOR_SAME    = QColor(0, 0, 0, 0)          # Transparent – unchanged


class DiffTableModel(QAbstractTableModel):
    """Virtual and paginated table model showing diff results with color-coding and tooltips."""

    def __init__(
        self,
        df: pd.DataFrame,
        row_status: pd.Series,
        changed_cells: Set[Tuple[int, int]],
        cell_diffs: Optional[Dict[Tuple[int, int], Tuple[Any, Any]]] = None,
        parent=None,
    ):
        """
        Args:
            df: The combined diff DataFrame.
            row_status: Series with same index, values: 'added'|'deleted'|'changed'|'same'.
            changed_cells: Set of (row_iloc, col_iloc) that have cell-level changes.
            cell_diffs: Optional dict of (row_iloc, col_iloc) -> (old_val, new_val).
        """
        super().__init__(parent)
        self._df = df.reset_index(drop=True)
        self._row_status = row_status.reset_index(drop=True)
        self._changed_cells = changed_cells
        self._cell_diffs = cell_diffs or {}
        self._cols = [str(c) for c in df.columns]

        # Pagination & Filtering state
        self._show_only_changes: bool = False
        self._page: int = 1
        self._page_size: int = 100  # -1 means all
        self._visible_indices: np.ndarray = np.array([], dtype=np.int64)

        self._recompute_visible_indices()

    def set_filter_changes_only(self, changes_only: bool):
        self.beginResetModel()
        self._show_only_changes = changes_only
        self._page = 1
        self._recompute_visible_indices()
        self.endResetModel()

    def set_page(self, page: int):
        self.beginResetModel()
        self._page = max(1, page)
        self.endResetModel()

    def set_page_size(self, size: int):
        self.beginResetModel()
        self._page_size = size
        self._page = 1
        self.endResetModel()

    @property
    def current_page(self) -> int:
        return self._page

    @property
    def page_size(self) -> int:
        return self._page_size

    @property
    def total_visible_rows(self) -> int:
        return len(self._visible_indices)

    def _recompute_visible_indices(self):
        if len(self._df) == 0:
            self._visible_indices = np.array([], dtype=np.int64)
            return

        if self._show_only_changes:
            mask = self._row_status.isin(["added", "deleted", "changed"]).to_numpy()
            self._visible_indices = np.flatnonzero(mask)
        else:
            self._visible_indices = np.arange(len(self._df), dtype=np.int64)

    def _get_actual_row(self, visual_row: int) -> int:
        if len(self._visible_indices) == 0:
            return visual_row
        if self._page_size > 0:
            offset = (self._page - 1) * self._page_size
            idx = offset + visual_row
            if 0 <= idx < len(self._visible_indices):
                return int(self._visible_indices[idx])
            return 0
        else:
            if 0 <= visual_row < len(self._visible_indices):
                return int(self._visible_indices[visual_row])
            return 0

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        total = len(self._visible_indices)
        if self._page_size > 0:
            start = (self._page - 1) * self._page_size
            if start >= total:
                return 0
            return min(self._page_size, total - start)
        return total

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._cols)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        v_r, c = index.row(), index.column()
        r = self._get_actual_row(v_r)
        if r >= len(self._df) or c >= len(self._cols):
            return None

        val = self._df.iat[r, c]
        is_null = pd.isna(val)

        if role == Qt.ItemDataRole.DisplayRole:
            if is_null:
                return "<null>"
            if isinstance(val, (float, np.floating)):
                if np.isnan(val):
                    return "<null>"
                return f"{val:g}"
            return str(val)

        elif role == Qt.ItemDataRole.BackgroundRole:
            status = self._row_status.iloc[r] if r < len(self._row_status) else "same"
            if status == "added":
                return QBrush(_COLOR_ADDED)
            elif status == "deleted":
                return QBrush(_COLOR_DELETED)
            elif (r, c) in self._changed_cells:
                return QBrush(_COLOR_CHANGED)
            return None

        elif role == Qt.ItemDataRole.ForegroundRole:
            if is_null:
                return QBrush(QColor(140, 140, 140))
            status = self._row_status.iloc[r] if r < len(self._row_status) else "same"
            if status in ("added", "deleted") or (r, c) in self._changed_cells:
                return QBrush(QColor(255, 255, 255))
            return None

        elif role == Qt.ItemDataRole.ToolTipRole:
            status = self._row_status.iloc[r] if r < len(self._row_status) else "same"
            col_name = self._cols[c]
            if (r, c) in self._cell_diffs:
                old_val, new_val = self._cell_diffs[(r, c)]
                return (
                    f"Column: {col_name} (Row #{r + 1})\n"
                    f"🔴 Baseline: {repr(old_val)}\n"
                    f"🟢 Current:  {repr(new_val)}"
                )
            elif status == "added":
                return f"🟢 Added Row #{r + 1} | Column: {col_name} | Value: {repr(val)}"
            elif status == "deleted":
                return f"🔴 Deleted Row #{r + 1} | Column: {col_name} | Value: {repr(val)}"
            return f"Column: {col_name} (Row #{r + 1})\nValue: {repr(val)} (Unchanged)"

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal and section < len(self._cols):
                return self._cols[section]
            elif orientation == Qt.Orientation.Vertical:
                r = self._get_actual_row(section)
                status = self._row_status.iloc[r] if r < len(self._row_status) else "same"
                prefix = ""
                if status == "added":
                    prefix = "+ "
                elif status == "deleted":
                    prefix = "- "
                elif status == "changed":
                    prefix = "~ "
                return f"{prefix}{r + 1}"
        return None

    def get_summary(self) -> dict:
        counts = self._row_status.value_counts().to_dict()
        return {
            "added": counts.get("added", 0),
            "deleted": counts.get("deleted", 0),
            "changed": counts.get("changed", 0),
            "same": counts.get("same", 0),
            "total": len(self._df),
            "changed_cells_count": len(self._changed_cells),
        }


class DetailedChangesModel(QAbstractTableModel):
    """Model displaying a tabular audit log of each individual changed cell and row."""

    HEADERS = ["#", "Row", "Column", "Original Value (Baseline)", "New Value (Current)", "Change Type"]

    def __init__(self, changes_list: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self._all_changes = changes_list
        self._filtered_changes = list(changes_list)

    def filter_text(self, text: str):
        self.beginResetModel()
        if not text.strip():
            self._filtered_changes = list(self._all_changes)
        else:
            q = text.strip().lower()
            self._filtered_changes = [
                rec for rec in self._all_changes
                if q in str(rec.get("column", "")).lower()
                or q in str(rec.get("old_value", "")).lower()
                or q in str(rec.get("new_value", "")).lower()
                or q in str(rec.get("change_type", "")).lower()
                or q in str(rec.get("row", "")).lower()
            ]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._filtered_changes)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        if r >= len(self._filtered_changes):
            return None

        rec = self._filtered_changes[r]

        if role == Qt.ItemDataRole.DisplayRole:
            if c == 0:
                return str(r + 1)
            elif c == 1:
                return f"Row {rec.get('row', '')}"
            elif c == 2:
                return str(rec.get("column", ""))
            elif c == 3:
                val = rec.get("old_value")
                return "<null>" if pd.isna(val) else str(val)
            elif c == 4:
                val = rec.get("new_value")
                return "<null>" if pd.isna(val) else str(val)
            elif c == 5:
                ctype = rec.get("change_type", "")
                if ctype == "modified":
                    return "✏️ Modified Cell"
                elif ctype == "added_row":
                    return "🟢 Added Row"
                elif ctype == "deleted_row":
                    return "🔴 Deleted Row"
                return ctype

        elif role == Qt.ItemDataRole.ForegroundRole:
            if c == 3:
                return QBrush(QColor(239, 83, 80))   # Red for old
            elif c == 4:
                return QBrush(QColor(102, 187, 106)) # Green for new
            elif c == 5:
                ctype = rec.get("change_type", "")
                if ctype == "modified":
                    return QBrush(QColor(255, 183, 77)) # Amber
                elif ctype == "added_row":
                    return QBrush(QColor(102, 187, 106))
                elif ctype == "deleted_row":
                    return QBrush(QColor(239, 83, 80))

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if c in (0, 1):
                return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if section < len(self.HEADERS):
                return self.HEADERS[section]
        return None


def _diff_dataframes(
    base_df: pd.DataFrame,
    target_df: pd.DataFrame,
    key_col: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.Series, Set[Tuple[int, int]], Dict[Tuple[int, int], Tuple[Any, Any]], List[Dict[str, Any]]]:
    """
    Produces a high-performance combined diff DataFrame with cell-level change details.

    Returns:
        (combined_df, row_status_series, changed_cells_set, cell_diffs_dict, detailed_changes_list)
    """
    if base_df is None:
        base_df = pd.DataFrame()
    if target_df is None:
        target_df = pd.DataFrame()

    # 1. Key-based merge diff if key column is specified and present in both
    if key_col and key_col in base_df.columns and key_col in target_df.columns:
        merged = pd.merge(
            base_df, target_df, on=key_col, how="outer",
            suffixes=("__base", "__target"), indicator=True
        )
        statuses = []
        changed_cells: Set[Tuple[int, int]] = set()
        cell_diffs: Dict[Tuple[int, int], Tuple[Any, Any]] = {}
        detailed_changes: List[Dict[str, Any]] = []

        common_cols = [c for c in base_df.columns if c != key_col and c in target_df.columns]
        added_cols = [c for c in target_df.columns if c != key_col and c not in base_df.columns]
        deleted_cols = [c for c in base_df.columns if c != key_col and c not in target_df.columns]
        all_cols = [key_col] + common_cols + added_cols + deleted_cols

        result_rows = []

        for i, row in merged.iterrows():
            ind = row["_merge"]
            rec = {key_col: row[key_col]}
            row_idx = len(result_rows)

            if ind == "left_only":
                status = "deleted"
                for c in common_cols + deleted_cols:
                    rec[c] = row.get(f"{c}__base" if c in common_cols else c, np.nan)
                for c in added_cols:
                    rec[c] = np.nan
                detailed_changes.append({
                    "row": row_idx + 1,
                    "column": "(Row Deleted)",
                    "old_value": f"Key {row[key_col]}",
                    "new_value": "<deleted>",
                    "change_type": "deleted_row",
                })

            elif ind == "right_only":
                status = "added"
                for c in common_cols + added_cols:
                    rec[c] = row.get(f"{c}__target" if c in common_cols else c, np.nan)
                for c in deleted_cols:
                    rec[c] = np.nan
                detailed_changes.append({
                    "row": row_idx + 1,
                    "column": "(Row Added)",
                    "old_value": "<none>",
                    "new_value": f"Key {row[key_col]}",
                    "change_type": "added_row",
                })

            else:
                status = "same"
                for c_idx, c in enumerate(common_cols):
                    bval = row.get(f"{c}__base")
                    tval = row.get(f"{c}__target")
                    both_null = pd.isna(bval) and pd.isna(tval)
                    if not both_null and bval != tval:
                        status = "changed"
                        col_pos = c_idx + 1  # +1 for key col
                        changed_cells.add((row_idx, col_pos))
                        cell_diffs[(row_idx, col_pos)] = (bval, tval)
                        detailed_changes.append({
                            "row": row_idx + 1,
                            "column": c,
                            "old_value": bval,
                            "new_value": tval,
                            "change_type": "modified",
                        })
                    rec[c] = tval
                for c in added_cols:
                    rec[c] = row.get(c, np.nan)
                for c in deleted_cols:
                    rec[c] = row.get(c, np.nan)

            statuses.append(status)
            result_rows.append(rec)

        result_df = pd.DataFrame(result_rows, columns=all_cols) if result_rows else pd.DataFrame(columns=all_cols)
        return result_df, pd.Series(statuses), changed_cells, cell_diffs, detailed_changes

    # 2. Vectorized positional diff (ultra-fast for large datasets)
    else:
        base_cols = list(base_df.columns)
        target_cols = list(target_df.columns)
        common_cols = [c for c in base_cols if c in target_cols]
        added_cols = [c for c in target_cols if c not in base_cols]
        deleted_cols = [c for c in base_cols if c not in target_cols]
        all_display_cols = common_cols + added_cols + deleted_cols

        n_base = len(base_df)
        n_target = len(target_df)
        n_max = max(n_base, n_target)

        cell_diffs: Dict[Tuple[int, int], Tuple[Any, Any]] = {}
        changed_cells: Set[Tuple[int, int]] = set()
        row_statuses = ["same"] * n_max
        detailed_changes: List[Dict[str, Any]] = []

        n_common_rows = min(n_base, n_target)

        # Vectorized check on common rows and common columns
        for c_idx, col in enumerate(all_display_cols):
            if col in common_cols and n_common_rows > 0:
                s_base = base_df[col].iloc[:n_common_rows]
                s_target = target_df[col].iloc[:n_common_rows]

                base_null = s_base.isna().to_numpy()
                target_null = s_target.isna().to_numpy()

                null_mismatch = base_null != target_null
                neither_null = ~base_null & ~target_null

                val_mismatch = np.zeros(n_common_rows, dtype=bool)
                if np.any(neither_null):
                    b_sub = s_base.to_numpy()[neither_null]
                    t_sub = s_target.to_numpy()[neither_null]
                    try:
                        val_mismatch_sub = (b_sub != t_sub)
                    except Exception:
                        val_mismatch_sub = np.array([b != t for b, t in zip(b_sub, t_sub)])
                    val_mismatch[neither_null] = val_mismatch_sub

                mismatches = np.flatnonzero(null_mismatch | val_mismatch)

                for r in mismatches:
                    r_int = int(r)
                    row_statuses[r_int] = "changed"
                    old_v = s_base.iat[r_int]
                    new_v = s_target.iat[r_int]
                    changed_cells.add((r_int, c_idx))
                    cell_diffs[(r_int, c_idx)] = (old_v, new_v)
                    detailed_changes.append({
                        "row": r_int + 1,
                        "column": col,
                        "old_value": old_v,
                        "new_value": new_v,
                        "change_type": "modified",
                    })

        # Added rows (in working copy beyond baseline)
        if n_target > n_base:
            for r in range(n_base, n_target):
                row_statuses[r] = "added"
                detailed_changes.append({
                    "row": r + 1,
                    "column": "(Row Added)",
                    "old_value": "<none>",
                    "new_value": f"Row #{r + 1}",
                    "change_type": "added_row",
                })

        # Deleted rows (in baseline beyond working copy)
        elif n_base > n_target:
            for r in range(n_target, n_base):
                row_statuses[r] = "deleted"
                detailed_changes.append({
                    "row": r + 1,
                    "column": "(Row Deleted)",
                    "old_value": f"Row #{r + 1}",
                    "new_value": "<deleted>",
                    "change_type": "deleted_row",
                })

        # Unified display dataframe
        target_pad = target_df.reindex(columns=all_display_cols, index=range(n_max))
        if n_base > n_target:
            for col in all_display_cols:
                if col in base_df.columns:
                    target_pad.loc[n_target:n_base - 1, col] = base_df.loc[n_target:n_base - 1, col].values

        result_df = target_pad if not target_pad.empty else pd.DataFrame(columns=all_display_cols)
        return result_df, pd.Series(row_statuses), changed_cells, cell_diffs, detailed_changes


def _schema_diff_text(base_df: pd.DataFrame, target_df: pd.DataFrame) -> str:
    lines = ["=== Schema & Column Drift Summary ===\n"]
    base_cols = dict(zip(base_df.columns, base_df.dtypes)) if base_df is not None else {}
    target_cols = dict(zip(target_df.columns, target_df.dtypes)) if target_df is not None else {}

    all_cols = list(dict.fromkeys(list(base_cols) + list(target_cols)))
    added_count = 0
    removed_count = 0
    type_change_count = 0

    for c in all_cols:
        in_base = c in base_cols
        in_target = c in target_cols
        if in_base and in_target:
            if str(base_cols[c]) != str(target_cols[c]):
                lines.append(f"  ~ {c}: {base_cols[c]} → {target_cols[c]}  (TYPE CHANGED)")
                type_change_count += 1
            else:
                lines.append(f"    {c}: {base_cols[c]}")
        elif in_base:
            lines.append(f"  - {c}: {base_cols[c]}  (REMOVED / DELETED)")
            removed_count += 1
        else:
            lines.append(f"  + {c}: {target_cols[c]}  (ADDED)")
            added_count += 1

    lines.append("\n--- Summary ---")
    lines.append(f"Columns: {len(target_cols)} current vs {len(base_cols)} baseline (+{added_count}, -{removed_count}, ~{type_change_count})")
    lines.append(f"Rows:    {len(target_df):,} current vs {len(base_df):,} baseline ({len(target_df) - len(base_df):+,} delta)")
    return "\n".join(lines)


class WorkingCopyDiffDialog(QDialog):
    """
    Git-like Unsaved Changes Inspector.
    Compares the current working copy DataFrame against its baseline (loaded/saved state).
    """

    revert_requested = Signal()  # Emitted if user chooses to revert all changes

    def __init__(
        self,
        base_df: pd.DataFrame,
        current_df: pd.DataFrame,
        file_name: str = "Current Parquet",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Review Changes (Git-style Diff) — {file_name}")
        self.resize(1150, 720)
        self._base_df = base_df.copy() if base_df is not None else pd.DataFrame()
        self._current_df = current_df.copy() if current_df is not None else pd.DataFrame()
        self._file_name = file_name

        self._diff_model: Optional[DiffTableModel] = None
        self._audit_model: Optional[DetailedChangesModel] = None
        self._detailed_changes: List[Dict[str, Any]] = []

        self._setup_ui()
        self._compute_and_display_diff()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Top Metric Header Cards
        header_frame = QFrame()
        header_frame.setStyleSheet(
            "background: #181824; border: 1px solid #282838; border-radius: 6px; padding: 6px;"
        )
        hf_layout = QHBoxLayout(header_frame)
        hf_layout.setContentsMargins(10, 6, 10, 6)
        hf_layout.setSpacing(16)

        self.lbl_title = QLabel(f"📄 <b>{self._file_name}</b>")
        self.lbl_title.setStyleSheet("font-size: 13px; color: #f0f0f5;")
        hf_layout.addWidget(self.lbl_title)

        hf_layout.addStretch(1)

        self.card_modified = QLabel("🟡 0 edits")
        self.card_modified.setStyleSheet("background: #332619; color: #ffb74d; border: 1px solid #ff9800; border-radius: 4px; padding: 3px 8px; font-weight: bold; font-size: 11px;")
        hf_layout.addWidget(self.card_modified)

        self.card_added = QLabel("🟢 +0 rows")
        self.card_added.setStyleSheet("background: #1b3320; color: #81c784; border: 1px solid #4caf50; border-radius: 4px; padding: 3px 8px; font-weight: bold; font-size: 11px;")
        hf_layout.addWidget(self.card_added)

        self.card_deleted = QLabel("🔴 -0 rows")
        self.card_deleted.setStyleSheet("background: #331c1c; color: #e57373; border: 1px solid #f44336; border-radius: 4px; padding: 3px 8px; font-weight: bold; font-size: 11px;")
        hf_layout.addWidget(self.card_deleted)

        self.card_rows = QLabel("📊 0 rows")
        self.card_rows.setStyleSheet("color: #a0a0b5; font-size: 11px; padding: 3px;")
        hf_layout.addWidget(self.card_rows)

        layout.addWidget(header_frame)

        # 2. Controls & Filter Bar
        toolbar = QFrame()
        toolbar.setStyleSheet("background: #1e1e2c; border-radius: 4px; padding: 4px;")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 4, 8, 4)
        tb_layout.setSpacing(12)

        self.chk_changes_only = QCheckBox("⚡ Show Only Changed Rows (Delta View)")
        self.chk_changes_only.setChecked(True)
        self.chk_changes_only.setStyleSheet("font-weight: bold; color: #4ade80;")
        self.chk_changes_only.toggled.connect(self._on_changes_only_toggled)
        tb_layout.addWidget(self.chk_changes_only)

        tb_layout.addSpacing(16)
        tb_layout.addWidget(QLabel("Key Column (optional):"))
        self.cmb_key = QComboBox()
        self.cmb_key.addItem("(row position)")
        if self._base_df is not None:
            for c in self._base_df.columns:
                self.cmb_key.addItem(str(c))
        self.cmb_key.currentIndexChanged.connect(lambda: self._compute_and_display_diff())
        tb_layout.addWidget(self.cmb_key)

        tb_layout.addStretch(1)

        # Pagination controls for visual grid
        tb_layout.addWidget(QLabel("Page:"))
        self.btn_prev_page = QPushButton("◀")
        self.btn_prev_page.setFixedWidth(28)
        self.btn_prev_page.clicked.connect(self._prev_page)
        tb_layout.addWidget(self.btn_prev_page)

        self.lbl_page_info = QLabel("1 / 1")
        self.lbl_page_info.setStyleSheet("color: #e0e0e0; font-weight: 500;")
        tb_layout.addWidget(self.lbl_page_info)

        self.btn_next_page = QPushButton("▶")
        self.btn_next_page.setFixedWidth(28)
        self.btn_next_page.clicked.connect(self._next_page)
        tb_layout.addWidget(self.btn_next_page)

        tb_layout.addWidget(QLabel("Page size:"))
        self.cmb_page_size = QComboBox()
        self.cmb_page_size.addItems(["50", "100", "250", "500", "All (No pagination)"])
        self.cmb_page_size.setCurrentText("100")
        self.cmb_page_size.currentIndexChanged.connect(self._on_page_size_changed)
        tb_layout.addWidget(self.cmb_page_size)

        layout.addWidget(toolbar)

        # 3. Central Tabs
        self.tabs = QTabWidget()

        # Tab 1: Visual Grid Diff
        grid_tab = QWidget()
        gt_layout = QVBoxLayout(grid_tab)
        gt_layout.setContentsMargins(0, 4, 0, 0)
        self.diff_view = QTableView()
        self.diff_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.diff_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.diff_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.diff_view.setStyleSheet("QTableView { background-color: #121218; gridline-color: #262633; }")
        gt_layout.addWidget(self.diff_view)

        # Legend footer
        legend_bar = QLabel(
            "Legend:   🟢 Added Row   🔴 Deleted Row   🟡 Modified Cell (Hover for Before/After)   ⬜ Unchanged"
        )
        legend_bar.setStyleSheet("color: #9a9ab0; font-size: 11px; padding: 4px 6px;")
        gt_layout.addWidget(legend_bar)

        self.tabs.addTab(grid_tab, "🔍 Visual Diff Grid")

        # Tab 2: Detailed Changes Audit Log
        audit_tab = QWidget()
        at_layout = QVBoxLayout(audit_tab)
        at_layout.setContentsMargins(4, 4, 4, 4)

        search_bar = QHBoxLayout()
        search_bar.addWidget(QLabel("🔍 Filter Changes:"))
        self.txt_audit_search = QLineEdit()
        self.txt_audit_search.setPlaceholderText("Search by column, old value, new value, or row...")
        self.txt_audit_search.textChanged.connect(self._on_audit_search_changed)
        search_bar.addWidget(self.txt_audit_search)
        at_layout.addLayout(search_bar)

        self.audit_view = QTableView()
        self.audit_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.audit_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.audit_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.audit_view.setStyleSheet("QTableView { background-color: #121218; gridline-color: #262633; }")
        at_layout.addWidget(self.audit_view)

        self.tabs.addTab(audit_tab, "📋 Detailed Changes Audit Log")

        # Tab 3: Schema Drift
        self.txt_schema = QTextEdit()
        self.txt_schema.setReadOnly(True)
        self.txt_schema.setFont(QFont("Consolas", 10))
        self.txt_schema.setStyleSheet("background-color: #121218; color: #d0d0d8; padding: 8px;")
        self.tabs.addTab(self.txt_schema, "📐 Schema Drift")

        layout.addWidget(self.tabs, 1)

        # 4. Bottom Action Bar
        bottom_bar = QHBoxLayout()

        btn_export = QPushButton("📤 Export Diff Report (CSV / JSON)...")
        btn_export.clicked.connect(self._export_diff)
        bottom_bar.addWidget(btn_export)

        btn_revert = QPushButton("↩️ Revert All Unsaved Changes")
        btn_revert.setStyleSheet("background: #3a1c1c; color: #ff8080; border: 1px solid #772b2b; padding: 5px 12px; font-weight: bold;")
        btn_revert.clicked.connect(self._on_revert_clicked)
        bottom_bar.addWidget(btn_revert)

        bottom_bar.addStretch(1)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_close)

        layout.addLayout(bottom_bar)

    def _compute_and_display_diff(self):
        key = self.cmb_key.currentText()
        key_col = None if key == "(row position)" else key

        try:
            diff_df, row_status, changed_cells, cell_diffs, detailed_changes = _diff_dataframes(
                self._base_df, self._current_df, key_col
            )
        except Exception as ex:
            QMessageBox.critical(self, "Diff Error", f"Failed to compute diff:\n{str(ex)}")
            return

        self._detailed_changes = detailed_changes

        # 1. Update Diff Grid Model
        self._diff_model = DiffTableModel(diff_df, row_status, changed_cells, cell_diffs, parent=self)
        self._diff_model.set_filter_changes_only(self.chk_changes_only.isChecked())
        
        # Apply page size
        ps_text = self.cmb_page_size.currentText()
        ps = -1 if "All" in ps_text else int(ps_text)
        self._diff_model.set_page_size(ps)

        self.diff_view.setModel(self._diff_model)
        self.diff_view.resizeColumnsToContents()

        # 2. Update Audit Log Model
        self._audit_model = DetailedChangesModel(detailed_changes, parent=self)
        self.audit_view.setModel(self._audit_model)
        self.audit_view.resizeColumnsToContents()

        # 3. Update Summary Badges
        summary = self._diff_model.get_summary()
        self.card_modified.setText(f"🟡 {summary['changed_cells_count']:,} cell edits")
        self.card_added.setText(f"🟢 +{summary['added']:,} rows")
        self.card_deleted.setText(f"🔴 -{summary['deleted']:,} rows")
        self.card_rows.setText(f"📊 {len(self._current_df):,} current rows (baseline: {len(self._base_df):,})")

        # 4. Schema diff text
        self.txt_schema.setPlainText(_schema_diff_text(self._base_df, self._current_df))

        self._update_pagination_ui()

    def _on_changes_only_toggled(self, checked: bool):
        if self._diff_model:
            self._diff_model.set_filter_changes_only(checked)
            self._update_pagination_ui()

    def _on_page_size_changed(self):
        if not self._diff_model:
            return
        ps_text = self.cmb_page_size.currentText()
        ps = -1 if "All" in ps_text else int(ps_text)
        self._diff_model.set_page_size(ps)
        self._update_pagination_ui()

    def _prev_page(self):
        if self._diff_model and self._diff_model.current_page > 1:
            self._diff_model.set_page(self._diff_model.current_page - 1)
            self._update_pagination_ui()

    def _next_page(self):
        if self._diff_model:
            total_visible = self._diff_model.total_visible_rows
            ps = self._diff_model.page_size
            if ps > 0:
                max_page = max(1, (total_visible + ps - 1) // ps)
                if self._diff_model.current_page < max_page:
                    self._diff_model.set_page(self._diff_model.current_page + 1)
                    self._update_pagination_ui()

    def _update_pagination_ui(self):
        if not self._diff_model:
            return
        total_visible = self._diff_model.total_visible_rows
        ps = self._diff_model.page_size
        if ps <= 0:
            self.lbl_page_info.setText(f"All {total_visible:,} rows")
            self.btn_prev_page.setEnabled(False)
            self.btn_next_page.setEnabled(False)
        else:
            max_page = max(1, (total_visible + ps - 1) // ps)
            curr = self._diff_model.current_page
            self.lbl_page_info.setText(f"Page {curr:,} of {max_page:,} ({total_visible:,} rows)")
            self.btn_prev_page.setEnabled(curr > 1)
            self.btn_next_page.setEnabled(curr < max_page)

    def _on_audit_search_changed(self, text: str):
        if self._audit_model:
            self._audit_model.filter_text(text)

    def _export_diff(self):
        if not self._detailed_changes:
            QMessageBox.information(self, "Export Diff", "No changes found to export.")
            return

        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Diff Report", "changes_diff_report.csv",
            "CSV Report (*.csv);;JSON Delta (*.json)"
        )
        if not path:
            return

        try:
            if path.lower().endswith(".json") or "JSON" in selected_filter:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self._detailed_changes, f, indent=2, default=str)
            else:
                df_changes = pd.DataFrame(self._detailed_changes)
                df_changes.to_csv(path, index=False)

            QMessageBox.information(
                self, "Export Complete",
                f"Diff report with {len(self._detailed_changes):,} changes exported to:\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export report:\n{str(e)}")

    def _on_revert_clicked(self):
        confirm = QMessageBox.question(
            self,
            "Revert All Changes",
            "Are you sure you want to discard all unsaved edits and revert back to the original baseline file?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.revert_requested.emit()
            self.accept()


class ParquetDiffDialog(QDialog):
    """Dialog to compare two Parquet files from disk and display a color-coded diff."""

    def __init__(self, current_df: Optional[pd.DataFrame] = None,
                 current_file: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare Parquet Files (Diff)")
        self.resize(1150, 700)
        self._base_df: Optional[pd.DataFrame] = current_df
        self._target_df: Optional[pd.DataFrame] = None
        self._base_file = current_file or "(current file)"

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # File selectors
        file_bar = QFrame()
        file_bar.setStyleSheet("background: #1c1c28; border-bottom: 1px solid #2d2d3a; padding: 6px;")
        fb_layout = QHBoxLayout(file_bar)
        fb_layout.setContentsMargins(10, 6, 10, 6)

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
        fb_layout.addWidget(QLabel("Key Column:"))
        self.cmb_key = QComboBox()
        self.cmb_key.addItem("(row position)")
        self.cmb_key.setMinimumWidth(160)
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
            "  🟢 Added (in Target)   🔴 Deleted (in Base)   🟡 Modified cell (Hover for values)   ⬜ Unchanged"
        )
        legend.setStyleSheet("padding: 4px 10px; color: #9090a0; font-size: 11px;")
        layout.addWidget(legend)

        # Main area: tabs
        self.tabs = QTabWidget()

        # Tab 1: Diff Table
        self.diff_view = QTableView()
        self.diff_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
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
        self.lbl_summary = QLabel("Select two files and run comparison.")
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
            diff_df, row_status, changed_cells, cell_diffs, _ = _diff_dataframes(
                self._base_df, self._target_df, key_col
            )
        except Exception as ex:
            QMessageBox.critical(self, "Diff Error", str(ex))
            return

        model = DiffTableModel(diff_df, row_status, changed_cells, cell_diffs, parent=self)
        model.set_page_size(-1)  # All rows by default
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
