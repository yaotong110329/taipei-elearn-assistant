from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QRadioButton, QTableWidgetItem, QVBoxLayout, QWidget,
)

from taipei_elearn.core.learning_record_scanner import ScanResult, format_duration, with_extra_hours
from taipei_elearn.ui.widgets import PageHeader, StateBanner, make_button, make_table


class LearningPage(QWidget):
    scan_requested = Signal()
    records_requested = Signal()
    start_requested = Signal(object)
    pause_requested = Signal()
    skip_requested = Signal()
    stop_requested = Signal()
    time_reached = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(PageHeader("學習紀錄／上課", "掃描學習紀錄並依序執行已勾選課程。"))
        self.banner = StateBanner()
        self.banner.show_state("empty", "登入後會自動選擇未完成、更新課程並改為每頁 50 筆，再按「開始掃描」。")
        layout.addWidget(self.banner)
        self.progress_label = QLabel("目前：尚未開始")
        self.progress_label.setWordWrap(True)
        self.progress_label.setObjectName("courseProgress")
        layout.addWidget(self.progress_label)
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self._tick_countdown)
        self._remaining_seconds = 0
        self._current_progress = {}
        self._time_reached_emitted = False
        self.table = make_table(
            ["勾選", "課程名稱", "狀態", "原始認證時數", "已上課", "所需時數", "剩餘", "測驗", "執行狀態"],
            [],
        )
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.buttons = {}
        for text in ("開始掃描", "回到學習紀錄", "✏️ 補正", "開始上課", "暫停", "跳過", "停止"):
            button = make_button(text, text == "開始上課")
            button.setEnabled(text in {"開始掃描", "回到學習紀錄"})
            self.buttons[text] = button
            actions.addWidget(button)
        self.buttons["開始掃描"].clicked.connect(self.scan_requested)
        self.buttons["回到學習紀錄"].clicked.connect(self.records_requested)
        self.buttons["✏️ 補正"].clicked.connect(self._open_correction_dialog)
        self.buttons["✏️ 補正"].setEnabled(False)
        self.buttons["開始上課"].clicked.connect(self._emit_start)
        self.buttons["暫停"].clicked.connect(self.pause_requested)
        self.buttons["跳過"].clicked.connect(self.skip_requested)
        self.buttons["停止"].clicked.connect(self.stop_requested)
        actions.addStretch()
        layout.addLayout(actions)

    def set_busy(self, busy: bool) -> None:
        self.buttons["開始掃描"].setEnabled(not busy)
        if busy:
            self.banner.show_state("loading", "正在掃描未完成課程… Chrome 可能短暫出現在前景。")

    def show_result(self, result: ScanResult) -> None:
        self._records = list(result.records)
        self._extra_hours = {
            key: value for key, value in getattr(self, "_extra_hours", {}).items()
            if any(self._record_key(record) == key for record in self._records)
        }
        self.table.setRowCount(len(result.records))
        for row_index, record in enumerate(result.records):
            record = self._corrected(record)
            values = [
                "",
                record.name,
                record.status_text,
                record.raw_certification_hours,
                f"{record.raw_studied_time}（{record.studied_seconds} 秒）",
                format_duration(record.required_seconds),
                format_duration(record.remaining_seconds),
                record.quiz_score_text or "-",
                "待執行" if not record.completed else "已完成",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0 and not record.completed:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked)
                if record.completed:
                    item.setForeground(QColor("#6b7280"))
                    item.setBackground(QColor("#f1f3f4"))
                self.table.setItem(row_index, column, item)
        failures = len(result.failures)
        state = "success" if not failures else "error"
        detail = f"已掃描 {result.pages_scanned} 頁、{len(result.records)} 門課程。"
        if failures:
            detail += f" {failures} 列無法解析，詳細特徵已寫入日誌。"
        self.banner.show_state(state, detail)
        self.buttons["開始上課"].setEnabled(bool(result.records))
        self.buttons["✏️ 補正"].setEnabled(bool(result.records))

    def selected_records(self):
        selected = []
        for row, record in enumerate(getattr(self, "_records", [])):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected.append(self._corrected(record))
        return selected

    def _emit_start(self) -> None:
        self.start_requested.emit(self.selected_records())

    def show_course_started(self, result: dict) -> None:
        self._time_reached_emitted = False
        self.banner.show_state(
            "success",
            f"執行 {result.get('position', 1)} / {result.get('total', 1)}：{result['course']}\n"
            f"教材：{result['material']}"
            f"{'｜影片已開始播放' if result.get('media_started') else ''}"
            f"{'｜換課測試：15 秒' if result.get('runtime_override') else ''}",
        )
        self.buttons["開始上課"].setEnabled(False)
        self.buttons["暫停"].setEnabled(True)
        self.buttons["跳過"].setEnabled(True)
        self.buttons["停止"].setEnabled(True)
        self._current_progress = dict(result)
        self._remaining_seconds = max(0, int(result.get("remaining_seconds") or 0))
        self._update_progress_label()
        if self._remaining_seconds > 0:
            self.countdown_timer.start()
        else:
            self.countdown_timer.stop()
            self._emit_time_reached()

    def show_queue_state(self, state: str, detail: str = "") -> None:
        self.banner.show_state("empty", f"{state}{chr(10) + detail if detail else ''}")
        stopped = state in {"已停止", "全部完成"}
        self.buttons["開始上課"].setEnabled(stopped and bool(getattr(self, "_records", [])))
        self.buttons["暫停"].setEnabled(not stopped)
        self.buttons["跳過"].setEnabled(not stopped)
        self.buttons["停止"].setEnabled(not stopped)
        self.buttons["暫停"].setText("繼續" if state == "已暫停" else "暫停")
        if state == "已暫停":
            self.countdown_timer.stop()
        elif state == "執行中" and self._remaining_seconds > 0:
            self.countdown_timer.start()
        elif stopped:
            self.countdown_timer.stop()
        self._update_progress_label(state)

    def _tick_countdown(self) -> None:
        if self._remaining_seconds > 0:
            self._remaining_seconds -= 1
        if self._remaining_seconds <= 0:
            self.countdown_timer.stop()
            self._emit_time_reached()
        self._update_progress_label()

    def _update_progress_label(self, state: str = "") -> None:
        if not self._current_progress:
            self.progress_label.setText("目前：尚未開始")
            return
        position = self._current_progress.get("position", 1)
        total = self._current_progress.get("total", 1)
        course = self._current_progress.get("course", "")
        countdown = (
            "本次上課時數已完成，準備下一門"
            if self._remaining_seconds <= 0
            else f"剩餘 {format_duration(self._remaining_seconds)}"
        )
        state_text = f"｜{state}" if state else ""
        self.progress_label.setText(f"目前第 {position} 門／共 {total} 門{state_text}\n{course}\n{countdown}")

    def _emit_time_reached(self) -> None:
        if self._time_reached_emitted:
            return
        self._time_reached_emitted = True
        self.time_reached.emit()

    def _open_correction_dialog(self) -> None:
        row = self.table.currentRow()
        if row < 0 and getattr(self, "_records", []):
            row = 0
            self.table.selectRow(0)
        if row < 0:
            self.show_error("請先選取一門課程。")
            return
        record = self._records[row]
        key = self._record_key(record)
        current = self._extra_hours.get(key, 0.0)
        dialog = QDialog(self)
        dialog.setWindowTitle("額外時數補正")
        layout = QVBoxLayout(dialog)
        title = QLabel(record.name)
        title.setWordWrap(True)
        layout.addWidget(title)
        no_correction = QRadioButton("不補正（預設）")
        correction = QRadioButton("補正：")
        values = QComboBox()
        values.setEditable(True)
        values.addItems(["+0.5", "+1", "+1.5", "+2", "+2.5", "+3"])
        values.setCurrentText(f"+{current:g}" if current else "+0.5")
        row_layout = QHBoxLayout()
        row_layout.addWidget(correction)
        row_layout.addWidget(values)
        no_correction.setChecked(current == 0)
        correction.setChecked(current > 0)
        layout.addWidget(no_correction)
        layout.addLayout(row_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        extra = 0.0
        if correction.isChecked():
            try:
                extra = float(values.currentText().strip().lstrip("+"))
            except ValueError:
                self.show_error("補正值必須是數字，例如 +0.5。")
                return
            if extra < 0:
                self.show_error("補正值不可小於 0。")
                return
        self._extra_hours[key] = extra
        corrected = self._corrected(record)
        self.table.item(row, 5).setText(format_duration(corrected.required_seconds))
        self.table.item(row, 6).setText(format_duration(corrected.remaining_seconds))
        text = "不補正" if extra == 0 else f"補正 +{extra:g} 小時"
        self.banner.show_state("success", f"{record.name}\n{text}")

    def _corrected(self, record):
        return with_extra_hours(record, self._extra_hours.get(self._record_key(record), 0.0))

    @staticmethod
    def _record_key(record) -> str:
        return record.course_id or record.course_url or record.name

    def show_error(self, message: str) -> None:
        self.banner.show_state("error", message)
