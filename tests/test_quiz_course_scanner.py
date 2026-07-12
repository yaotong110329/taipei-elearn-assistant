import pytest

from taipei_elearn.core.quiz_course_scanner import QuizCourseScanner
from taipei_elearn.core.learning_record_scanner import CourseRecord


@pytest.mark.parametrize("text, expected", [
    ("繼續上一次作答", "作答中"),
    ("Continue the last attempt", "作答中"),
    ("開始作答測驗", "尚未作答"),
    ("Attempt quiz now", "尚未作答"),
    ("再測驗一次", "需重新測驗"),
    ("重新作答測驗", "需重新測驗"),
    ("Re-attempt quiz", "需重新測驗"),
    ("返回課程", None),
])
def test_classify_quiz_attempt_button(text, expected):
    assert QuizCourseScanner.classify_button(text) == expected


class PageMustNotBeUsed:
    def __getattr__(self, name):
        raise AssertionError(f"scan should use learning-record quiz URL, not page.{name}")


def make_record(score: str, quiz_url: str, remaining_seconds: int | None = 0) -> CourseRecord:
    return CourseRecord(
        "1", "課程", False, "未完成", "0秒", 0, "1", 3600,
        1800, remaining_seconds, "course-url", score, quiz_url, "-",
    )


def test_scan_uses_unfinished_quiz_link_from_learning_record():
    result = QuizCourseScanner().scan(
        PageMustNotBeUsed(),
        [make_record("未完成", "https://example.test/mod/quiz/view.php?id=1")],
    )
    assert len(result.candidates) == 1
    assert result.candidates[0].state == "未完成測驗"


def test_scan_skips_finished_quiz_score():
    result = QuizCourseScanner().scan(
        PageMustNotBeUsed(),
        [make_record("100", "https://example.test/mod/quiz/view.php?id=1")],
    )
    assert result.candidates == ()


def test_scan_skips_quiz_until_reading_time_is_reached():
    result = QuizCourseScanner().scan(
        PageMustNotBeUsed(),
        [make_record("未完成", "https://example.test/mod/quiz/view.php?id=1", 61)],
    )
    assert result.candidates == ()
    assert "閱讀時數不足" in result.skipped[0]
    assert "1分1秒" in result.skipped[0]
