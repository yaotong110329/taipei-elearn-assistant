from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from taipei_elearn.core.answer_parser import AnswerValidationError, parse_and_validate_answers
from taipei_elearn.core.quiz_extractor import QuizSnapshot
from taipei_elearn.core.quiz_prompt_builder import build_quiz_prompt
from taipei_elearn.ui.widgets import PageHeader, StateBanner, make_button, make_table


class QuizPage(QWidget):
    scan_requested = Signal()
    start_requested = Signal(object)
    fill_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.snapshot: QuizSnapshot | None = None
        self._candidates = []
        layout = QVBoxLayout(self)
        layout.addWidget(PageHeader(
            "測驗答題",
            "掃描後勾選課程並開始答題。每門只在複製題目給 AI、貼回答案時等待，其餘自動完成。",
        ))
        self.banner = StateBanner()
        self.banner.show_state("empty", "請先在「學習紀錄／上課」完成掃描。")
        layout.addWidget(self.banner)

        actions = QHBoxLayout()
        self.scan_button = make_button("掃描未答題課程", True)
        self.scan_button.clicked.connect(self._request_scan)
        self.start_button = make_button("開始答題", True)
        self.start_button.clicked.connect(self._request_start)
        self.start_button.setEnabled(False)
        self.question_count = QLabel("尚未開始")
        actions.addWidget(self.scan_button)
        actions.addWidget(self.start_button)
        actions.addWidget(self.question_count)
        actions.addStretch()
        layout.addLayout(actions)

        self.course_table = make_table(
            ["勾選", "課程名稱", "測驗成績", "閱讀時數", "狀態"], []
        )
        self.course_table.setMinimumHeight(150)
        layout.addWidget(self.course_table, 1)

        layout.addWidget(QLabel("目前步驟"))
        self.step_editor = QPlainTextEdit()
        self.step_editor.setReadOnly(True)
        self.step_editor.setPlaceholderText("開始答題後，這裡會顯示目前處理步驟。")
        self.step_editor.setMinimumHeight(180)
        layout.addWidget(self.step_editor, 1)

        answer_actions = QHBoxLayout()
        self.clipboard_button = make_button("從剪貼簿讀取送出答案", True)
        self.clipboard_button.clicked.connect(self._read_clipboard_and_submit)
        self.clipboard_button.setEnabled(False)
        answer_actions.addWidget(self.clipboard_button)
        answer_actions.addStretch()
        layout.addLayout(answer_actions)

    def _request_scan(self) -> None:
        self._candidates = []
        self.snapshot = None
        self.course_table.setRowCount(0)
        self.step_editor.clear()
        self._append_step("掃描未答題課程中")
        self.scan_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.banner.show_state("loading", "正在掃描有測驗項目、課程未完成且成績不是 100 分的課程…")
        self.scan_requested.emit()

    def show_candidates(self, result) -> None:
        self._candidates = list(result.candidates)
        self.snapshot = None
        self.course_table.setRowCount(len(self._candidates))
        for row, candidate in enumerate(self._candidates):
            values = [
                "", candidate.course_name, candidate.score_text or "-",
                candidate.raw_studied_time or "0秒", candidate.state,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0 and candidate.eligible:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked)
                if not candidate.eligible:
                    item.setForeground(QColor("#6b7280"))
                    item.setBackground(QColor("#f1f3f4"))
                self.course_table.setItem(row, column, item)
        eligible = sum(candidate.eligible for candidate in self._candidates)
        blocked = len(self._candidates) - eligible
        detail = f"找到 {len(self._candidates)} 門待答題課程，可進入 {eligible} 門。"
        if blocked:
            detail += f" {blocked} 門閱讀時數為 0 或無法判斷，不能勾選進入測驗。"
        self.banner.show_state("success", detail)
        self._append_step(f"掃描完成：找到 {len(self._candidates)} 門待答題課程")
        self.question_count.setText("請勾選後開始答題")
        self.scan_button.setEnabled(True)
        self.start_button.setEnabled(eligible > 0)
        self.clipboard_button.setEnabled(False)

    def selected_candidates(self):
        selected = []
        for row, candidate in enumerate(self._candidates):
            item = self.course_table.item(row, 0)
            if candidate.eligible and item and item.checkState() == Qt.CheckState.Checked:
                selected.append(candidate)
        return selected

    def _request_start(self) -> None:
        selected = self.selected_candidates()
        if not selected:
            self.show_error("請至少勾選一門可進入測驗的課程。")
            return
        self.scan_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.step_editor.clear()
        self._append_step("進入第一門測驗")
        self.banner.show_state("loading", "正在進入第一門測驗並擷取題目…")
        self.start_requested.emit(selected)

    def show_snapshot(
        self, snapshot: QuizSnapshot, position: int = 0,
        total: int = 0, course: str = "",
    ) -> None:
        self.snapshot = snapshot
        queue_text = f"測驗 {position}/{total}" if total else "目前測驗"
        course_text = f"：{course}" if course else ""
        self._append_step(f"{queue_text}{course_text}")
        self._append_step("複製題目中")
        prompt = build_quiz_prompt(snapshot)
        QApplication.clipboard().setText(prompt)
        self._append_step("題目複製成功，等待 AI 答案")
        count_text = f"｜測驗 {position}/{total}" if total else ""
        self.question_count.setText(f"共 {len(snapshot.questions)} 題{count_text}")
        self.clipboard_button.setEnabled(True)
        self.banner.show_state(
            "success",
            f"{course + chr(10) if course else ''}已擷取並複製 {len(snapshot.questions)} 題。"
            "請貼給 AI，再將答案複製回來。",
        )
        QMessageBox.information(
            self,
            "題目複製成功",
            "題目複製成功，請貼給 AI（ChatGPT、Claude 等）。\n"
            "取得答案後，複製答案並回到本程式送出。",
        )

    def _read_clipboard_and_submit(self) -> None:
        if self.snapshot is None:
            self.show_error("尚未進入測驗。")
            return
        self._append_step("讀取剪貼簿答案")
        try:
            answers = parse_and_validate_answers(
                QApplication.clipboard().text(), self.snapshot
            )
        except AnswerValidationError as exc:
            self._append_step(f"答案格式錯誤：{exc}")
            self.banner.show_state("error", str(exc))
            return
        self.clipboard_button.setEnabled(False)
        self._append_step("送出答案中")
        self.banner.show_state(
            "loading", f"答案驗證通過，共 {len(answers)} 題。正在自動填入並送出…"
        )
        self.fill_requested.emit(answers)

    def show_submission(self, result) -> None:
        self._append_step("已送出")
        self._append_step(f"分數：{result.get('score') or '平台未顯示'}")
        if result.get("has_next"):
            self._append_step("下一門")

    def show_completed(self, count: int) -> None:
        self.snapshot = None
        self.scan_button.setEnabled(True)
        self.start_button.setEnabled(False)
        self.clipboard_button.setEnabled(False)
        self.question_count.setText("全部測驗已處理")
        self._append_step("全部測驗已處理")
        self.banner.show_state("success", f"最後一門已填入並送出 {count} 題，測驗佇列完成。")

    def show_error(self, message: str) -> None:
        self.scan_button.setEnabled(True)
        self.start_button.setEnabled(
            self.snapshot is None and bool(self.selected_candidates())
        )
        self.clipboard_button.setEnabled(self.snapshot is not None)
        self._append_step(f"錯誤：{message}")
        self.banner.show_state("error", message)

    def _append_step(self, text: str) -> None:
        self.step_editor.appendPlainText(text)
        scrollbar = self.step_editor.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
