import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QSpinBox

from taipei_elearn.ui.pages.enrollment import EnrollmentPage
from taipei_elearn.ui.pages.learning import LearningPage
from taipei_elearn.ui.pages.quiz import QuizPage
from taipei_elearn.ui.styles import APP_STYLE
from taipei_elearn.core.quiz_extractor import QuizOption, QuizQuestion, QuizSnapshot
from taipei_elearn.core.quiz_course_scanner import (
    QuizCandidate, QuizCourseScanResult,
)
from taipei_elearn.support.enrollment_keywords import DEFAULT_ENROLLMENT_KEYWORDS


def test_tables_support_scanned_and_mock_rows():
    app = QApplication.instance() or QApplication([])
    learning = LearningPage()
    enrollment = EnrollmentPage()
    assert learning.table.rowCount() == 0
    assert enrollment.table.rowCount() == 0
    assert "環境教育" in enrollment.keywords
    assert enrollment.buttons["搜尋已勾選關鍵字"].isEnabled()
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


def test_enrollment_keyword_rows_add_duplicate_delete_and_restore(tmp_path):
    app = QApplication.instance() or QApplication([])
    config = tmp_path / "settings.json"
    page = EnrollmentPage(config)
    assert page.keyword_table.rowCount() == len(DEFAULT_ENROLLMENT_KEYWORDS)
    assert not isinstance(page.keyword_table.cellWidget(0, 3), QPushButton)

    page.keyword_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    first_limit = page.keyword_table.cellWidget(0, 2)
    assert isinstance(first_limit, QSpinBox)
    first_limit.setValue(2)

    page.new_keyword_input.setText("自訂教育")
    page.new_keyword_limit.setValue(3)
    page.add_keyword_button.click()
    assert page.keyword_table.rowCount() == len(DEFAULT_ENROLLMENT_KEYWORDS) + 1
    assert page.keyword_settings[-1].keyword == "自訂教育"
    assert page.keyword_settings[-1].enabled
    assert page.keyword_settings[-1].course_limit == 3

    page.new_keyword_input.setText("自訂教育")
    page.add_keyword_button.click()
    assert "不可重複新增" in page.banner.label.text()
    page.close()

    restored = EnrollmentPage(config)
    assert restored.keyword_table.item(0, 0).checkState() == Qt.CheckState.Unchecked
    assert restored.keyword_table.cellWidget(0, 2).value() == 2
    assert restored.keyword_settings[-1].keyword == "自訂教育"
    delete_button = restored.keyword_table.cellWidget(
        restored.keyword_table.rowCount() - 1, 3
    )
    assert isinstance(delete_button, QPushButton)
    delete_button.click()
    assert restored.keyword_table.rowCount() == len(DEFAULT_ENROLLMENT_KEYWORDS)
    restored.close()
    app.processEvents()


def test_enrollment_search_emits_only_checked_keywords_with_limits(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = EnrollmentPage(tmp_path / "settings.json")
    for row in range(page.keyword_table.rowCount()):
        page.keyword_table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
    page.keyword_table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    page.keyword_table.cellWidget(1, 2).setValue(4)
    emitted = []
    page.search_requested.connect(emitted.append)
    page.buttons["搜尋已勾選關鍵字"].click()
    assert len(emitted) == 1
    assert [(item.keyword, item.course_limit) for item in emitted[0]] == [
        (DEFAULT_ENROLLMENT_KEYWORDS[1], 4)
    ]
    page.close()
    app.processEvents()


def test_enrollment_panels_collapse_independently_and_restore(tmp_path):
    app = QApplication.instance() or QApplication([])
    config = tmp_path / "settings.json"
    page = EnrollmentPage(config)

    assert not page.keyword_panel.expanded
    assert page.keyword_panel.header_button.text().startswith("▶")
    assert page.keyword_panel.content.isHidden()
    assert page.course_panel.expanded
    assert page.course_panel.header_button.text().startswith("▼")
    assert not page.course_panel.content.isHidden()

    page.keyword_panel.header_button.click()
    assert page.keyword_panel.expanded
    assert page.course_panel.expanded
    assert page.main_layout.stretch(page.main_layout.indexOf(page.keyword_panel)) == 1
    assert page.main_layout.stretch(page.main_layout.indexOf(page.course_panel)) == 2

    page.course_panel.header_button.click()
    assert page.keyword_panel.expanded
    assert not page.course_panel.expanded
    assert page.course_panel.content.isHidden()
    assert page.main_layout.stretch(page.main_layout.indexOf(page.keyword_panel)) == 1
    assert page.main_layout.stretch(page.main_layout.indexOf(page.course_panel)) == 0
    page.close()

    restored = EnrollmentPage(config)
    assert restored.keyword_panel.expanded
    assert not restored.course_panel.expanded
    restored.keyword_panel.header_button.click()
    assert not restored.keyword_panel.expanded
    assert not restored.course_panel.expanded
    restored.close()
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


def test_quiz_page_lists_candidates_and_auto_submits_valid_clipboard_answer(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "taipei_elearn.ui.pages.quiz.QMessageBox.information",
        lambda *_args, **_kwargs: None,
    )
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
    assert page.clipboard_button.text() == "從剪貼簿讀取送出答案"
    assert "題目複製成功" in page.step_editor.toPlainText()
    assert not hasattr(page, "prompt_editor")
    assert not hasattr(page, "continue_button")
    submitted = []
    page.fill_requested.connect(submitted.append)
    QApplication.clipboard().setText("[[ANSWERS]]1=A[[/ANSWERS]]")
    page._read_clipboard_and_submit()
    assert submitted == [{1: ("A",)}]
    assert not page.clipboard_button.isEnabled()
    assert "送出答案中" in page.step_editor.toPlainText()
    page.close()
    app.processEvents()
