"""
Formula / Expression Builder Dialog for Parquet Editor.
Allows the user to apply a pandas-style expression to compute a new column
or overwrite an existing one. Uses a safe eval sandbox.
"""
from __future__ import annotations

from typing import Optional, List
import traceback
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QDialogButtonBox, QTextEdit,
    QSplitter, QListWidget, QListWidgetItem, QFrame,
)


# Safe built-ins available inside expressions
_SAFE_NAMESPACE_KEYS = ["abs", "round", "min", "max", "len", "str", "int", "float", "bool"]


def _build_safe_ns(df: pd.DataFrame) -> dict:
    """Build the evaluation namespace with column references and safe pandas funcs."""
    import numpy as np
    ns: dict = {"df": df, "pd": pd, "np": np}
    # Convenience: col('name') shortcut
    ns["col"] = lambda name: df[name]
    # Row index as a series
    ns["index"] = df.index.to_series()
    # Safe builtins
    for k in _SAFE_NAMESPACE_KEYS:
        ns[k] = __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k, None)
    return ns


FUNCTION_HINTS = [
    ("col('name')",         "Reference a column by name"),
    ("col('a') + col('b')", "Add two columns"),
    ("col('price') * 1.2",  "Scalar multiply"),
    ("col('name').str.upper()", "String to uppercase"),
    ("col('name').str.strip()", "Strip whitespace"),
    ("col('val').clip(0, 100)", "Clamp values between 0 and 100"),
    ("col('a').fillna(0)",  "Fill nulls with 0"),
    ("col('a').isna()",     "Boolean: is null?"),
    ("pd.to_datetime(col('date_str'))", "Parse datetime string"),
    ("np.log1p(col('amount'))", "Natural log(1+x)"),
    ("col('cat').map({'A': 1, 'B': 2})", "Map categorical to int"),
]


class FormulaBuilderDialog(QDialog):
    """Dialog to construct and preview a column formula before applying it."""

    def __init__(self, df: pd.DataFrame, existing_col: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Column Formula / Expression Builder")
        self.resize(740, 540)
        self._df = df
        self._result_series: Optional[pd.Series] = None
        self._target_col: Optional[str] = None

        layout = QVBoxLayout(self)

        # --- Target column ---
        top = QHBoxLayout()
        top.addWidget(QLabel("Target Column:"))
        self.cmb_target = QComboBox()
        self.cmb_target.setEditable(True)
        self.cmb_target.addItem("[New Column…]")
        for c in df.columns:
            self.cmb_target.addItem(str(c))
        if existing_col and existing_col in [str(c) for c in df.columns]:
            self.cmb_target.setCurrentText(existing_col)
        self.cmb_target.setMinimumWidth(220)
        top.addWidget(self.cmb_target)

        self.txt_new_col = QLineEdit()
        self.txt_new_col.setPlaceholderText("New column name (if [New Column…] selected)")
        top.addWidget(self.txt_new_col)
        top.addStretch(1)
        layout.addLayout(top)

        # --- Splitter: Left hints, Right editor ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: helper panel
        left = QFrame()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("📚 Column Names (double-click to insert):"))
        self.lst_cols = QListWidget()
        self.lst_cols.setMaximumWidth(200)
        for c in df.columns:
            it = QListWidgetItem(str(c))
            it.setToolTip(f"dtype: {df[c].dtype}")
            self.lst_cols.addItem(it)
        self.lst_cols.itemDoubleClicked.connect(self._insert_col_ref)
        left_layout.addWidget(self.lst_cols)

        left_layout.addWidget(QLabel("🔧 Function Hints (double-click):"))
        self.lst_hints = QListWidget()
        self.lst_hints.setMaximumWidth(200)
        for expr, desc in FUNCTION_HINTS:
            it = QListWidgetItem(expr)
            it.setToolTip(desc)
            self.lst_hints.addItem(it)
        self.lst_hints.itemDoubleClicked.connect(self._insert_hint)
        left_layout.addWidget(self.lst_hints)
        splitter.addWidget(left)

        # Right: expression + preview
        right = QFrame()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Expression (Python / Pandas):"))
        self.txt_expr = QTextEdit()
        self.txt_expr.setPlaceholderText("Example:\n  col('price') * col('quantity')\n\nor use df directly:\n  df['price'] * df['quantity']")
        self.txt_expr.setMinimumHeight(120)
        self.txt_expr.setMaximumHeight(160)
        right_layout.addWidget(self.txt_expr)

        btn_preview = QPushButton("▶ Preview (first 10 rows)")
        btn_preview.clicked.connect(self._run_preview)
        right_layout.addWidget(btn_preview)

        right_layout.addWidget(QLabel("Preview:"))
        self.txt_preview = QTextEdit()
        self.txt_preview.setReadOnly(True)
        self.txt_preview.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        right_layout.addWidget(self.txt_preview)
        splitter.addWidget(right)

        splitter.setSizes([200, 520])
        layout.addWidget(splitter)

        # Status
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.lbl_status)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._on_apply)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _insert_col_ref(self, item: QListWidgetItem):
        self.txt_expr.insertPlainText(f"col('{item.text()}')")

    def _insert_hint(self, item: QListWidgetItem):
        self.txt_expr.insertPlainText(item.text())

    def _evaluate(self) -> Optional[pd.Series]:
        expr = self.txt_expr.toPlainText().strip()
        if not expr:
            self.lbl_status.setText("⚠️ Expression is empty.")
            return None
        ns = _build_safe_ns(self._df)
        try:
            result = eval(expr, {"__builtins__": {}}, ns)  # noqa: S307
            if isinstance(result, pd.Series):
                return result.reset_index(drop=True)
            elif hasattr(result, "__len__") and len(result) == len(self._df):
                return pd.Series(result, index=self._df.index)
            else:
                # Scalar — broadcast
                return pd.Series([result] * len(self._df), index=self._df.index)
        except Exception as ex:
            self.lbl_status.setText(f"❌ Error: {ex}")
            return None

    def _run_preview(self):
        result = self._evaluate()
        if result is None:
            return
        preview = result.head(10).to_string()
        self.txt_preview.setPlainText(preview)
        self.lbl_status.setText(f"✅ Preview OK — dtype: {result.dtype}, length: {len(result):,}")

    def _on_apply(self):
        result = self._evaluate()
        if result is None:
            return

        target = self.cmb_target.currentText()
        if target == "[New Column…]":
            name = self.txt_new_col.text().strip()
            if not name:
                self.lbl_status.setText("⚠️ Provide a new column name.")
                return
            self._target_col = name
        else:
            self._target_col = target

        self._result_series = result
        self.lbl_status.setText(f"✅ Ready to apply to '{self._target_col}'.")
        self.accept()

    def get_result(self):
        """Returns (target_col_name, pd.Series) or (None, None) if cancelled."""
        return self._target_col, self._result_series
