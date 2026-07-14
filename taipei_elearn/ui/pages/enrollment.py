from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QSpinBox,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from taipei_elearn.support.enrollment_keywords import (
    EnrollmentKeywordRepository, EnrollmentKeywordSetting,
)
from taipei_elearn.ui.widgets import PageHeader, StateBanner, make_button, make_table


class CollapsiblePanel(QWidget):
    expanded_changed = Signal(bool)

    def __init__(self, title: str, expanded: bool) -> None:
        super().__init__()
        self.title = title
        self._expanded = not expanded
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.header_button = QPushButton()
        self.header_button.setCheckable(True)
        self.header_button.setMinimumHeight(38)
        self.header_button.setStyleSheet(
            "QPushButton { text-align: left; padding: 7px 10px; font-weight: 700; "
            "background: #eef3f6; border: 1px solid #b9c5cc; border-radius: 5px; }"
            "QPushButton:hover { background: #e2edf3; }"
        )
        self.content = QWidget()
        layout.addWidget(self.header_button)
        layout.addWidget(self.content, 1)
        self.header_button.clicked.connect(self.set_expanded)
        self.set_expanded(expanded, emit_signal=False)

    @property
    def expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool, emit_signal: bool = True) -> None:
        expanded = bool(expanded)
        changed = expanded != self._expanded
        self._expanded = expanded
        self.header_button.setChecked(expanded)
        self.header_button.setText(f"{'▼' if expanded else '▶'}  {self.title}")
        self.content.setVisible(expanded)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding if expanded else QSizePolicy.Policy.Fixed,
        )
        self.updateGeometry()
        if changed and emit_signal:
            self.expanded_changed.emit(expanded)


class EnrollmentPage(QWidget):
    search_requested = Signal(object)
    add_to_pocket_requested = Signal(object)
    enroll_all_requested = Signal()

    def __init__(self, config_file: Path | None = None) -> None:
        super().__init__()
        self.keyword_repository = EnrollmentKeywordRepository(
            config_file or Path("settings.json")
        )
        self.keyword_settings = self.keyword_repository.load()
        panel_state = self.keyword_repository.load_panel_state()
        self._loading_keywords = False
        self._courses = []

        layout = QVBoxLayout(self)
        self.main_layout = layout
        layout.addWidget(PageHeader(
            "批次選課",
            "勾選本次要搜尋的關鍵字，並為每個關鍵字設定 1～5 門課程。",
        ))
        self.banner = StateBanner()
        self.banner.show_state("empty", "請先開啟 Chrome 並確認已登入，再搜尋已勾選關鍵字。")
        layout.addWidget(self.banner)

        self.keyword_panel = CollapsiblePanel(
            "選課關鍵字", panel_state["keywords_expanded"]
        )
        keyword_layout = QVBoxLayout(self.keyword_panel.content)
        keyword_layout.setContentsMargins(0, 0, 0, 0)
        self.keyword_table = make_table(
            ["搜尋", "關鍵字", "選課數量", "操作"], []
        )
        self.keyword_table.setMinimumHeight(220)
        self.keyword_table.horizontalHeader().setSectionResizeMode(
            2, self.keyword_table.horizontalHeader().ResizeMode.ResizeToContents
        )
        self.keyword_table.horizontalHeader().setSectionResizeMode(
            3, self.keyword_table.horizontalHeader().ResizeMode.ResizeToContents
        )
        self.keyword_table.itemChanged.connect(self._keyword_item_changed)
        keyword_layout.addWidget(self.keyword_table, 1)

        add_row = QHBoxLayout()
        self.new_keyword_input = QLineEdit()
        self.new_keyword_input.setPlaceholderText("輸入一個新關鍵字")
        self.new_keyword_input.returnPressed.connect(self._add_keyword)
        self.new_keyword_limit = QSpinBox()
        self.new_keyword_limit.setRange(1, 5)
        self.new_keyword_limit.setValue(5)
        self.new_keyword_limit.setPrefix("選課數量 ")
        self.add_keyword_button = make_button("新增")
        self.add_keyword_button.clicked.connect(self._add_keyword)
        add_row.addWidget(self.new_keyword_input, 1)
        add_row.addWidget(self.new_keyword_limit)
        add_row.addWidget(self.add_keyword_button)
        keyword_layout.addLayout(add_row)
        self._render_keyword_rows()
        layout.addWidget(self.keyword_panel)

        self.course_panel = CollapsiblePanel(
            "待選課程", panel_state["courses_expanded"]
        )
        course_layout = QVBoxLayout(self.course_panel.content)
        course_layout.setContentsMargins(0, 0, 0, 0)
        self.table = make_table(
            ["勾選", "符合關鍵字", "課程名稱", "認證時數", "課程 ID", "平台狀態", "處理結果"],
            [],
        )
        course_layout.addWidget(self.table, 1)
        layout.addWidget(self.course_panel)
        self.keyword_panel.expanded_changed.connect(self._panel_state_changed)
        self.course_panel.expanded_changed.connect(self._panel_state_changed)

        actions = QHBoxLayout()
        self.buttons = {}
        for text in (
            "搜尋已勾選關鍵字", "加入選課口袋", "選課口袋全部報名",
        ):
            button = make_button(text, text in {"搜尋已勾選關鍵字", "加入選課口袋"})
            self.buttons[text] = button
            actions.addWidget(button)
        self.buttons["加入選課口袋"].setEnabled(False)
        self.buttons["搜尋已勾選關鍵字"].clicked.connect(self._request_search)
        self.buttons["加入選課口袋"].clicked.connect(self._request_add_to_pocket)
        self.buttons["選課口袋全部報名"].clicked.connect(self._request_enroll_all)
        actions.addStretch()
        layout.addLayout(actions)
        self._update_panel_layout()

    @property
    def keywords(self) -> list[str]:
        return [item.keyword for item in self.keyword_settings]

    def _panel_state_changed(self, _expanded: bool) -> None:
        self._update_panel_layout()
        self.keyword_repository.save_panel_state(
            self.keyword_panel.expanded,
            self.course_panel.expanded,
        )

    def _update_panel_layout(self) -> None:
        keyword_weight = 1 if self.keyword_panel.expanded else 0
        course_weight = 1 if self.course_panel.expanded else 0
        if self.keyword_panel.expanded and self.course_panel.expanded:
            course_weight = 2
        self.main_layout.setStretchFactor(self.keyword_panel, keyword_weight)
        self.main_layout.setStretchFactor(self.course_panel, course_weight)

    def _render_keyword_rows(self) -> None:
        self._loading_keywords = True
        self.keyword_table.setRowCount(len(self.keyword_settings))
        for row, setting in enumerate(self.keyword_settings):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(
                Qt.CheckState.Checked if setting.enabled else Qt.CheckState.Unchecked
            )
            check.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.keyword_table.setItem(row, 0, check)

            name = QTableWidgetItem(setting.keyword)
            name.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.keyword_table.setItem(row, 1, name)

            course_limit = QSpinBox()
            course_limit.setRange(1, 5)
            course_limit.setValue(setting.course_limit)
            course_limit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            course_limit.valueChanged.connect(self._persist_keyword_table)
            self.keyword_table.setCellWidget(row, 2, course_limit)

            if setting.is_default:
                default_label = QLabel("預設")
                default_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.keyword_table.setCellWidget(row, 3, default_label)
            else:
                delete_button = QPushButton("刪除")
                delete_button.setMinimumHeight(28)
                delete_button.clicked.connect(
                    lambda _checked=False, keyword=setting.keyword: self._delete_keyword(keyword)
                )
                self.keyword_table.setCellWidget(row, 3, delete_button)
        self._loading_keywords = False

    def _keyword_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._persist_keyword_table()

    def _persist_keyword_table(self, *_args) -> None:
        if self._loading_keywords:
            return
        updated = []
        for row, setting in enumerate(self.keyword_settings):
            check = self.keyword_table.item(row, 0)
            spin = self.keyword_table.cellWidget(row, 2)
            updated.append(replace(
                setting,
                enabled=bool(check and check.checkState() == Qt.CheckState.Checked),
                course_limit=spin.value() if isinstance(spin, QSpinBox) else setting.course_limit,
            ))
        self.keyword_settings = self.keyword_repository.save(updated)

    def _add_keyword(self) -> None:
        keyword = self.new_keyword_input.text().strip()
        if not keyword:
            self.show_error("請輸入一個關鍵字。")
            return
        if keyword.casefold() in {item.keyword.casefold() for item in self.keyword_settings}:
            self.show_error(f"關鍵字「{keyword}」已存在，不可重複新增。")
            return
        self.keyword_settings.append(EnrollmentKeywordSetting(
            keyword=keyword,
            enabled=True,
            course_limit=self.new_keyword_limit.value(),
            is_default=False,
        ))
        self.keyword_settings = self.keyword_repository.save(self.keyword_settings)
        self._render_keyword_rows()
        self.new_keyword_input.clear()
        self.new_keyword_limit.setValue(5)
        self.banner.show_state("success", f"已新增並勾選關鍵字「{keyword}」。")

    def _delete_keyword(self, keyword: str) -> None:
        target = next(
            (item for item in self.keyword_settings if item.keyword.casefold() == keyword.casefold()),
            None,
        )
        if target is None:
            return
        if target.is_default:
            self.show_error("預設關鍵字不可刪除；可取消勾選停止本次搜尋。")
            return
        self.keyword_settings = self.keyword_repository.save([
            item for item in self.keyword_settings
            if item.keyword.casefold() != keyword.casefold()
        ])
        self._render_keyword_rows()
        self.banner.show_state("success", f"已刪除自訂關鍵字「{keyword}」。")

    def selected_keyword_settings(self) -> list[EnrollmentKeywordSetting]:
        return [item for item in self.keyword_settings if item.enabled]

    def _request_search(self) -> None:
        selected = self.selected_keyword_settings()
        if not selected:
            self.show_error("請至少勾選一個要搜尋的關鍵字。")
            return
        self._courses = []
        self.table.setRowCount(0)
        self._set_busy(True)
        self.banner.show_state("loading", "正在搜尋已勾選關鍵字…")
        self.search_requested.emit(selected)

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
            f"依各列設定數量去重後可加入 {available} 門。請取消不需要的課程。",
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
        self.keyword_table.setEnabled(not busy)
        self.new_keyword_input.setEnabled(not busy)
        self.new_keyword_limit.setEnabled(not busy)
        self.add_keyword_button.setEnabled(not busy)
        self.buttons["搜尋已勾選關鍵字"].setEnabled(not busy)
        self.buttons["加入選課口袋"].setEnabled(
            not busy and bool(self.selected_courses())
        )
        self.buttons["選課口袋全部報名"].setEnabled(not busy)
