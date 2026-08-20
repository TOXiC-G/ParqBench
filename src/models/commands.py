"""
Undo/Redo Command System for Parquet Editor.
Provides QUndoCommand subclasses for every mutable operation: cell edits, bulk paste,
row insertions/deletions, and column schema changes (add/rename/delete).
"""
from __future__ import annotations

from typing import Any, List, Set, Tuple, TYPE_CHECKING
import copy
import pandas as pd
from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from src.models.parquet_table_model import ParquetTableModel


class EditCellCommand(QUndoCommand):
    """Undoable single-cell value edit."""

    def __init__(self, model: "ParquetTableModel", actual_row: int, col: int, old_value: Any, new_value: Any):
        super().__init__(f"Edit cell ({actual_row + 1}, {model._col_names[col]})")
        self._model = model
        self._actual_row = actual_row
        self._col = col
        self._old_value = old_value
        self._new_value = new_value

    def redo(self):
        self._apply(self._new_value)

    def undo(self):
        self._apply(self._old_value)

    def _apply(self, val: Any):
        try:
            self._model._df.iat[self._actual_row, self._col] = val
            if val == self._new_value:
                self._model._modified_cells.add((self._actual_row, self._col))
            else:
                # Restoring old value — if it's the original, remove modified mark
                self._model._modified_cells.discard((self._actual_row, self._col))
            self._model._is_dirty = True
            self._model._recompute_filtered_indices()
            self._model.dataModified.emit()
        except Exception:
            pass


class BulkPasteCommand(QUndoCommand):
    """Undoable bulk paste of a row×col matrix starting at (start_row, start_col)."""

    def __init__(self, model: "ParquetTableModel", start_actual_row: int, start_col: int,
                 old_matrix: List[List[Any]], new_matrix: List[List[str]]):
        n_rows = len(new_matrix)
        n_cols = max((len(r) for r in new_matrix), default=0)
        super().__init__(f"Paste {n_rows}×{n_cols} block")
        self._model = model
        self._start_row = start_actual_row
        self._start_col = start_col
        self._old_matrix = old_matrix
        self._new_matrix = new_matrix

    def redo(self):
        self._model.paste_bulk_matrix(self._start_row, self._start_col, self._new_matrix, _from_command=True)

    def undo(self):
        # Restore old values cell by cell
        for r_off, row in enumerate(self._old_matrix):
            for c_off, val in enumerate(row):
                actual_r = self._start_row + r_off
                actual_c = self._start_col + c_off
                if actual_r < len(self._model._df) and actual_c < len(self._model._col_names):
                    try:
                        self._model._df.iat[actual_r, actual_c] = val
                        self._model._modified_cells.discard((actual_r, actual_c))
                    except Exception:
                        pass
        self._model._is_dirty = True
        self._model._recompute_filtered_indices()
        self._model.dataModified.emit()


class InsertRowCommand(QUndoCommand):
    """Undoable row insertion at a given position."""

    def __init__(self, model: "ParquetTableModel", at_row: int):
        super().__init__(f"Insert row at {at_row + 1}")
        self._model = model
        self._at_row = at_row

    def redo(self):
        self._model.insert_row(self._at_row, _from_command=True)

    def undo(self):
        # Remove the row that was just inserted
        if 0 <= self._at_row < len(self._model._df):
            self._model._df = self._model._df.drop(self._model._df.index[self._at_row]).reset_index(drop=True)
            self._model._modified_cells.clear()
            self._model._is_dirty = True
            self._model._recompute_filtered_indices()
            self._model.dataModified.emit()


class DeleteRowsCommand(QUndoCommand):
    """Undoable row deletion (snapshot-restore)."""

    def __init__(self, model: "ParquetTableModel", actual_rows: List[int]):
        super().__init__(f"Delete {len(actual_rows)} row(s)")
        self._model = model
        self._actual_rows = sorted(actual_rows, reverse=True)
        # Snapshot deleted rows in order so undo can reconstruct
        self._deleted_data: List[Tuple[int, pd.DataFrame]] = []
        for r in sorted(actual_rows):
            self._deleted_data.append((r, model._df.iloc[[r]].copy()))

    def redo(self):
        self._model.delete_rows_actual(self._actual_rows, _from_command=True)

    def undo(self):
        # Re-insert deleted rows in original order
        for at_row, row_df in sorted(self._deleted_data, key=lambda x: x[0]):
            top = self._model._df.iloc[:at_row]
            bottom = self._model._df.iloc[at_row:]
            self._model._df = pd.concat([top, row_df, bottom], ignore_index=True)
        self._model._modified_cells.clear()
        self._model._is_dirty = True
        self._model._recompute_filtered_indices()
        self._model.dataModified.emit()


class AddColumnCommand(QUndoCommand):
    """Undoable column addition."""

    def __init__(self, model: "ParquetTableModel", col_name: str, dtype_str: str, default_val: Any):
        super().__init__(f"Add column '{col_name}'")
        self._model = model
        self._col_name = col_name
        self._dtype_str = dtype_str
        self._default_val = default_val

    def redo(self):
        self._model.add_column(self._col_name, self._dtype_str, self._default_val, _from_command=True)

    def undo(self):
        if self._col_name in self._model._df.columns:
            self._model._df = self._model._df.drop(columns=[self._col_name])
            self._model._rebuild_column_cache()
            self._model._is_dirty = True
            self._model._recompute_filtered_indices()
            self._model.dataModified.emit()


class RenameColumnCommand(QUndoCommand):
    """Undoable column rename."""

    def __init__(self, model: "ParquetTableModel", old_name: str, new_name: str):
        super().__init__(f"Rename column '{old_name}' → '{new_name}'")
        self._model = model
        self._old_name = old_name
        self._new_name = new_name

    def redo(self):
        self._model.rename_column(self._old_name, self._new_name, _from_command=True)

    def undo(self):
        self._model.rename_column(self._new_name, self._old_name, _from_command=True)


class DeleteColumnCommand(QUndoCommand):
    """Undoable column deletion (snapshot)."""

    def __init__(self, model: "ParquetTableModel", col_name: str, col_index: int):
        super().__init__(f"Delete column '{col_name}'")
        self._model = model
        self._col_name = col_name
        self._col_index = col_index
        # Snapshot column data
        self._col_data: pd.Series = model._df[col_name].copy() if col_name in model._df.columns else pd.Series(dtype=object)
        self._col_dtype_str: str = str(model._df[col_name].dtype) if col_name in model._df.columns else "object"

    def redo(self):
        if self._col_name in self._model._df.columns:
            self._model._df = self._model._df.drop(columns=[self._col_name])
            self._model._rebuild_column_cache()
            self._model._is_dirty = True
            self._model._recompute_filtered_indices()
            self._model.dataModified.emit()

    def undo(self):
        # Re-insert column at original position
        idx = min(self._col_index, len(self._model._df.columns))
        self._model._df.insert(idx, self._col_name, self._col_data.values)
        self._model._rebuild_column_cache()
        self._model._is_dirty = True
        self._model._recompute_filtered_indices()
        self._model.dataModified.emit()


class ApplyFormulaCommand(QUndoCommand):
    """Undoable formula/expression applied to one or more columns."""

    def __init__(self, model: "ParquetTableModel", target_col: str, old_series: pd.Series, new_series: pd.Series):
        super().__init__(f"Apply formula to '{target_col}'")
        self._model = model
        self._target_col = target_col
        self._old_series = old_series.copy()
        self._new_series = new_series.copy()

    def redo(self):
        self._apply(self._new_series)

    def undo(self):
        self._apply(self._old_series)

    def _apply(self, series: pd.Series):
        if self._target_col in self._model._df.columns:
            self._model._df[self._target_col] = series.values
            col_idx = list(self._model._df.columns).index(self._target_col)
            for r in range(len(self._model._df)):
                self._model._modified_cells.add((r, col_idx))
            self._model._is_dirty = True
            self._model._rebuild_column_cache()
            self._model._recompute_filtered_indices()
            self._model.dataModified.emit()
