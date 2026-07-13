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


def make_record(
    score: str, quiz_url: str, remaining_seconds: int | None = 0,
    studied_seconds: int | None = 1800, completed: bool = False,
) -> CourseRecord:
    return CourseRecord(
        "1", "課程", completed, "已完成" if completed else "未完成",
        "0秒" if not studied_seconds else "30分0秒", studied_seconds, "1", 3600,
        1800, remaining_seconds, "course-url", score, quiz_url, "-",
    )


def test_scan_uses_quiz_link_from_unfinished_course():
    result = QuizCourseScanner().scan(
        PageMustNotBeUsed(),
        [make_record("未完成", "https://example.test/mod/quiz/view.php?id=1")],
    )
    assert len(result.candidates) == 1
    assert result.candidates[0].state == "可開始答題"
    assert result.candidates[0].eligible


def test_scan_skips_finished_quiz_score():
    result = QuizCourseScanner().scan(
        PageMustNotBeUsed(),
        [make_record("100", "https://example.test/mod/quiz/view.php?id=1")],
    )
    assert result.candidates == ()


def test_scan_keeps_non_100_scores_without_guessing_pass_threshold():
    result = QuizCourseScanner().scan(
        PageMustNotBeUsed(),
        [make_record("90", "https://example.test/mod/quiz/view.php?id=1", 61)],
    )
    assert len(result.candidates) == 1
    assert result.candidates[0].score_text == "90"


def test_scan_shows_zero_reading_time_but_blocks_entry():
    result = QuizCourseScanner().scan(
        PageMustNotBeUsed(),
        [make_record("未完成", "https://example.test/mod/quiz/view.php?id=1", studied_seconds=0)],
    )
    assert len(result.candidates) == 1
    assert not result.candidates[0].eligible
    assert "閱讀時數為 0" in result.candidates[0].block_reason


@pytest.mark.parametrize("score", ["100", "100分", "100.0", " 100 分 "])
def test_scan_excludes_only_perfect_score(score):
    result = QuizCourseScanner().scan(
        PageMustNotBeUsed(),
        [make_record(score, "https://example.test/mod/quiz/view.php?id=1")],
    )
    assert result.candidates == ()


def test_scan_skips_completed_course_even_with_quiz():
    result = QuizCourseScanner().scan(
        PageMustNotBeUsed(),
        [make_record("80", "https://example.test/mod/quiz/view.php?id=1", completed=True)],
    )
    assert result.candidates == ()
