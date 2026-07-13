from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPlainTextEdit,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from taipei_elearn.support.enrollment_keywords import EnrollmentKeywordRepository
from taipei_elearn.ui.widgets import PageHeader, StateBanner, make_button, make_table


class EnrollmentPage(QWidget):
    search_requested = Signal(object)
    add_to_pocket_requested = Signal(object)
    enroll_all_requested = Signal()

    def __init__(self, config_file: Path | None = None) -> None:
        super().__init__()
        self.keyword_repository = EnrollmentKeywordRepository(
            config_file or Path("settings.json")
        )
        self.keywords = self.keyword_repository.load()
        self._courses = []

        layout = QVBoxLayout(self)
        layout.addWidget(PageHeader(
            "批次選課",
            "每個關鍵字最多搜尋 5 門未報名且認證時數大於 0 的課程，再批次加入選課口袋。",
        ))
        self.banner = StateBanner()
        self.banner.show_state("empty", "請先開啟 Chrome 並確認已登入，再搜尋全部常用關鍵字。")
        layout.addWidget(self.banner)

        self.keyword_label = QLabel()
        self.keyword_label.setWordWrap(True)
        layout.addWidget(self.keyword_label)
        self._update_keyword_label()

        self.table = make_table(
            ["勾選", "符合關鍵字", "課程名稱", "認證時數", "課程 ID", "平台狀態", "處理結果"],
            [],
        )
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.buttons = {}
        for text in (
            "管理常用關鍵字", "搜尋全部關鍵字", "加入選課口袋", "選課口袋全部報名",
        ):
            button = make_button(text, text in {"搜尋全部關鍵字", "加入選課口袋"})
            self.buttons[text] = button
            actions.addWidget(button)
        self.buttons["加入選課口袋"].setEnabled(False)
        self.buttons["管理常用關鍵字"].clicked.connect(self._manage_keywords)
        self.buttons["搜尋全部關鍵字"].clicked.connect(self._request_search)
        self.buttons["加入選課口袋"].clicked.connect(self._request_add_to_pocket)
        self.buttons["選課口袋全部報名"].clicked.connect(self._request_enroll_all)
        actions.addStretch()
        layout.addLayout(actions)

    def _manage_keywords(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("管理常用選課關鍵字")
        dialog.resize(480, 420)
        layout = QVBoxLayout(dialog)
        hint = QLabel("每行一個關鍵字；重複項目會自動移除。")
        layout.addWidget(hint)
        editor = QPlainTextEdit()
        editor.setPlainText("\n".join(self.keywords))
        layout.addWidget(editor, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.keywords = self.keyword_repository.save(editor.toPlainText().splitlines())
        except ValueError as exc:
            self.show_error(str(exc))
            return
        self._update_keyword_label()
        self.banner.show_state("success", f"已保存 {len(self.keywords)} 個常用關鍵字。")

    def _update_keyword_label(self) -> None:
        self.keyword_label.setText(
            f"常用關鍵字（{len(self.keywords)}）：" + "、".join(self.keywords)
        )

    def _request_search(self) -> None:
        if not self.keywords:
            self.show_error("請先新增常用關鍵字。")
            return
        self._courses = []
        self.table.setRowCount(0)
        self._set_busy(True)
        self.banner.show_state("loading", "正在批次搜尋常用關鍵字…")
        self.search_requested.emit(list(self.keywords))

    def show_search_result(self, result) -> None:
        self._courses = list(result.courses)
        self.table.setRowCount(len(self._courses))
        for row, course in enumerate(self._courses):
            values = [
                "", "、".join(course.matched_keywords), course.title,
                course.certification_text, course.course_id,
                course.site_status, "待處理" if course.can_add else course.site_status,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0 and course.can_add:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked)
                if not course.can_add:
                    item.setForeground(QColor("#6b7280"))
                    item.setBackground(QColor("#f1f3f4"))
                self.table.setItem(row, column, item)
        available = sum(course.can_add for course in self._courses)
        self._set_busy(False)
        self.buttons["加入選課口袋"].setEnabled(available > 0)
        self.banner.show_state(
            "success",
            f"已搜尋 {len(result.keywords)} 個關鍵字、{result.pages_scanned} 頁，"
            f"每個關鍵字最多 5 門，去重後可加入 {available} 門。請取消不需要的課程。",
        )

    def selected_courses(self):
        selected = []
        for row, course in enumerate(self._courses):
            item = self.table.item(row, 0)
            if course.can_add and item and item.checkState() == Qt.CheckState.Checked:
                selected.append(course)
        return selected

    def _request_add_to_pocket(self) -> None:
        selected = self.selected_courses()
        if not selected:
            self.show_error("請至少勾選一門可加入的課程。")
            return
        self._set_busy(True)
        self.banner.show_state("loading", f"正在將 {len(selected)} 門課程加入選課口袋…")
        self.add_to_pocket_requested.emit(selected)

    def show_pocket_add_result(self, result) -> None:
        by_id = {item.course_id: item for item in result.results}
        for row, course in enumerate(self._courses):
            item = by_id.get(course.course_id)
            if item:
                self.table.item(row, 6).setText(item.message)
                if item.success:
                    self.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
        failures = len(result.results) - result.success_count
        self._set_busy(False)
        self.buttons["加入選課口袋"].setEnabled(bool(self.selected_courses()))
        state = "success" if failures == 0 else "error"
        self.banner.show_state(
            state,
            f"已加入選課口袋 {result.success_count}/{len(result.results)} 門。"
            f"{' 失敗 ' + str(failures) + ' 門，請查看處理結果。' if failures else ' 可按「選課口袋全部報名」。'}",
        )

    def _request_enroll_all(self) -> None:
        self._set_busy(True)
        self.banner.show_state("loading", "正在進入選課口袋並執行全部報名…")
        self.enroll_all_requested.emit()

    def show_enroll_result(self, result) -> None:
        self._set_busy(False)
        state = "success" if result.success else "error"
        self.banner.show_state(state, f"選課口袋全部報名：{result.message}")

    def show_progress(self, message: str) -> None:
        self.banner.show_state("loading", message)

    def show_error(self, message: str) -> None:
        self._set_busy(False)
        self.buttons["加入選課口袋"].setEnabled(bool(self.selected_courses()))
        self.banner.show_state("error", message)

    def _set_busy(self, busy: bool) -> None:
        self.buttons["管理常用關鍵字"].setEnabled(not busy)
        self.buttons["搜尋全部關鍵字"].setEnabled(not busy)
        self.buttons["加入選課口袋"].setEnabled(
            not busy and bool(self.selected_courses())
        )
        self.buttons["選課口袋全部報名"].setEnabled(not busy)
