"""
Unit tests for the Working Copy Diff feature.
Tests cover:
  - Baseline capture and delta tracking in ParquetTableModel
  - Vectorized row and cell change detection in _diff_dataframes
  - "Show Only Changed Rows" filtering and pagination in DiffTableModel
  - Column additions, deletions, and cell edits in the diff report
  - mark_clean / revert behaviour
"""

import sys
import os
import unittest

import pandas as pd
import numpy as np

# Ensure repo root is on the path regardless of where pytest is run from.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ui.parquet_diff import _diff_dataframes, DiffTableModel, DetailedChangesModel
from src.models.parquet_table_model import ParquetTableModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_simple_df(n_rows: int = 5) -> pd.DataFrame:
    return pd.DataFrame({
        "id":    list(range(1, n_rows + 1)),
        "name":  [f"Name_{i}" for i in range(1, n_rows + 1)],
        "value": [float(i * 10) for i in range(1, n_rows + 1)],
    })


# ---------------------------------------------------------------------------
# 1. ParquetTableModel - Baseline & mark_clean
# ---------------------------------------------------------------------------

class TestParquetTableModelBaseline(unittest.TestCase):
    """Verify that _original_df is captured / updated correctly."""

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.model = ParquetTableModel()

    def test_baseline_captured_on_set_dataframe(self):
        df = _make_simple_df()
        self.model.set_dataframe(df)
        orig = self.model.get_original_dataframe()
        pd.testing.assert_frame_equal(df, orig)

    def test_baseline_not_mutated_by_edit(self):
        df = _make_simple_df()
        self.model.set_dataframe(df)
        # Directly mutate the live dataframe via _raw_set_cell
        self.model._raw_set_cell(0, 2, 9999.0)
        orig = self.model.get_original_dataframe()
        # Original must still hold the original value
        self.assertEqual(orig.iat[0, 2], 10.0)

    def test_is_dirty_after_edit(self):
        self.model.set_dataframe(_make_simple_df())
        self.assertFalse(self.model.is_dirty)
        self.model._raw_set_cell(1, 1, "Modified")
        self.assertTrue(self.model.is_dirty)

    def test_mark_clean_resets_dirty_and_updates_baseline(self):
        df = _make_simple_df()
        self.model.set_dataframe(df)
        self.model._raw_set_cell(0, 2, 9999.0)
        self.assertTrue(self.model.is_dirty)
        self.model.mark_clean()
        self.assertFalse(self.model.is_dirty)
        # After mark_clean, new baseline should include the edit
        orig = self.model.get_original_dataframe()
        self.assertEqual(orig.iat[0, 2], 9999.0)


# ---------------------------------------------------------------------------
# 2. _diff_dataframes - positional / vectorized diff
# ---------------------------------------------------------------------------

class TestDiffDataframesPositional(unittest.TestCase):
    """Test vectorized positional diff (no key column)."""

    def _diff(self, base, target):
        return _diff_dataframes(base, target, key_col=None)

    def test_no_changes(self):
        df = _make_simple_df()
        result_df, row_status, changed_cells, cell_diffs, detailed = self._diff(df, df.copy())
        self.assertTrue(all(s == "same" for s in row_status))
        self.assertEqual(len(changed_cells), 0)
        self.assertEqual(len(detailed), 0)

    def test_single_cell_edit_detected(self):
        base = _make_simple_df()
        target = base.copy()
        target.iat[2, 2] = 999.0  # Row index 2, 'value' column (col 2)
        _, row_status, changed_cells, cell_diffs, detailed = self._diff(base, target)
        self.assertEqual(row_status.iloc[2], "changed")
        self.assertIn((2, 2), changed_cells)
        self.assertEqual(cell_diffs[(2, 2)], (30.0, 999.0))
        self.assertEqual(len(detailed), 1)
        self.assertEqual(detailed[0]["change_type"], "modified")

    def test_added_row_detected(self):
        base = _make_simple_df(3)
        target = _make_simple_df(5)   # 2 extra rows
        _, row_status, _, _, detailed = self._diff(base, target)
        added = [s for s in row_status if s == "added"]
        self.assertEqual(len(added), 2)
        added_changes = [d for d in detailed if d["change_type"] == "added_row"]
        self.assertEqual(len(added_changes), 2)

    def test_deleted_row_detected(self):
        base = _make_simple_df(5)
        target = _make_simple_df(3)   # 2 fewer rows
        _, row_status, _, _, detailed = self._diff(base, target)
        deleted = [s for s in row_status if s == "deleted"]
        self.assertEqual(len(deleted), 2)
        del_changes = [d for d in detailed if d["change_type"] == "deleted_row"]
        self.assertEqual(len(del_changes), 2)

    def test_null_to_value_detected(self):
        base = pd.DataFrame({"x": [1.0, None, 3.0]})
        target = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
        _, row_status, changed_cells, cell_diffs, _ = self._diff(base, target)
        self.assertEqual(row_status.iloc[1], "changed")
        self.assertIn((1, 0), changed_cells)

    def test_value_to_null_detected(self):
        base = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
        target = pd.DataFrame({"x": [1.0, None, 3.0]})
        _, row_status, changed_cells, _, _ = self._diff(base, target)
        self.assertEqual(row_status.iloc[1], "changed")
        self.assertIn((1, 0), changed_cells)

    def test_column_added_to_target(self):
        base = pd.DataFrame({"a": [1, 2, 3]})
        target = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        result_df, _, _, _, _ = self._diff(base, target)
        self.assertIn("b", result_df.columns)

    def test_column_removed_from_target(self):
        base = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        target = pd.DataFrame({"a": [1, 2, 3]})
        result_df, _, _, _, _ = self._diff(base, target)
        self.assertIn("b", result_df.columns)

    def test_both_nulls_same(self):
        """Two NaN values in the same position must NOT be flagged as changed."""
        base = pd.DataFrame({"x": [None, 2.0]})
        target = pd.DataFrame({"x": [None, 2.0]})
        _, row_status, changed_cells, _, _ = self._diff(base, target)
        self.assertEqual(row_status.iloc[0], "same")
        self.assertEqual(len(changed_cells), 0)

    def test_empty_base(self):
        base = pd.DataFrame({"a": pd.Series([], dtype=float)})
        target = pd.DataFrame({"a": [1.0, 2.0]})
        result_df, row_status, _, _, detailed = self._diff(base, target)
        self.assertEqual(len(result_df), 2)
        self.assertTrue(all(s == "added" for s in row_status))

    def test_empty_target(self):
        base = pd.DataFrame({"a": [1.0, 2.0]})
        target = pd.DataFrame({"a": pd.Series([], dtype=float)})
        result_df, row_status, _, _, detailed = self._diff(base, target)
        self.assertEqual(len(result_df), 2)
        self.assertTrue(all(s == "deleted" for s in row_status))


# ---------------------------------------------------------------------------
# 3. _diff_dataframes - key-column based diff
# ---------------------------------------------------------------------------

class TestDiffDataframesKeyBased(unittest.TestCase):
    """Test key-column merge diff."""

    def _diff(self, base, target, key="id"):
        return _diff_dataframes(base, target, key_col=key)

    def test_key_based_edit_detected(self):
        base = pd.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})
        target = pd.DataFrame({"id": [1, 2, 3], "val": [10, 99, 30]})  # row id=2 changed
        _, row_status, changed_cells, cell_diffs, detailed = self._diff(base, target)
        changed_rows = [i for i, s in enumerate(row_status) if s == "changed"]
        self.assertEqual(len(changed_rows), 1)
        modified = [d for d in detailed if d["change_type"] == "modified"]
        self.assertEqual(len(modified), 1)
        self.assertEqual(modified[0]["old_value"], 20)
        self.assertEqual(modified[0]["new_value"], 99)

    def test_key_based_added_row(self):
        base = pd.DataFrame({"id": [1, 2], "val": [10, 20]})
        target = pd.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})
        _, row_status, _, _, detailed = self._diff(base, target)
        added = [d for d in detailed if d["change_type"] == "added_row"]
        self.assertEqual(len(added), 1)

    def test_key_based_deleted_row(self):
        base = pd.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})
        target = pd.DataFrame({"id": [1, 3], "val": [10, 30]})
        _, row_status, _, _, detailed = self._diff(base, target)
        deleted = [d for d in detailed if d["change_type"] == "deleted_row"]
        self.assertEqual(len(deleted), 1)


# ---------------------------------------------------------------------------
# 4. DiffTableModel - Delta View & Pagination
# ---------------------------------------------------------------------------

class TestDiffTableModel(unittest.TestCase):
    """Test filtering and pagination in DiffTableModel."""

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication(sys.argv)

    def _make_model(self, base, target, changes_only=False):
        diff_df, row_status, changed_cells, cell_diffs, _ = _diff_dataframes(base, target)
        model = DiffTableModel(diff_df, row_status, changed_cells, cell_diffs)
        model.set_filter_changes_only(changes_only)
        return model

    def test_all_rows_visible_by_default(self):
        base = _make_simple_df(10)
        target = base.copy()
        target.iat[0, 2] = 9999.0
        model = self._make_model(base, target, changes_only=False)
        model.set_page_size(-1)
        self.assertEqual(model.rowCount(), 10)

    def test_delta_view_filters_unchanged_rows(self):
        base = _make_simple_df(10)
        target = base.copy()
        target.iat[0, 2] = 9999.0   # Only 1 row changed
        model = self._make_model(base, target, changes_only=True)
        model.set_page_size(-1)
        self.assertEqual(model.rowCount(), 1)

    def test_pagination_row_count(self):
        base = _make_simple_df(100)
        target = base.copy()
        diff_df, row_status, cc, cd, _ = _diff_dataframes(base, target)
        model = DiffTableModel(diff_df, row_status, cc, cd)
        model.set_page_size(20)
        self.assertEqual(model.rowCount(), 20)

    def test_pagination_last_page(self):
        base = _make_simple_df(25)
        target = base.copy()
        diff_df, row_status, cc, cd, _ = _diff_dataframes(base, target)
        model = DiffTableModel(diff_df, row_status, cc, cd)
        model.set_page_size(20)
        model.set_page(2)
        # Second page: 25 - 20 = 5 rows
        self.assertEqual(model.rowCount(), 5)

    def test_total_visible_rows(self):
        base = _make_simple_df(10)
        target = base.copy()
        target.iat[3, 1] = "Changed"
        model = self._make_model(base, target, changes_only=False)
        model.set_page_size(-1)
        self.assertEqual(model.total_visible_rows, 10)

    def test_tooltip_shows_before_after(self):
        from PySide6.QtCore import Qt
        base = pd.DataFrame({"v": [1.0, 2.0, 3.0]})
        target = pd.DataFrame({"v": [1.0, 99.0, 3.0]})
        diff_df, row_status, changed_cells, cell_diffs, _ = _diff_dataframes(base, target)
        model = DiffTableModel(diff_df, row_status, changed_cells, cell_diffs)
        model.set_page_size(-1)
        idx = model.index(1, 0)
        tooltip = model.data(idx, Qt.ItemDataRole.ToolTipRole)
        self.assertIn("2.0", tooltip)
        self.assertIn("99.0", tooltip)

    def test_summary_counts(self):
        base = _make_simple_df(5)
        target = _make_simple_df(6)  # 1 added row
        target.iat[0, 2] = 7777.0   # 1 cell changed in shared rows
        diff_df, row_status, changed_cells, cell_diffs, _ = _diff_dataframes(base, target)
        model = DiffTableModel(diff_df, row_status, changed_cells, cell_diffs)
        summary = model.get_summary()
        self.assertEqual(summary["added"], 1)
        self.assertEqual(summary["deleted"], 0)
        self.assertGreaterEqual(summary["changed_cells_count"], 1)


# ---------------------------------------------------------------------------
# 5. DetailedChangesModel - Search / Filter
# ---------------------------------------------------------------------------

class TestDetailedChangesModel(unittest.TestCase):

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication(sys.argv)
        self._changes = [
            {"row": 1, "column": "price", "old_value": 100, "new_value": 200, "change_type": "modified"},
            {"row": 2, "column": "name", "old_value": "Alice", "new_value": "Bob", "change_type": "modified"},
            {"row": 3, "column": "(Row Added)", "old_value": "<none>", "new_value": "Row #3", "change_type": "added_row"},
        ]

    def test_all_rows_initially_visible(self):
        model = DetailedChangesModel(self._changes)
        self.assertEqual(model.rowCount(), 3)

    def test_filter_by_column_name(self):
        model = DetailedChangesModel(self._changes)
        model.filter_text("price")
        self.assertEqual(model.rowCount(), 1)

    def test_filter_by_value(self):
        model = DetailedChangesModel(self._changes)
        model.filter_text("Alice")
        self.assertEqual(model.rowCount(), 1)

    def test_filter_by_change_type(self):
        model = DetailedChangesModel(self._changes)
        model.filter_text("added_row")
        self.assertEqual(model.rowCount(), 1)

    def test_filter_clear_shows_all(self):
        model = DetailedChangesModel(self._changes)
        model.filter_text("price")
        self.assertEqual(model.rowCount(), 1)
        model.filter_text("")
        self.assertEqual(model.rowCount(), 3)

    def test_no_match_shows_zero(self):
        model = DetailedChangesModel(self._changes)
        model.filter_text("zzznomatch999")
        self.assertEqual(model.rowCount(), 0)


# ---------------------------------------------------------------------------
# 6. Integration: model edit -> diff consistency
# ---------------------------------------------------------------------------

class TestModelEditAndDiff(unittest.TestCase):

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication(sys.argv)

    def test_model_edit_shows_in_diff(self):
        df = _make_simple_df(5)
        model = ParquetTableModel()
        model.set_dataframe(df)
        model._raw_set_cell(2, 2, 9999.0)
        original = model.get_original_dataframe()
        current = model.get_dataframe()
        _, row_status, changed_cells, _, _ = _diff_dataframes(original, current)
        self.assertEqual(row_status.iloc[2], "changed")
        self.assertIn((2, 2), changed_cells)

    def test_revert_via_set_dataframe(self):
        df = _make_simple_df(5)
        model = ParquetTableModel()
        model.set_dataframe(df)
        model._raw_set_cell(0, 1, "CHANGED")
        baseline = model.get_original_dataframe()
        model.set_dataframe(baseline)
        model.mark_clean()
        self.assertFalse(model.is_dirty)
        pd.testing.assert_frame_equal(model.get_dataframe(), df)

    def test_mark_clean_advances_baseline(self):
        df = _make_simple_df(5)
        model = ParquetTableModel()
        model.set_dataframe(df)
        model._raw_set_cell(1, 2, 777.0)
        model.mark_clean()
        pd.testing.assert_frame_equal(
            model.get_original_dataframe(), model.get_dataframe()
        )

    def test_diff_after_column_added(self):
        df = _make_simple_df(3)
        model = ParquetTableModel()
        model.set_dataframe(df)
        model.add_column("new_col", "string", "", _from_command=True)
        original = model.get_original_dataframe()
        current = model.get_dataframe()
        result_df, _, _, _, _ = _diff_dataframes(original, current)
        self.assertIn("new_col", result_df.columns)


if __name__ == "__main__":
    unittest.main()
