from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)


class PageHeader(QWidget):
    def __init__(self, title: str, description: str = "") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        if description:
            label = QLabel(description)
            label.setWordWrap(True)
            layout.addWidget(label)


class StateBanner(QFrame):
    COLORS = {"loading": "#eaf4fb", "empty": "#f1f3f4", "success": "#e8f5ec", "error": "#fdecea"}

    def __init__(self) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        self.label = QLabel()
        self.label.setWordWrap(True)
        row.addWidget(self.label)
        self.hide()

    def show_state(self, state: str, text: str) -> None:
        color = self.COLORS.get(state, self.COLORS["empty"])
        self.setStyleSheet(f"QFrame {{ background: {color}; border: 1px solid #b9c5cc; border-radius: 5px; }}")
        self.label.setText(text)
        self.show()


def make_button(text: str, primary: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setMinimumHeight(40)
    button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    if primary:
        button.setObjectName("primary")
    return button


def make_table(headers: list[str], rows: list[list[str]]) -> QTableWidget:
    table = QTableWidget(len(rows), len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.verticalHeader().setDefaultSectionSize(34)
    table.verticalHeader().setVisible(False)
    for row_index, values in enumerate(rows):
        for column_index, value in enumerate(values):
            table.setItem(row_index, column_index, QTableWidgetItem(value))
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setSectionResizeMode(0, table.horizontalHeader().ResizeMode.ResizeToContents)
    if len(headers) > 1:
        table.horizontalHeader().setSectionResizeMode(1, table.horizontalHeader().ResizeMode.Stretch)
    return table

