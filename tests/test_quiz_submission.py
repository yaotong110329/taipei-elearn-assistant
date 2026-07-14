import logging

from taipei_elearn.core.browser_manager import BrowserManager
from taipei_elearn.support.settings import AppSettings
from taipei_elearn.ui.main_window import BrowserWorker


class SubmitLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    def filter(self, **_kwargs):
        return self

    def count(self):
        if self.selector.startswith('form#responseform'):
            return int(self.page.stage == "attempt")
        if self.selector == 'form#frm-finishattempt:visible':
            return int(self.page.stage == "summary")
        if self.selector.startswith('form#frm-finishattempt button'):
            return int(self.page.stage == "summary")
        if self.selector.startswith('.modal-dialog button[data-action'):
            return int(self.page.stage == "confirm")
        return 0

    def wait_for(self, **_kwargs):
        if not self.count():
            raise TimeoutError(self.selector)

    def click(self):
        if self.page.stage == "attempt":
            self.page.stage = "summary"
        elif self.page.stage == "summary":
            self.page.stage = "confirm"
        elif self.page.stage == "confirm":
            self.page.stage = "done"
            self.page.url = "https://example.test/mod/quiz/review.php?attempt=1"


class SubmitPage:
    def __init__(self):
        self.stage = "attempt"
        self.url = "https://example.test/mod/quiz/attempt.php?attempt=1"

    def locator(self, selector):
        return SubmitLocator(self, selector)

    def wait_for_function(self, _script, **_kwargs):
        if self.stage != "done":
            raise TimeoutError("not done")


def test_submit_quiz_clicks_finish_summary_and_confirmation():
    page = SubmitPage()
    BrowserManager._submit_quiz_attempt(page)
    assert page.stage == "done"
    assert "/review.php" in page.url


class WorkerManager:
    def __init__(self, has_next):
        self._has_next = has_next
        self.submitted = None

    def submit_quiz_answers(self, answers):
        self.submitted = answers
        return len(answers)

    def has_next_quiz(self):
        return self._has_next

    @staticmethod
    def open_next_quiz():
        return {"candidate": "next"}

    @staticmethod
    def open_learning_records():
        return "https://example.test/learning-records?status=unfinished"


def make_worker(tmp_path, has_next):
    settings = AppSettings(
        tmp_path, tmp_path / "profile", tmp_path / "logs", tmp_path / "settings.json"
    )
    worker = BrowserWorker(settings, logging.getLogger("test-quiz-submit"))
    worker.manager = WorkerManager(has_next)
    return worker


def test_worker_automatically_opens_next_quiz_after_submit(tmp_path):
    worker = make_worker(tmp_path, True)
    opened = []
    submitted = []
    worker.quiz_queue_opened.connect(opened.append)
    worker.quiz_submitted.connect(submitted.append)
    worker._fill_quiz({1: ("A",)})
    assert opened == [{"candidate": "next"}]
    assert submitted == [{"count": 1, "score": "平台未顯示", "has_next": True}]


def test_worker_reports_queue_completed_after_last_submit(tmp_path):
    worker = make_worker(tmp_path, False)
    completed = []
    records_opened = []
    worker.quiz_queue_completed.connect(completed.append)
    worker.learning_records_opened.connect(records_opened.append)
    worker._fill_quiz({1: ("A",), 2: ("B",)})
    assert completed == [2]
    assert records_opened == ["https://example.test/learning-records?status=unfinished"]


class ScoreLocator:
    def __init__(self, selector):
        self.selector = selector

    def filter(self, **_kwargs):
        return self

    def count(self):
        return 0

    def inner_text(self):
        return "測驗完成\n成績：80 / 100\n回顧"


class ScorePage:
    def locator(self, selector):
        return ScoreLocator(selector)


def test_reads_quiz_score_from_review_page_text():
    assert BrowserManager._read_quiz_score(ScorePage()) == "80 / 100"
