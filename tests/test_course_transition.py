import logging

from taipei_elearn.core.browser_manager import BrowserManager
from taipei_elearn.core.course_navigator import CourseNavigator, MaterialEntry
from taipei_elearn.core.learning_record_scanner import CourseRecord
from taipei_elearn.support.settings import AppSettings
from taipei_elearn.ui.main_window import BrowserWorker


class FakeLocator:
    def __init__(self, page, selector, count=0):
        self.page = page
        self.selector = selector
        self._count = count

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def count(self):
        return self._count

    def filter(self, **_kwargs):
        return self

    def get_attribute(self, name):
        assert name == "href"
        return "/elearn/transformation.php?fun=courseview"

    def click(self):
        self.page.clicked = True


class FakePage:
    def __init__(self, url, title="", player=False, context=None):
        self.url = url
        self._title = title
        self.player = player
        self.context = context
        self.closed = False
        self.spawned = False
        self.clicked = False

    def title(self):
        return self._title

    def is_closed(self):
        return self.closed

    def close(self):
        self.closed = True

    def locator(self, selector):
        if selector.startswith('a[href*="transformation.php'):
            return FakeLocator(self, selector, int(self.player))
        if selector.startswith("#scorm_object"):
            return FakeLocator(self, selector, int(self.player))
        return FakeLocator(self, selector, 0)

    def goto(self, url, **_kwargs):
        self.url = url
        self.player = False

    def wait_for_timeout(self, _milliseconds):
        if self.context and not self.spawned:
            self.spawned = True
            self.context.pages.append(
                FakePage("https://example.test/questionnaire", "課後問卷")
            )


class FakeContext:
    def __init__(self, pages):
        self.pages = pages
        for page in pages:
            page.context = self


def manager_with(pages):
    manager = BrowserManager.__new__(BrowserManager)
    manager._context = FakeContext(pages)
    manager.logger = logging.getLogger("test-course-transition")
    return manager


def test_select_course_page_ignores_last_questionnaire_window():
    player = FakePage("https://example.test/mod/scorm/player.php", player=True)
    questionnaire = FakePage("https://example.test/survey", "課後滿意度問卷")
    manager = manager_with([player, questionnaire])
    assert manager._select_course_page() is player


def test_leave_course_closes_delayed_questionnaire_popup():
    player = FakePage("https://example.test/mod/scorm/player.php", player=True)
    manager = manager_with([player])
    manager._leave_course_and_close_questionnaire(player)
    popup = manager._context.pages[-1]
    assert popup is not player
    assert popup.closed
    assert "transformation.php?fun=courseview" in player.url


def test_leave_course_preserves_new_non_questionnaire_page():
    player = FakePage("https://example.test/mod/scorm/player.php", player=True)
    manager = manager_with([player])
    replacement = FakePage("https://example.test/course/view.php?id=2", "下一門課")
    manager._context.pages.append(replacement)
    manager._leave_course_and_close_questionnaire(player)
    assert not replacement.closed


def test_leave_course_closes_questionnaire_already_open_before_transition():
    player = FakePage("https://example.test/mod/scorm/player.php", player=True)
    questionnaire = FakePage("https://example.test/survey", "課後滿意度問卷")
    manager = manager_with([player, questionnaire])
    manager._leave_course_and_close_questionnaire(player)
    assert questionnaire.closed


def test_worker_uses_scanned_remaining_seconds_without_test_override(tmp_path):
    settings = AppSettings(
        tmp_path, tmp_path / "profile", tmp_path / "logs", tmp_path / "settings.json"
    )
    worker = BrowserWorker(settings, logging.getLogger("test-real-duration"))

    class Manager:
        @staticmethod
        def start_course(course):
            return {"course": course.name, "material": "教材", "url": course.course_url}

    worker.manager = Manager()
    record = CourseRecord(
        "1", "課程", False, "未完成", "0秒", 0, "1", 3600, 1800, 1234,
        "https://example.test/course/view.php?id=1",
    )
    emitted = []
    worker.course_started.connect(emitted.append)
    worker._open_current(worker.course_queue.start([record]))
    assert emitted[0]["remaining_seconds"] == 1234


class DirectScormPage:
    def __init__(self):
        self.url = "https://example.test/course/view.php?id=1"
        self.frames = []
        self.goto_calls = []

    def goto(self, url, **_kwargs):
        self.goto_calls.append(url)
        self.url = "https://example.test/mod/scorm/player.php?id=9"

    def wait_for_timeout(self, _milliseconds):
        pass

    def locator(self, selector):
        return FakeLocator(self, selector, 0)


def test_scorm_entry_uses_direct_url_without_waiting_for_old_page_navigation():
    page = DirectScormPage()
    navigator = CourseNavigator()
    entry = MaterialEntry(
        "教材", "https://example.test/mod/scorm/view.php?id=9", "scorm"
    )
    navigator.enter_material(page, entry)
    assert page.goto_calls == [entry.url]
    assert "/mod/scorm/player.php" in page.url


class RetryScormPage(DirectScormPage):
    def goto(self, url, **_kwargs):
        self.goto_calls.append(url)
        self.url = (
            "https://example.test/course/view.php?id=1"
            if len(self.goto_calls) == 1
            else "https://example.test/mod/scorm/player.php?id=9"
        )

    def locator(self, selector):
        count = int('/mod/scorm/view.php?id=9' in selector)
        return FakeLocator(self, selector, count)


def test_scorm_entry_retries_once_when_platform_returns_to_course_page():
    page = RetryScormPage()
    navigator = CourseNavigator()
    entry = MaterialEntry(
        "C# 教材", "https://example.test/mod/scorm/view.php?id=9", "scorm"
    )
    navigator.enter_material(page, entry)
    assert page.goto_calls == [entry.url, entry.url]
    assert "/mod/scorm/player.php" in page.url
