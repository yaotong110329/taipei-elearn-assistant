from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QVBoxLayout, QWidget,
)

from taipei_elearn.core.answer_parser import AnswerValidationError, parse_and_validate_answers
from taipei_elearn.core.quiz_extractor import QuizSnapshot
from taipei_elearn.core.quiz_prompt_builder import build_quiz_prompt
from taipei_elearn.ui.widgets import PageHeader, StateBanner, make_button


class QuizPage(QWidget):
    scan_requested = Signal()
    extract_requested = Signal()
    fill_requested = Signal(object)
    next_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.snapshot: QuizSnapshot | None = None
        self.validated_answers: dict[int, tuple[str, ...]] | None = None
        layout = QVBoxLayout(self)
        layout.addWidget(PageHeader(
            "測驗答題",
            "支援單頁單選／多選。擷取後提示詞自動複製；答案驗證成功，確認後才填入。",
        ))
        self.banner = StateBanner()
        self.banner.show_state("empty", "請先在 Chrome 進入測驗作答頁。")
        layout.addWidget(self.banner)

        extract_row = QHBoxLayout()
        self.scan_button = make_button("掃描未測驗課程", True)
        self.scan_button.clicked.connect(self._request_scan)
        extract_row.addWidget(self.scan_button)
        self.extract_button = make_button("擷取目前測驗", True)
        self.extract_button.clicked.connect(self._request_extract)
        extract_row.addWidget(self.extract_button)
        self.question_count = QLabel("尚未擷取")
        extract_row.addWidget(self.question_count)
        extract_row.addStretch()
        layout.addLayout(extract_row)

        layout.addWidget(QLabel("AI 提示詞（擷取後自動複製）"))
        self.prompt_editor = QPlainTextEdit()
        self.prompt_editor.setReadOnly(True)
        self.prompt_editor.setPlaceholderText("題目與固定提示詞會顯示於此。")
        self.prompt_editor.setMinimumHeight(180)
        layout.addWidget(self.prompt_editor, 1)

        layout.addWidget(QLabel("貼上 AI 回傳答案"))
        self.answer_editor = QPlainTextEdit()
        self.answer_editor.setPlaceholderText("[[ANSWERS]]1=A;2=BD;3=C[[/ANSWERS]]")
        self.answer_editor.setMaximumHeight(100)
        layout.addWidget(self.answer_editor)

        buttons = QHBoxLayout()
        self.clipboard_button = make_button("從剪貼簿讀取")
        self.clipboard_button.clicked.connect(self._read_clipboard)
        self.validate_button = make_button("驗證答案")
        self.validate_button.clicked.connect(self._validate)
        self.fill_button = make_button("確認並填入", True)
        self.fill_button.clicked.connect(self._confirm_fill)
        self.validate_button.setEnabled(False)
        self.fill_button.setEnabled(False)
        self.next_button = make_button("下一個測驗")
        self.next_button.clicked.connect(self._request_next)
        self.next_button.setEnabled(False)
        buttons.addWidget(self.clipboard_button)
        buttons.addWidget(self.validate_button)
        buttons.addWidget(self.fill_button)
        buttons.addWidget(self.next_button)
        buttons.addStretch()
        layout.addLayout(buttons)

    def _request_scan(self) -> None:
        self.scan_button.setEnabled(False)
        self.extract_button.setEnabled(False)
        self.banner.show_state("loading", "正在掃描已勾選課程的未測驗項目…")
        self.scan_requested.emit()

    def _request_extract(self) -> None:
        self.extract_button.setEnabled(False)
        self.banner.show_state("loading", "正在擷取目前測驗…")
        self.extract_requested.emit()

    def show_snapshot(self, snapshot: QuizSnapshot, position: int = 0, total: int = 0, course: str = "") -> None:
        self.snapshot = snapshot
        self.validated_answers = None
        prompt = build_quiz_prompt(snapshot)
        self.prompt_editor.setPlainText(prompt)
        QApplication.clipboard().setText(prompt)
        queue_text = f"｜測驗 {position}/{total}" if total else ""
        self.question_count.setText(f"共 {len(snapshot.questions)} 題{queue_text}")
        self.extract_button.setEnabled(True)
        self.scan_button.setEnabled(True)
        self.validate_button.setEnabled(True)
        self.fill_button.setEnabled(False)
        self.next_button.setEnabled(bool(total and position < total))
        self.banner.show_state(
            "success",
            f"{course + chr(10) if course else ''}已擷取並複製 {len(snapshot.questions)} 題。請貼到 AI。",
        )

    def show_error(self, message: str) -> None:
        self.extract_button.setEnabled(True)
        self.scan_button.setEnabled(True)
        self.banner.show_state("error", message)

    def _read_clipboard(self) -> None:
        self.answer_editor.setPlainText(QApplication.clipboard().text())
        self._validate()

    def _validate(self) -> None:
        if self.snapshot is None:
            self.show_error("請先擷取目前測驗。")
            return
        try:
            self.validated_answers = parse_and_validate_answers(
                self.answer_editor.toPlainText(), self.snapshot
            )
        except AnswerValidationError as exc:
            self.validated_answers = None
            self.fill_button.setEnabled(False)
            self.banner.show_state("error", str(exc))
            return
        self.fill_button.setEnabled(True)
        self.banner.show_state(
            "success", f"答案格式與題目均通過，共 {len(self.validated_answers)} 題。"
        )

    def _confirm_fill(self) -> None:
        if not self.validated_answers:
            return
        result = QMessageBox.question(
            self,
            "確認填入",
            f"將填入 {len(self.validated_answers)} 題，但不會送出。\n是否繼續？",
        )
        if result == QMessageBox.StandardButton.Yes:
            self.fill_button.setEnabled(False)
            self.banner.show_state("loading", "正在填入答案…")
            self.fill_requested.emit(self.validated_answers)

    def show_filled(self, count: int) -> None:
        self.fill_button.setEnabled(True)
        self.banner.show_state(
            "success", f"已填入 {count} 題，尚未送出。請回 Chrome 人工核對。"
        )

    def _request_next(self) -> None:
        self.next_button.setEnabled(False)
        self.banner.show_state("loading", "正在進入下一個測驗…")
        self.next_requested.emit()
