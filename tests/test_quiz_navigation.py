from contextlib import nullcontext

import pytest

from taipei_elearn.core.browser_manager import BrowserManager, BrowserManagerError
from taipei_elearn.core.quiz_course_scanner import QuizCandidate


class FakeLink:
    def __init__(self, page, target, count=1):
        self.page = page
        self.target = target
        self._count = count

    def count(self):
        return self._count

    def click(self):
        self.page.url = self.target

    def evaluate(self, script):
        assert script == "element => element.click()"
        self.page.url = self.target


class FakePage:
    def __init__(self, count=1):
        self.url = "https://example.test/courserecord/index.php"
        self.count = count
        self.selectors = []

    def locator(self, selector):
        self.selectors.append(selector)
        target = (
            "https://example.test/course/view.php?id=5025"
            if selector.startswith("#applySelection")
            else "https://example.test/mod/quiz/view.php?id=16868"
        )
        return FakeLink(self, target, self.count)

    def expect_navigation(self, **kwargs):
        return nullcontext()


def candidate():
    return QuizCandidate(
        "課程", "https://example.test/course/view.php?id=5025",
        "正式測驗", "https://example.test/mod/quiz/view.php?id=16868", "未完成測驗",
    )


def test_open_quiz_view_clicks_record_then_formal_quiz():
    page = FakePage()
    BrowserManager._open_quiz_view(page, candidate())
    assert len(page.selectors) == 2
    assert page.selectors[0].startswith("#applySelection")
    assert page.selectors[1] == 'a[href*="/mod/quiz/view.php?id=16868"] button:visible'
    assert "/mod/quiz/view.php?id=16868" in page.url


def test_open_quiz_view_stops_when_entry_is_not_unique():
    with pytest.raises(BrowserManagerError, match="唯一"):
        BrowserManager._open_quiz_view(FakePage(count=0), candidate())
