from contextlib import nullcontext

import pytest

from taipei_elearn.core.browser_manager import BrowserManager, BrowserManagerError
from taipei_elearn.core.quiz_course_scanner import QuizCandidate


class FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def filter(self, **_kwargs):
        return self

    def count(self):
        if self.selector.startswith("#applySelection"):
            return self.page.entry_count
        if self.selector.startswith('.que:visible, form[action*="startattempt.php"]'):
            return int(self.page.stage in {"course", "quiz", "attempt"})
        if self.selector == ".que:visible":
            return int(self.page.stage == "attempt")
        if self.selector == 'form[action*="startattempt.php"]:visible':
            return int(self.page.stage == "quiz")
        if self.selector.startswith('a[href*="/mod/quiz/view.php?id=16868"] button'):
            return int(self.page.stage == "course")
        if self.selector.startswith('form[action*="startattempt.php"] button'):
            return int(self.page.stage == "quiz")
        return 0

    def wait_for(self, **_kwargs):
        if not self.count():
            raise TimeoutError(self.selector)

    def click(self):
        if self.selector.startswith("#applySelection"):
            self.page.stage = self.page.record_target
            if not self.page.stale_url:
                self.page.url = (
                    "https://example.test/mod/quiz/view.php?id=16868"
                    if self.page.stage == "quiz"
                    else "https://example.test/course/view.php?id=5025"
                )
        elif self.selector.startswith('a[href*="/mod/quiz/view.php?id=16868"] button'):
            self.page.stage = "quiz"
            self.page.url = "https://example.test/mod/quiz/view.php?id=16868"
        elif self.selector.startswith('form[action*="startattempt.php"] button'):
            self.page.stage = "attempt"
            self.page.url = "https://example.test/mod/quiz/attempt.php?attempt=1"


class FakePage:
    def __init__(self, record_target="quiz", entry_count=1, stale_url=False):
        self.url = "https://example.test/courserecord/index.php"
        self.stage = "records"
        self.record_target = record_target
        self.entry_count = entry_count
        self.stale_url = stale_url
        self.selectors = []

    def locator(self, selector):
        self.selectors.append(selector)
        return FakeLocator(self, selector)

    def expect_navigation(self, **_kwargs):
        return nullcontext()


def candidate():
    return QuizCandidate(
        "課程", "https://example.test/course/view.php?id=5025",
        "正式測驗", "https://example.test/mod/quiz/view.php?id=16868", "未完成測驗",
    )


def test_open_quiz_view_accepts_direct_quiz_page():
    page = FakePage(record_target="quiz")
    BrowserManager._open_quiz_view(page, candidate())
    assert page.stage == "quiz"


def test_open_quiz_view_accepts_quiz_dom_while_url_is_stale():
    page = FakePage(record_target="quiz", stale_url=True)
    BrowserManager._open_quiz_view(page, candidate())
    assert page.stage == "quiz"
    assert "/courserecord/" in page.url


def test_open_quiz_view_clicks_formal_button_from_course_page():
    page = FakePage(record_target="course")
    BrowserManager._open_quiz_view(page, candidate())
    assert page.stage == "quiz"


def test_open_quiz_view_stops_when_entry_is_not_unique():
    with pytest.raises(BrowserManagerError, match="唯一"):
        BrowserManager._open_quiz_view(FakePage(entry_count=0), candidate())


def test_enter_quiz_attempt_uses_dom_instead_of_initial_url():
    page = FakePage()
    page.stage = "quiz"
    BrowserManager._enter_quiz_attempt(page)
    assert page.stage == "attempt"
    assert "/mod/quiz/attempt.php" in page.url
