"""
Custom Cell Item Delegate for Parquet Table View.
Provides spacious, high-contrast, crystal-clear inline text editing.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect
from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit, QWidget, QStyleOptionViewItem
from PySide6.QtGui import QColor, QFont


class ParquetCellDelegate(QStyledItemDelegate):
    """Custom item delegate with enhanced geometry and styling for inline cell editing."""

    def __init__(self, parent=None):
        super().__init__(parent)

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index) -> QWidget:
        editor = QLineEdit(parent)
        editor.setStyleSheet("""
            QLineEdit {
                background-color: #262833;
                color: #ffffff;
                border: 2px solid #107c41;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 13px;
                font-weight: 500;
                selection-background-color: #107c41;
                selection-color: #ffffff;
            }
        """)
        return editor

    def setEditorData(self, editor: QWidget, index):
        if isinstance(editor, QLineEdit):
            val = index.model().data(index, Qt.ItemDataRole.EditRole)
            text_val = "" if val is None else str(val)
            editor.setText(text_val)
            # Select all text so user can immediately type over or edit
            editor.selectAll()

    def setModelData(self, editor: QWidget, model, index):
        if isinstance(editor, QLineEdit):
            new_text = editor.text()
            model.setData(index, new_text, Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor: QWidget, option: QStyleOptionViewItem, index):
        # Provide spacious editing box without clipping
        geom = option.rect
        # Give extra height and slight margin
        min_height = max(geom.height(), 28)
        adjusted_rect = QRect(geom.x(), geom.y() - 1, geom.width(), min_height + 2)
        editor.setGeometry(adjusted_rect)
