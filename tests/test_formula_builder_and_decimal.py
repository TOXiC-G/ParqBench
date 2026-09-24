"""
Tests for Formula Builder and Decimal/Type Compatibility.
Verifies that decimal.Decimal columns, float operations, direct column references,
currency cleaning, conditional helpers, table model stats/filtering, and Parquet saving work seamlessly.
"""
import os
import sys
import unittest
import decimal
from decimal import Decimal
import tempfile
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

app = QApplication.instance()
if app is None:
    app = QApplication([])

from src.ui.formula_dialog import FormulaBuilderDialog, _build_safe_ns, to_numeric, where, coalesce
from src.models.parquet_table_model import ParquetTableModel
from src.engine.parquet_handler import ParquetHandler


class TestFormulaBuilderAndDecimal(unittest.TestCase):

    def setUp(self):
        # DataFrame with decimal.Decimal, float, integer, currency string, and nulls
        self.df = pd.DataFrame({
            "price": [Decimal("10.50"), Decimal("20.00"), Decimal("15.75"), None],
            "tax_rate": [0.10, 0.15, 0.08, 0.05],
            "quantity": [2, 5, 1, 3],
            "raw_currency": ["$1,200.50", "€450.00", "$10.00", None],
            "category": ["A", "B", "A", "C"],
        })
        self.dialog = FormulaBuilderDialog(self.df)

    def test_decimal_multiplication_with_float(self):
        """The core issue: multiplying a Decimal column by a float literal (e.g. 1.2)."""
        self.dialog.txt_expr.setPlainText("col('price') * 1.2")
        result = self.dialog._evaluate()
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 4)
        self.assertAlmostEqual(result.iloc[0], 10.50 * 1.2, places=4)
        self.assertAlmostEqual(result.iloc[1], 20.00 * 1.2, places=4)
        self.assertAlmostEqual(result.iloc[2], 15.75 * 1.2, places=4)
        self.assertTrue(pd.isna(result.iloc[3]))

    def test_reverse_decimal_multiplication(self):
        """1.2 * col('price') must also evaluate cleanly."""
        self.dialog.txt_expr.setPlainText("1.2 * col('price')")
        result = self.dialog._evaluate()
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.iloc[0], 1.2 * 10.50, places=4)

    def test_decimal_addition_subtraction_division(self):
        """Binary arithmetic (+, -, /) between Decimal columns and floats."""
        self.dialog.txt_expr.setPlainText("col('price') + 5.5")
        res_add = self.dialog._evaluate()
        self.assertIsNotNone(res_add)
        self.assertAlmostEqual(res_add.iloc[0], 16.0, places=4)

        self.dialog.txt_expr.setPlainText("col('price') - 0.5")
        res_sub = self.dialog._evaluate()
        self.assertIsNotNone(res_sub)
        self.assertAlmostEqual(res_sub.iloc[0], 10.0, places=4)

        self.dialog.txt_expr.setPlainText("col('price') / 2.0")
        res_div = self.dialog._evaluate()
        self.assertIsNotNone(res_div)
        self.assertAlmostEqual(res_div.iloc[0], 5.25, places=4)

    def test_decimal_column_multiplied_by_float_column(self):
        """col('price') * col('tax_rate') where one is Decimal and one is float."""
        self.dialog.txt_expr.setPlainText("col('price') * col('tax_rate')")
        result = self.dialog._evaluate()
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.iloc[0], 10.50 * 0.10, places=4)
        self.assertAlmostEqual(result.iloc[1], 20.00 * 0.15, places=4)

    def test_direct_column_reference(self):
        """Expressions like price * 1.2 or price * quantity without col('...')."""
        self.dialog.txt_expr.setPlainText("price * 1.2")
        result = self.dialog._evaluate()
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.iloc[0], 12.6, places=4)

        self.dialog.txt_expr.setPlainText("price * quantity")
        result2 = self.dialog._evaluate()
        self.assertIsNotNone(result2)
        self.assertAlmostEqual(result2.iloc[0], 21.0, places=4)

    def test_column_accessor_variants(self):
        """col('price'), col['price'], col.price, c.price, df['price'], df.price."""
        for expr in ["col['price'] * 1.2", "col.price * 1.2", "c.price * 1.2", "df['price'] * 1.2", "df.price * 1.2"]:
            self.dialog.txt_expr.setPlainText(expr)
            result = self.dialog._evaluate()
            self.assertIsNotNone(result, f"Failed for expression: {expr}")
            self.assertAlmostEqual(result.iloc[0], 12.6, places=4)

    def test_decimal_comparisons(self):
        """col('price') > 15.0 or col('price') <= 20.0."""
        self.dialog.txt_expr.setPlainText("col('price') > 15.0")
        result = self.dialog._evaluate()
        self.assertIsNotNone(result)
        self.assertFalse(result.iloc[0]) # 10.50 > 15.0 is False
        self.assertTrue(result.iloc[1])  # 20.00 > 15.0 is True
        self.assertTrue(result.iloc[2])  # 15.75 > 15.0 is True

    def test_decimal_numpy_and_pandas_methods(self):
        """np.log, round, mean, sum on Decimal columns."""
        self.dialog.txt_expr.setPlainText("np.log(col('price'))")
        res_log = self.dialog._evaluate()
        self.assertIsNotNone(res_log)
        self.assertAlmostEqual(res_log.iloc[0], np.log(10.5), places=4)

        self.dialog.txt_expr.setPlainText("round(col('price') * 1.2345, 2)")
        res_round = self.dialog._evaluate()
        self.assertIsNotNone(res_round)
        self.assertAlmostEqual(res_round.iloc[0], round(10.5 * 1.2345, 2), places=2)

    def test_safe_decimal_constructor(self):
        """Decimal('1.2') * col('price')."""
        self.dialog.txt_expr.setPlainText("Decimal('1.2') * col('price')")
        result = self.dialog._evaluate()
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.iloc[0], 12.6, places=4)

    def test_to_numeric_helper(self):
        """to_numeric(col('raw_currency')) * 1.2 strips currency symbols and commas."""
        self.dialog.txt_expr.setPlainText("to_numeric(col('raw_currency')) * 1.2")
        result = self.dialog._evaluate()
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.iloc[0], 1200.50 * 1.2, places=2)
        self.assertAlmostEqual(result.iloc[1], 450.00 * 1.2, places=2)
        self.assertAlmostEqual(result.iloc[2], 10.00 * 1.2, places=2)
        self.assertTrue(pd.isna(result.iloc[3]))

    def test_where_conditional_helper(self):
        """where(col('price') >= 15, 'High', 'Low')."""
        self.dialog.txt_expr.setPlainText("where(col('price') >= 15, 'High', 'Low')")
        result = self.dialog._evaluate()
        self.assertIsNotNone(result)
        self.assertEqual(result.iloc[0], "Low")
        self.assertEqual(result.iloc[1], "High")
        self.assertEqual(result.iloc[2], "High")

    def test_coalesce_helper(self):
        """coalesce(col('price'), 0)."""
        self.dialog.txt_expr.setPlainText("coalesce(col('price'), 0)")
        result = self.dialog._evaluate()
        self.assertIsNotNone(result)
        self.assertEqual(result.iloc[3], 0)

    def test_string_broadcast(self):
        """Returning a constant string broadcasts to all rows instead of splitting characters."""
        self.dialog.txt_expr.setPlainText("'constant_status'")
        result = self.dialog._evaluate()
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 4)
        for v in result:
            self.assertEqual(v, "constant_status")

    def test_table_model_decimal_support(self):
        """Table model right-aligns decimal, calculates stats, and handles cell editing."""
        model = ParquetTableModel(self.df)

        # Check numeric alignment for Decimal column (price is column 0)
        align = model.data(model.index(0, 0), Qt.ItemDataRole.TextAlignmentRole)
        self.assertEqual(align, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))

        # Check tooltip says decimal
        tooltip = model.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
        self.assertIn("decimal", tooltip)

        # Check stats computation
        indexes = [model.index(0, 0), model.index(1, 0), model.index(2, 0)]
        stats = model.compute_stats(indexes)
        self.assertTrue(stats["is_numeric"])
        self.assertAlmostEqual(stats["sum"], 10.50 + 20.00 + 15.75, places=2)

        # Check cell editing keeps Decimal type
        success = model.setData(model.index(0, 0), "99.95", Qt.ItemDataRole.EditRole)
        self.assertTrue(success)
        edited_val = model._df.iat[0, 0]
        self.assertIsInstance(edited_val, Decimal)
        self.assertEqual(edited_val, Decimal("99.95"))

    def test_table_model_decimal_condition_filtering(self):
        """Filter condition price >= 15.0 on decimal column."""
        model = ParquetTableModel(self.df)
        model.set_filter("price", {
            "type": "condition",
            "op": ">=",
            "val1": "15.0",
        })
        # Prices are [10.50, 20.00, 15.75, None] -> 20.00 and 15.75 match
        self.assertEqual(model.get_total_filtered_rows(), 2)

    def test_parquet_saving_with_decimal_schema(self):
        """ParquetHandler preserves pyarrow decimal128 type when writing modified/computed float series."""
        schema = pa.schema([
            pa.field("price", pa.decimal128(10, 2)),
            pa.field("qty", pa.int32()),
        ])
        tbl = pa.Table.from_arrays([
            pa.array([Decimal("10.50"), Decimal("20.00"), None], type=pa.decimal128(10, 2)),
            pa.array([2, 5, 1], type=pa.int32()),
        ], schema=schema)

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "test.parquet")
            pq.write_table(tbl, file_path)

            loaded_df, loaded_schema, meta = ParquetHandler.read_parquet(file_path)

            # Apply formula: price * 1.2 (produces float series)
            loaded_df["price"] = loaded_df["price"].astype(float) * 1.2

            # Write back using original schema
            dest_path = os.path.join(tmp_dir, "saved.parquet")
            write_success = ParquetHandler.write_parquet(loaded_df, dest_path, original_schema=loaded_schema)
            self.assertTrue(write_success)

            # Read back and verify the decimal type and quantized values
            reloaded_df, reloaded_schema, _ = ParquetHandler.read_parquet(dest_path)
            field = reloaded_schema.field("price")
            self.assertTrue(pa.types.is_decimal(field.type))
            self.assertEqual(field.type.scale, 2)
            self.assertEqual(reloaded_df["price"].iloc[0], Decimal("12.60"))
            self.assertEqual(reloaded_df["price"].iloc[1], Decimal("24.00"))
            self.assertTrue(pd.isna(reloaded_df["price"].iloc[2]))


if __name__ == "__main__":
    unittest.main()
