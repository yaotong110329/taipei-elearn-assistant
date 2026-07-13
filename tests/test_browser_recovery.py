import logging

from taipei_elearn.core.browser_manager import BrowserManager
from taipei_elearn.core.session_detector import LoginState, SessionResult


class Page:
    def __init__(self, url="https://elearning.taipei/mpage/", closed=False):
        self.url = url
        self.closed = closed
        self.records = False

    def is_closed(self):
        return self.closed

    def title(self):
        return "頁面"

    def locator(self, selector):
        return Locator(int(selector == "#applySelection" and self.records))

    def goto(self, url, **_kwargs):
        self.url = "https://ap2.elearning.taipei/elearn/courserecord/index.php"
        self.records = True


class Locator:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count

    def wait_for(self, **_kwargs):
        assert self._count == 1


class Context:
    def __init__(self, pages):
        self.pages = pages
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


class Playwright:
    def __init__(self):
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


def manager(tmp_path):
    return BrowserManager(tmp_path / "profile", logging.getLogger("browser-recovery"))


def test_connected_requires_at_least_one_open_page(tmp_path):
    browser = manager(tmp_path)
    browser._context = Context([])
    assert not browser.connected
    browser._context = Context([Page(closed=True)])
    assert not browser.connected
    browser._context = Context([Page()])
    assert browser.connected


def test_open_restarts_stale_context_after_manual_browser_close(tmp_path, monkeypatch):
    browser = manager(tmp_path)
    old_context = Context([])
    old_playwright = Playwright()
    browser._context = old_context
    browser._playwright = old_playwright
    new_page = Page()

    def launch():
        browser._context = Context([new_page])
        browser._playwright = Playwright()

    expected = SessionResult(LoginState.LOGGED_IN, "已登入", new_page.url)
    monkeypatch.setattr(browser, "_launch_browser_context", launch)
    monkeypatch.setattr(
        "taipei_elearn.core.browser_manager.SessionDetector.detect",
        lambda _self, _page: expected,
    )

    assert browser.open() is expected
    assert old_context.close_calls == 1
    assert old_playwright.stop_calls == 1
    assert browser.connected


def test_backup_returns_to_learning_records_from_quiz_page(tmp_path, monkeypatch):
    browser = manager(tmp_path)
    page = Page("https://ap2.elearning.taipei/elearn/mod/quiz/attempt.php?attempt=1")
    browser._context = Context([page])
    monkeypatch.setattr(browser, "_prepare_unfinished_records", lambda _page: None)

    url = browser.open_learning_records()

    assert "/courserecord/index.php" in url
    assert page.records
