import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from taipei_elearn.ui.pages.enrollment import EnrollmentPage
from taipei_elearn.ui.pages.learning import LearningPage
from taipei_elearn.ui.pages.quiz import QuizPage
from taipei_elearn.core.quiz_extractor import QuizOption, QuizQuestion, QuizSnapshot


def test_tables_support_scanned_and_mock_rows():
    app = QApplication.instance() or QApplication([])
    learning = LearningPage()
    enrollment = EnrollmentPage()
    assert learning.table.rowCount() == 0
    assert enrollment.table.rowCount() == 30
    assert learning.table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    learning.close()
    enrollment.close()
    app.processEvents()


def test_course_progress_countdown_display():
    app = QApplication.instance() or QApplication([])
    page = LearningPage()
    page.show_course_started({
        "course": "測試課程", "material": "第一章", "position": 2,
        "total": 5, "remaining_seconds": 61,
    })
    assert "目前第 2 門／共 5 門" in page.progress_label.text()
    assert "1分1秒" in page.progress_label.text()
    page._tick_countdown()
    assert "1分0秒" in page.progress_label.text()
    page.close()


def test_countdown_zero_emits_time_reached_once():
    app = QApplication.instance() or QApplication([])
    page = LearningPage()
    reached = []
    page.time_reached.connect(lambda: reached.append(True))
    page.show_course_started({
        "course": "測試課程", "material": "第一章", "position": 1,
        "total": 2, "remaining_seconds": 1,
    })
    page._tick_countdown()
    page._tick_countdown()
    assert reached == [True]
    assert "準備下一門" in page.progress_label.text()
    page.close()


def test_quiz_page_enables_validation_after_extract():
    app = QApplication.instance() or QApplication([])
    page = QuizPage()
    snapshot = QuizSnapshot(
        "測驗", "https://example.test/mod/quiz/attempt.php?attempt=1",
        (QuizQuestion(1, "single", "題目？", (
            QuizOption("A", "甲"), QuizOption("B", "乙"),
        )),),
    )
    page.show_snapshot(snapshot)
    assert page.validate_button.isEnabled()
    assert not page.fill_button.isEnabled()
    assert "共 1 題" == page.question_count.text()
    page.answer_editor.setPlainText("[[ANSWERS]]1=A[[/ANSWERS]]")
    page._validate()
    assert page.fill_button.isEnabled()
    page.close()
    app.processEvents()
