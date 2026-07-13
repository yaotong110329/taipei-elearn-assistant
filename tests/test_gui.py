import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from taipei_elearn.ui.pages.enrollment import EnrollmentPage
from taipei_elearn.ui.pages.learning import LearningPage
from taipei_elearn.ui.pages.quiz import QuizPage
from taipei_elearn.ui.styles import APP_STYLE
from taipei_elearn.core.quiz_extractor import QuizOption, QuizQuestion, QuizSnapshot
from taipei_elearn.core.quiz_course_scanner import (
    QuizCandidate, QuizCourseScanResult,
)


def test_tables_support_scanned_and_mock_rows():
    app = QApplication.instance() or QApplication([])
    learning = LearningPage()
    enrollment = EnrollmentPage()
    assert learning.table.rowCount() == 0
    assert enrollment.table.rowCount() == 0
    assert "環境教育" in enrollment.keywords
    assert enrollment.buttons["搜尋全部關鍵字"].isEnabled()
    assert learning.table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    learning.close()
    enrollment.close()
    app.processEvents()


def test_learning_actions_use_requested_labels_and_backup_signal():
    app = QApplication.instance() or QApplication([])
    page = LearningPage()
    requested = []
    page.records_requested.connect(lambda: requested.append(True))
    assert "開始掃描" in page.buttons
    assert "重新掃描" not in page.buttons
    page.buttons["回到學習紀錄"].click()
    assert requested == [True]
    page.close()


def test_sidebar_brand_has_explicit_dark_background_and_white_text():
    assert "QFrame#sidebar QLabel#brand" in APP_STYLE
    assert "color: #ffffff" in APP_STYLE


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


def test_quiz_page_lists_candidates_and_auto_submits_valid_clipboard_answer():
    app = QApplication.instance() or QApplication([])
    page = QuizPage()
    available = QuizCandidate(
        "可答課程", "course-1", "正式測驗", "quiz-1", "可開始答題",
        "80", "10分0秒", 600, True, "",
    )
    blocked = QuizCandidate(
        "零時數課程", "course-2", "正式測驗", "quiz-2",
        "課程閱讀時數為 0，不能進入測驗", "未完成", "0秒", 0, False,
        "課程閱讀時數為 0，不能進入測驗",
    )
    page.show_candidates(QuizCourseScanResult((available, blocked), 2, ()))
    assert page.course_table.rowCount() == 2
    assert page.selected_candidates() == [available]
    assert page.start_button.isEnabled()
    assert "不能勾選" in page.banner.label.text()

    snapshot = QuizSnapshot(
        "測驗", "https://example.test/mod/quiz/attempt.php?attempt=1",
        (QuizQuestion(1, "single", "題目？", (
            QuizOption("A", "甲"), QuizOption("B", "乙"),
        )),),
    )
    page.show_snapshot(snapshot, 1, 1, "可答課程")
    assert "共 1 題" in page.question_count.text()
    submitted = []
    page.fill_requested.connect(submitted.append)
    QApplication.clipboard().setText("[[ANSWERS]]1=A[[/ANSWERS]]")
    page._read_clipboard_and_continue()
    assert submitted == [{1: ("A",)}]
    assert not page.clipboard_button.isEnabled()
    page.close()
    app.processEvents()
