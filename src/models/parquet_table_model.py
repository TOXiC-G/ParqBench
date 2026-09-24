"""
Parquet Table Model for QTableView — v2 with full Undo/Redo integration.
Provides high-performance virtualized data binding, type-safe editing,
Spark/Excel-style multi-column filtering, sorting, pagination, metadata tooltips,
and reversible column schema operations (add/rename/delete) via QUndoStack.
"""
from __future__ import annotations

from typing import Any, Optional, Set, Tuple, List, Dict
import pandas as pd
import numpy as np
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QBrush, QUndoStack


class ParquetTableModel(QAbstractTableModel):
    """QAbstractTableModel subclass for efficient pandas DataFrame display, filtering, and editing."""

    dataModified = Signal()      # Emitted whenever any cell is edited
    filterChanged = Signal(int)  # Emitted with total filtered row count
    paginationChanged = Signal() # Emitted when pagination state changes

    def __init__(self, df: Optional[pd.DataFrame] = None, parent=None):
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame()
        self._original_df: pd.DataFrame = self._df.copy()
        self._modified_cells: Set[Tuple[int, int]] = set()  # (actual_row, col)
        self._is_dirty: bool = False

        # Undo stack
        self._undo_stack = QUndoStack(self)

        # Cached column metadata
        self._col_names: List[str] = []
        self._col_dtypes: List[Any] = []
        self._col_alignments: List[int] = []
        self._is_numeric_cols: List[bool] = []

        # Filtering, Sorting & Pagination state
        self._active_filters: Dict[str, Dict[str, Any]] = {}
        self._filtered_indices: np.ndarray = np.array([], dtype=np.int64)
        self._sort_col: Optional[int] = None
        self._sort_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder

        self._page: int = 1
        self._page_size: int = 250  # -1 means disabled (all rows)

        # Colors for display
        self._modified_bg_color = QColor(255, 243, 205)
        self._null_text_color = QColor(140, 140, 140)
        self._null_bg_color = QColor(248, 249, 250, 80)

        self._rebuild_column_cache()
        self._recompute_filtered_indices()

    # -------------------------------------------------------------------------
    # Undo/Redo Stack
    # -------------------------------------------------------------------------

    @property
    def undo_stack(self) -> QUndoStack:
        return self._undo_stack

    # -------------------------------------------------------------------------
    # Index Translation (Visual Row -> Actual DataFrame Row)
    # -------------------------------------------------------------------------

    def _get_actual_row(self, visual_row: int) -> int:
        if len(self._filtered_indices) == 0:
            return visual_row

        if self._page_size > 0:
            offset = (self._page - 1) * self._page_size
            filtered_idx = offset + visual_row
            if 0 <= filtered_idx < len(self._filtered_indices):
                return int(self._filtered_indices[filtered_idx])
            return 0
        else:
            if 0 <= visual_row < len(self._filtered_indices):
                return int(self._filtered_indices[visual_row])
            return 0

    # -------------------------------------------------------------------------
    # Core QAbstractTableModel Overrides
    # -------------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid() or self._df is None:
            return 0

        total_filtered = len(self._filtered_indices)
        if self._page_size > 0:
            start = (self._page - 1) * self._page_size
            if start >= total_filtered:
                return 0
            return min(self._page_size, total_filtered - start)
        return total_filtered

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid() or self._df is None:
            return 0
        return len(self._col_names)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or self._df is None:
            return None

        visual_row, col = index.row(), index.column()
        if col >= len(self._col_names):
            return None

        actual_row = self._get_actual_row(visual_row)
        if actual_row >= len(self._df):
            return None

        val = self._df.iat[actual_row, col]
        is_null = pd.isna(val)

        if role == Qt.ItemDataRole.DisplayRole:
            if is_null:
                return "<null>"
            if isinstance(val, (float, np.floating)):
                if np.isnan(val):
                    return "<null>"
                if np.isinf(val):
                    return "inf" if val > 0 else "-inf"
                return f"{val:g}"
            if isinstance(val, (pd.Timestamp, np.datetime64)):
                return str(val)
            if isinstance(val, bool):
                return "True" if val else "False"
            return str(val)

        elif role == Qt.ItemDataRole.EditRole:
            if is_null:
                return ""
            return str(val)

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return self._col_alignments[col] if col < len(self._col_alignments) else int(Qt.AlignmentFlag.AlignLeft)

        elif role == Qt.ItemDataRole.ForegroundRole:
            # 1. Null text color
            if is_null:
                return QBrush(self._null_text_color)
            # 2. THE FIX: Force black text if the cell is modified so it contrasts with the yellow background
            if (actual_row, col) in self._modified_cells:
                return QBrush(QColor(0, 0, 0)) # Black text
            # 3. Default text color
            return None

        elif role == Qt.ItemDataRole.BackgroundRole:
            if (actual_row, col) in self._modified_cells:
                return QBrush(self._modified_bg_color)
            if is_null:
                return QBrush(self._null_bg_color)
            return None

        elif role == Qt.ItemDataRole.ToolTipRole:
            col_name = self._col_names[col]
            col_type = str(self._col_dtypes[col])
            raw_repr = "<null>" if is_null else repr(val)
            mod_status = " (Edited)" if (actual_row, col) in self._modified_cells else ""
            return (
                f"Column: {col_name} [{col_type}]\n"
                f"Row: {actual_row + 1} (Page Row: {visual_row + 1})\n"
                f"Value: {raw_repr}{mod_status}"
            )

        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole or self._df is None:
            return False

        visual_row, col = index.row(), index.column()
        if col >= len(self._col_names):
            return False

        actual_row = self._get_actual_row(visual_row)
        if actual_row >= len(self._df):
            return False

        col_dtype = self._col_dtypes[col]
        current_val = self._df.iat[actual_row, col]

        parsed_val, success = self._cast_value(str(value).strip(), col_dtype, col=col)
        if not success:
            return False

        # Check equality
        try:
            if (pd.isna(current_val) and pd.isna(parsed_val)) or (current_val == parsed_val):
                return False
        except Exception:
            pass

        # Push to undo stack
        from src.models.commands import EditCellCommand
        cmd = EditCellCommand(self, actual_row, col, current_val, parsed_val)
        self._undo_stack.push(cmd)
        return True

    def _raw_set_cell(self, actual_row: int, col: int, value: Any) -> bool:
        """Direct cell write bypassing undo (called by commands)."""
        try:
            self._df.iat[actual_row, col] = value
            self._modified_cells.add((actual_row, col))
            self._is_dirty = True
            # Notify view
            self._recompute_filtered_indices()
            self.dataModified.emit()
            return True
        except Exception:
            return False

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if self._df is None:
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                if section < len(self._col_names):
                    name = self._col_names[section]
                    indicators = []
                    if self._sort_col == section:
                        indicators.append("▲" if self._sort_order == Qt.SortOrder.AscendingOrder else "▼")
                    if name in self._active_filters:
                        indicators.append("🔍")
                    return f"{name} {' '.join(indicators)}".strip()
            elif orientation == Qt.Orientation.Vertical:
                actual_r = self._get_actual_row(section)
                return str(actual_r + 1)

        elif role == Qt.ItemDataRole.ToolTipRole and orientation == Qt.Orientation.Horizontal:
            if section < len(self._col_names):
                col_name = self._col_names[section]
                dtype_str = str(self._col_dtypes[section])
                if dtype_str == "object" and self._df is not None and len(self._df) > 0:
                    import datetime
                    import decimal
                    sample = self._df[col_name].dropna()
                    if not sample.empty:
                        first_items = sample.head(10)
                        if any(isinstance(v, (datetime.date, datetime.datetime)) for v in first_items):
                            dtype_str = "date32 (date)"
                        elif any(isinstance(v, decimal.Decimal) for v in first_items):
                            dtype_str = "decimal"
                null_cnt = int(self._df[col_name].isna().sum())
                total = len(self._df)
                pct = (null_cnt / total * 100) if total > 0 else 0
                filter_status = "Active" if col_name in self._active_filters else "None"

                return (
                    f"--- Column Details ---\n"
                    f"Name: {col_name}\n"
                    f"Data Type: {dtype_str}\n"
                    f"Nulls: {null_cnt:,} ({pct:.1f}%)\n"
                    f"Filter: {filter_status}\n"
                    f"Click: Sort | Right-Click: Filter/Options"
                )

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )

    # -------------------------------------------------------------------------
    # Filtering, Sorting & Pagination Engine
    # -------------------------------------------------------------------------

    def set_filter(self, col_name: str, filter_dict: Dict[str, Any]):
        if filter_dict.get("type") == "clear":
            self._active_filters.pop(col_name, None)
        else:
            self._active_filters[col_name] = filter_dict
        self._recompute_filtered_indices()

    def remove_filter(self, col_name: str):
        if col_name in self._active_filters:
            del self._active_filters[col_name]
            self._recompute_filtered_indices()

    def clear_all_filters(self):
        self._active_filters.clear()
        self._recompute_filtered_indices()

    @property
    def active_filters(self) -> Dict[str, Dict[str, Any]]:
        return self._active_filters

    def get_total_filtered_rows(self) -> int:
        return len(self._filtered_indices)

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder):
        if column < 0 or column >= len(self._col_names):
            return
        self._sort_col = column
        self._sort_order = order
        self._recompute_filtered_indices()

    def set_page(self, page: int):
        self.beginResetModel()
        self._page = max(1, page)
        self.endResetModel()
        self.paginationChanged.emit()

    def set_page_size(self, size: int):
        self.beginResetModel()
        self._page_size = size
        self._page = 1
        self.endResetModel()
        self.paginationChanged.emit()

    @property
    def current_page(self) -> int:
        return self._page

    @property
    def page_size(self) -> int:
        return self._page_size

    def _recompute_filtered_indices(self):
        self.beginResetModel()

        if self._df is None or len(self._df) == 0:
            self._filtered_indices = np.array([], dtype=np.int64)
            self.endResetModel()
            self.filterChanged.emit(0)
            return

        mask = pd.Series(True, index=self._df.index)

        for col_name, f_info in self._active_filters.items():
            if col_name not in self._df.columns:
                continue

            series = self._df[col_name]
            f_type = f_info.get("type")

            if f_type == "values":
                allowed_values = f_info.get("values", [])
                include_null = f_info.get("include_null", False)
                col_mask = series.isin(allowed_values)
                if include_null:
                    col_mask = col_mask | series.isna()
                mask = mask & col_mask

            elif f_type == "condition":
                op = f_info.get("op")
                val1_str = str(f_info.get("val1", "")).strip()
                val2_str = str(f_info.get("val2", "")).strip()
                dtype = series.dtype

                if op == "null":
                    mask = mask & series.isna()
                elif op == "not_null":
                    mask = mask & series.notna()
                else:
                    # Check if series is decimal in object column
                    is_dec = False
                    if dtype == object:
                        import decimal
                        sample = series.dropna()
                        if not sample.empty and any(isinstance(v, decimal.Decimal) for v in sample.head(10)):
                            is_dec = True

                    if is_dec:
                        num_series = pd.to_numeric(series, errors="coerce")
                        try:
                            clean_v1 = val1_str.replace("$", "").replace(",", "")
                            parsed_val1 = float(clean_v1)
                            if op == "=":
                                mask = mask & (num_series == parsed_val1)
                            elif op == "!=":
                                mask = mask & (num_series != parsed_val1)
                            elif op == ">":
                                mask = mask & (num_series > parsed_val1)
                            elif op == ">=":
                                mask = mask & (num_series >= parsed_val1)
                            elif op == "<":
                                mask = mask & (num_series < parsed_val1)
                            elif op == "<=":
                                mask = mask & (num_series <= parsed_val1)
                            elif op == "between":
                                clean_v2 = val2_str.replace("$", "").replace(",", "")
                                parsed_val2 = float(clean_v2)
                                mask = mask & (num_series >= parsed_val1) & (num_series <= parsed_val2)
                        except Exception:
                            pass
                    else:
                        parsed_val1, s1 = self._cast_value(val1_str, dtype)
                        if s1:
                            if op == "=":
                                mask = mask & (series == parsed_val1)
                            elif op == "!=":
                                mask = mask & (series != parsed_val1)
                            elif op == ">":
                                mask = mask & (series > parsed_val1)
                            elif op == ">=":
                                mask = mask & (series >= parsed_val1)
                            elif op == "<":
                                mask = mask & (series < parsed_val1)
                            elif op == "<=":
                                mask = mask & (series <= parsed_val1)
                            elif op == "between":
                                parsed_val2, s2 = self._cast_value(val2_str, dtype)
                                if s2:
                                    mask = mask & (series >= parsed_val1) & (series <= parsed_val2)

        filtered_sub_df = self._df[mask]

        if self._sort_col is not None and self._sort_col < len(self._col_names):
            sort_col_name = self._col_names[self._sort_col]
            ascending = (self._sort_order == Qt.SortOrder.AscendingOrder)
            filtered_sub_df = filtered_sub_df.sort_values(by=sort_col_name, ascending=ascending, na_position="last")

        self._filtered_indices = filtered_sub_df.index.to_numpy(dtype=np.int64)

        if self._page_size > 0:
            max_pages = max(1, (len(self._filtered_indices) + self._page_size - 1) // self._page_size)
            if self._page > max_pages:
                self._page = max_pages

        self.endResetModel()
        self.filterChanged.emit(len(self._filtered_indices))
        self.paginationChanged.emit()

    # -------------------------------------------------------------------------
    # Column Schema Operations (undoable wrappers called by commands)
    # -------------------------------------------------------------------------

    def add_column(self, col_name: str, dtype_str: str, default_val_str: str, _from_command: bool = False):
        """Add a new column with given dtype and optional default value."""
        if col_name in self._df.columns:
            return

        # Determine default value
        default = None
        if default_val_str:
            import datetime
            dtype_map = {
                "int64": int, "float64": float, "string": str, "bool": bool,
                "datetime64": pd.Timestamp, "date32": lambda s: pd.to_datetime(s).date(),
            }
            try:
                caster = dtype_map.get(dtype_str, str)
                if caster == bool:
                    default = default_val_str.lower() in ("true", "1", "yes")
                elif caster == pd.Timestamp:
                    default = pd.Timestamp(default_val_str)
                elif dtype_str == "date32":
                    default = pd.to_datetime(default_val_str).date()
                else:
                    default = caster(default_val_str)
            except Exception:
                default = None

        # Create column
        if dtype_str == "int64":
            self._df[col_name] = pd.array([default] * len(self._df), dtype=pd.Int64Dtype())
        elif dtype_str == "float64":
            self._df[col_name] = pd.array([default] * len(self._df), dtype=float)
        elif dtype_str == "bool":
            self._df[col_name] = pd.array([default] * len(self._df), dtype=pd.BooleanDtype())
        elif dtype_str.startswith("datetime"):
            self._df[col_name] = pd.array(
                [default if default else pd.NaT] * len(self._df), dtype="datetime64[ns]"
            )
        elif dtype_str == "date32":
            self._df[col_name] = pd.array([default] * len(self._df), dtype="object")
        else:
            self._df[col_name] = pd.array([default] * len(self._df), dtype="object")

        self._rebuild_column_cache()
        self._is_dirty = True
        self._recompute_filtered_indices()
        self.dataModified.emit()

        if not _from_command:
            from src.models.commands import AddColumnCommand
            cmd = AddColumnCommand(self, col_name, dtype_str, default_val_str)
            self._undo_stack.push(cmd)

    def rename_column(self, old_name: str, new_name: str, _from_command: bool = False):
        """Rename a column, updating active filters accordingly."""
        if old_name not in self._df.columns or new_name in self._df.columns:
            return

        self._df = self._df.rename(columns={old_name: new_name})

        # Update filters that referenced the old name
        if old_name in self._active_filters:
            self._active_filters[new_name] = self._active_filters.pop(old_name)

        self._rebuild_column_cache()
        self._is_dirty = True
        self._recompute_filtered_indices()
        self.dataModified.emit()

        if not _from_command:
            from src.models.commands import RenameColumnCommand
            cmd = RenameColumnCommand(self, old_name, new_name)
            self._undo_stack.push(cmd)

    def delete_column(self, col_name: str, _from_command: bool = False):
        """Delete a column by name."""
        if col_name not in self._df.columns:
            return

        if not _from_command:
            col_idx = list(self._df.columns).index(col_name)
            from src.models.commands import DeleteColumnCommand
            cmd = DeleteColumnCommand(self, col_name, col_idx)
            self._undo_stack.push(cmd)
            return  # command's redo() will do the actual deletion

        self._df = self._df.drop(columns=[col_name])
        self._active_filters.pop(col_name, None)
        self._rebuild_column_cache()
        self._is_dirty = True
        self._recompute_filtered_indices()
        self.dataModified.emit()

    # -------------------------------------------------------------------------
    # Helper & Mutation Methods
    # -------------------------------------------------------------------------

    def _rebuild_column_cache(self):
        if self._df is None or len(self._df.columns) == 0:
            self._col_names = []
            self._col_dtypes = []
            self._col_alignments = []
            self._is_numeric_cols = []
            return

        self._col_names = [str(c) for c in self._df.columns]
        self._col_dtypes = [self._df[c].dtype for c in self._df.columns]

        import decimal
        import datetime

        is_num_list = []
        alignments = []

        for c, col_name in enumerate(self._df.columns):
            dt = self._col_dtypes[c]
            is_num = pd.api.types.is_numeric_dtype(dt) and not pd.api.types.is_bool_dtype(dt)
            is_date = False

            if not is_num and dt == object and len(self._df) > 0:
                sample = self._df.iloc[:20, c].dropna()
                if not sample.empty:
                    if any(isinstance(v, decimal.Decimal) for v in sample):
                        is_num = True
                    elif any(isinstance(v, (datetime.date, datetime.datetime)) for v in sample):
                        is_date = True

            is_num_list.append(is_num)

            if is_num:
                alignments.append(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
            elif pd.api.types.is_bool_dtype(dt) or pd.api.types.is_datetime64_any_dtype(dt) or is_date:
                alignments.append(int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter))
            else:
                alignments.append(int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))

        self._is_numeric_cols = is_num_list
        self._col_alignments = alignments

    def set_dataframe(self, df: pd.DataFrame) -> None:
        """Replaces the active DataFrame in the model."""
        self._df = df.copy()
        self._original_df = df.copy()
        self._rebuild_column_cache()
        self._modified_cells.clear()
        self._active_filters.clear()
        self._sort_col = None
        self._page = 1
        self._is_dirty = False
        self._undo_stack.clear()
        self._recompute_filtered_indices()

    def get_dataframe(self) -> pd.DataFrame:
        return self._df

    def get_original_dataframe(self) -> pd.DataFrame:
        return self._original_df.copy()

    @property
    def is_dirty(self) -> bool:
        return self._is_dirty

    def mark_clean(self) -> None:
        self._is_dirty = False
        self._original_df = self._df.copy()
        self._modified_cells.clear()
        self._undo_stack.setClean()
        if len(self._df) > 0 and len(self._col_names) > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(self.rowCount() - 1, len(self._col_names) - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.BackgroundRole])

    def insert_row(self, at_row: int = -1, _from_command: bool = False) -> bool:
        if self._df is None:
            return False

        if not _from_command:
            effective_at = len(self._df) if at_row == -1 else at_row
            from src.models.commands import InsertRowCommand
            cmd = InsertRowCommand(self, effective_at)
            self._undo_stack.push(cmd)
            return True

        if at_row == -1 or at_row > len(self._df):
            at_row = len(self._df)

        new_row = {col: None for col in self._df.columns}
        top = self._df.iloc[:at_row]
        bottom = self._df.iloc[at_row:]
        row_df = pd.DataFrame([new_row], columns=self._df.columns)
        self._df = pd.concat([top, row_df, bottom], ignore_index=True)

        new_mods = set()
        for r, c in self._modified_cells:
            if r >= at_row:
                new_mods.add((r + 1, c))
            else:
                new_mods.add((r, c))
        for c in range(len(self._df.columns)):
            new_mods.add((at_row, c))
        self._modified_cells = new_mods
        self._is_dirty = True
        self._recompute_filtered_indices()
        self.dataModified.emit()
        return True

    def delete_rows(self, row_indices: List[int]) -> bool:
        """Delete by visual row indices, pushing to undo stack."""
        if self._df is None or not row_indices:
            return False

        actual_rows = sorted(set(self._get_actual_row(r) for r in row_indices))
        from src.models.commands import DeleteRowsCommand
        cmd = DeleteRowsCommand(self, actual_rows)
        self._undo_stack.push(cmd)
        return True

    def delete_rows_actual(self, actual_rows: List[int], _from_command: bool = False) -> bool:
        """Delete by actual row indices (called by DeleteRowsCommand)."""
        for r in sorted(actual_rows, reverse=True):
            if 0 <= r < len(self._df):
                self._df = self._df.drop(self._df.index[r]).reset_index(drop=True)

        self._modified_cells.clear()
        self._is_dirty = True
        self._recompute_filtered_indices()
        self.dataModified.emit()
        return True

    def paste_bulk_matrix(self, start_row: int, start_col: int, matrix: List[List[str]],
                          _from_command: bool = False) -> Tuple[int, int]:
        """High-performance bulk paste with undo support."""
        if not matrix or self._df is None:
            return 0, 0

        actual_start_row = self._get_actual_row(start_row) if not _from_command else start_row
        num_paste_rows = len(matrix)
        num_paste_cols = max(len(row) for row in matrix) if matrix else 0

        needed_rows = actual_start_row + num_paste_rows
        current_rows = len(self._df)

        if needed_rows > current_rows:
            diff = needed_rows - current_rows
            empty_data = {col: [None] * diff for col in self._df.columns}
            extension_df = pd.DataFrame(empty_data)
            self._df = pd.concat([self._df, extension_df], ignore_index=True)

        max_cols = len(self._col_names)
        actual_cols_to_paste = min(num_paste_cols, max_cols - start_col)

        if not _from_command:
            # Snapshot old values for undo
            old_matrix = []
            for r_off in range(num_paste_rows):
                old_row = []
                for c_off in range(actual_cols_to_paste):
                    tr = actual_start_row + r_off
                    tc = start_col + c_off
                    if tr < len(self._df) and tc < len(self._col_names):
                        old_row.append(self._df.iat[tr, tc])
                    else:
                        old_row.append(None)
                old_matrix.append(old_row)

            from src.models.commands import BulkPasteCommand
            cmd = BulkPasteCommand(self, actual_start_row, start_col, old_matrix, matrix)
            self._undo_stack.push(cmd)
            return num_paste_rows, actual_cols_to_paste

        # Direct write (from command)
        for c_offset in range(actual_cols_to_paste):
            target_col = start_col + c_offset
            col_dtype = self._col_dtypes[target_col]
            for r_offset in range(num_paste_rows):
                target_r = actual_start_row + r_offset
                raw_val = matrix[r_offset][c_offset].strip() if c_offset < len(matrix[r_offset]) else ""
                parsed_val, success = self._cast_value(raw_val, col_dtype, col=target_col)
                if success:
                    try:
                        self._df.iat[target_r, target_col] = parsed_val
                    except Exception:
                        pass
            self._modified_cells.update(
                (actual_start_row + r, target_col) for r in range(num_paste_rows)
            )

        self._is_dirty = True
        self._recompute_filtered_indices()
        self.dataModified.emit()
        return num_paste_rows, actual_cols_to_paste

    def apply_formula(self, target_col: str, result_series: pd.Series, _from_command: bool = False):
        """Apply a formula result to a column (or add it as new)."""
        is_new = target_col not in self._df.columns
        old_series = self._df[target_col].copy() if not is_new else pd.Series(dtype=object)

        if not _from_command:
            from src.models.commands import ApplyFormulaCommand, AddColumnCommand
            if is_new:
                # First add empty column, then apply
                self._df[target_col] = None
                self._rebuild_column_cache()

            new_series = result_series.reset_index(drop=True)
            if len(new_series) == len(self._df):
                cmd = ApplyFormulaCommand(self, target_col, old_series, new_series)
                self._undo_stack.push(cmd)
            return

        # Direct application (from command)
        if target_col not in self._df.columns:
            self._df[target_col] = None
        aligned = result_series.reset_index(drop=True)
        if len(aligned) == len(self._df):
            self._df[target_col] = aligned.values
        col_idx = list(self._df.columns).index(target_col)
        for r in range(len(self._df)):
            self._modified_cells.add((r, col_idx))
        self._is_dirty = True
        self._rebuild_column_cache()
        self._recompute_filtered_indices()
        self.dataModified.emit()

    def compute_stats(self, selected_indexes: List[QModelIndex]) -> Dict[str, Any]:
        if not selected_indexes or self._df is None:
            return {"count": 0, "sum": None, "avg": None, "min": None, "max": None}

        col_to_rows: Dict[int, List[int]] = {}
        for idx in selected_indexes:
            c = idx.column()
            actual_r = self._get_actual_row(idx.row())
            col_to_rows.setdefault(c, []).append(actual_r)

        numeric_values = []
        total_count = len(selected_indexes)
        non_empty = 0

        for col, rows in col_to_rows.items():
            if col >= len(self._col_names):
                continue
            is_num = self._is_numeric_cols[col]
            series = self._df.iloc[rows, col]
            valid_series = series.dropna()
            non_empty += len(valid_series)
            if is_num and not valid_series.empty:
                try:
                    numeric_values.extend(valid_series.astype(float).tolist())
                except Exception:
                    for v in valid_series:
                        try:
                            numeric_values.append(float(v))
                        except Exception:
                            pass

        stats = {
            "count": total_count,
            "non_empty": non_empty,
            "sum": None,
            "avg": None,
            "min": None,
            "max": None,
            "is_numeric": False,
        }

        if numeric_values:
            stats["is_numeric"] = True
            arr = np.array(numeric_values, dtype=np.float64)
            stats["sum"] = float(np.sum(arr))
            stats["avg"] = float(np.mean(arr))
            stats["min"] = float(np.min(arr))
            stats["max"] = float(np.max(arr))

        return stats

    # -------------------------------------------------------------------------
    # Internal Type Conversion
    # -------------------------------------------------------------------------

    def _cast_value(self, input_str: str, target_dtype: Any, col: Optional[int] = None) -> Tuple[Any, bool]:
        if input_str == "" or input_str.lower() in ("none", "null", "<null>", "nan"):
            return None, True

        try:
            if pd.api.types.is_bool_dtype(target_dtype):
                lowered = input_str.lower()
                if lowered in ("true", "1", "t", "yes", "y"):
                    return True, True
                elif lowered in ("false", "0", "f", "no", "n"):
                    return False, True
                return None, False

            elif pd.api.types.is_integer_dtype(target_dtype):
                return int(round(float(input_str))), True

            elif pd.api.types.is_float_dtype(target_dtype):
                return float(input_str), True

            elif pd.api.types.is_datetime64_any_dtype(target_dtype):
                return pd.to_datetime(input_str), True

            else:
                # Check if this object column is date-like or decimal-like
                if col is not None and self._df is not None and col < len(self._df.columns):
                    import datetime
                    import decimal
                    sample = self._df.iloc[:, col].dropna()
                    if not sample.empty:
                        first_vals = sample.head(10)
                        if any(isinstance(v, (datetime.date, datetime.datetime)) for v in first_vals):
                            parsed_dt = pd.to_datetime(input_str, errors="coerce")
                            if pd.notna(parsed_dt):
                                return parsed_dt.date(), True
                        elif any(isinstance(v, decimal.Decimal) for v in first_vals):
                            try:
                                cleaned = input_str.replace("$", "").replace(",", "")
                                return decimal.Decimal(cleaned), True
                            except Exception:
                                return None, False
                return input_str, True

        except Exception:
            return None, False
