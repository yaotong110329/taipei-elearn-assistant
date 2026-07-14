import logging
import queue

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

from taipei_elearn.core.browser_manager import BrowserManager, BrowserManagerError
from taipei_elearn.core.course_queue_service import CourseQueueService, QueueState
from taipei_elearn.core.session_detector import SessionResult
from taipei_elearn.support.logging_setup import GuiLogEmitter
from taipei_elearn.support.settings import AppSettings
from taipei_elearn.ui.pages.dashboard import DashboardPage
from taipei_elearn.ui.pages.enrollment import EnrollmentPage
from taipei_elearn.ui.pages.learning import LearningPage
from taipei_elearn.ui.pages.logs_settings import LogsSettingsPage
from taipei_elearn.ui.pages.quiz import QuizPage


class BrowserWorker(QObject):
    completed = Signal(object)
    learning_scan_completed = Signal(object)
    learning_scan_failed = Signal(str)
    learning_records_opened = Signal(str)
    learning_records_open_failed = Signal(str)
    failed = Signal(str)
    stopped = Signal()
    course_started = Signal(object)
    course_failed = Signal(str)
    queue_state_changed = Signal(str, str)
    quiz_extracted = Signal(object)
    quiz_failed = Signal(str)
    quiz_filled = Signal(int)
    quiz_scan_completed = Signal(object)
    quiz_queue_opened = Signal(object)
    quiz_submitted = Signal(object)
    quiz_queue_completed = Signal(int)
    enrollment_search_completed = Signal(object)
    pocket_add_completed = Signal(object)
    pocket_enroll_completed = Signal(object)
    enrollment_progress = Signal(str)
    enrollment_failed = Signal(str)

    def __init__(self, settings: AppSettings, logger: logging.Logger) -> None:
        super().__init__()
        self.logger = logger
        self.manager = BrowserManager(settings.profile_dir, logger)
        self.commands: queue.Queue[object] = queue.Queue()
        self.course_queue = CourseQueueService()

    @Slot()
    def run(self) -> None:
        while True:
            command = self.commands.get()
            name, payload = command if isinstance(command, tuple) else (command, None)
            if name == "shutdown":
                self.manager.close()
                self.stopped.emit()
                return
            if name == "open":
                self._detect_and_open(self.manager.open)
            elif name == "detect":
                self._detect_and_open(self.manager.detect_session)
            elif name == "records":
                self._open_learning_records()
            elif name == "scan":
                self._scan_learning_records()
            elif name == "start_queue":
                self._start_queue(payload)
            elif name == "pause_queue":
                snapshot = self.course_queue.snapshot()
                snapshot = self.course_queue.resume() if snapshot.state is QueueState.PAUSED else self.course_queue.pause()
                self.queue_state_changed.emit(snapshot.state.value, snapshot.reason)
            elif name == "skip_course":
                snapshot = self.course_queue.skip()
                self._open_current(snapshot)
            elif name == "stop_queue":
                snapshot = self.course_queue.stop()
                self.queue_state_changed.emit(snapshot.state.value, snapshot.reason)
            elif name == "time_reached":
                self._open_current(self.course_queue.skip())
            elif name == "extract_quiz":
                self._extract_quiz()
            elif name == "fill_quiz":
                self._fill_quiz(payload)
            elif name == "scan_quizzes":
                self._scan_quizzes(payload)
            elif name == "start_quizzes":
                self._start_quizzes(payload)
            elif name == "next_quiz":
                self._next_quiz()
            elif name == "search_enrollment":
                self._search_enrollment(payload)
            elif name == "add_to_pocket":
                self._add_to_pocket(payload)
            elif name == "enroll_pocket_all":
                self._enroll_pocket_all()

    def submit(self, command: str) -> None:
        self.commands.put(command)

    def _start_queue(self, courses) -> None:
        self._open_current(self.course_queue.start(courses))

    def _open_current(self, snapshot) -> None:
        if snapshot.state is QueueState.COMPLETED:
            self.queue_state_changed.emit(snapshot.state.value, "沒有下一門已勾選課程。")
            return
        if snapshot.current is None:
            self.queue_state_changed.emit(snapshot.state.value, snapshot.reason)
            return
        try:
            result = self.manager.start_course(snapshot.current)
            result["position"] = snapshot.current_index + 1
            result["total"] = snapshot.total
            result["remaining_seconds"] = snapshot.current.remaining_seconds
            self.course_started.emit(result)
        except BrowserManagerError as exc:
            blocked = self.course_queue.block(str(exc))
            self.logger.error("%s", exc)
            self.course_failed.emit(str(exc))
            self.queue_state_changed.emit(blocked.state.value, blocked.reason)


    def _scan_learning_records(self) -> None:
        try:
            self.learning_scan_completed.emit(self.manager.scan_learning_records())
        except BrowserManagerError as exc:
            self.learning_scan_failed.emit(str(exc))
        except Exception as exc:
            self.learning_scan_failed.emit(f"未預期錯誤：{exc}")

    def _extract_quiz(self) -> None:
        try:
            self.quiz_extracted.emit(self.manager.extract_current_quiz())
        except BrowserManagerError as exc:
            self.quiz_failed.emit(str(exc))

    def _fill_quiz(self, answers) -> None:
        try:
            raw_result = self.manager.submit_quiz_answers(answers)
            result = (
                dict(raw_result)
                if isinstance(raw_result, dict)
                else {"count": int(raw_result), "score": "平台未顯示"}
            )
            has_next = self.manager.has_next_quiz()
            result["has_next"] = has_next
            self.quiz_submitted.emit(result)
            if has_next:
                self.quiz_queue_opened.emit(self.manager.open_next_quiz())
            else:
                self.quiz_queue_completed.emit(result["count"])
                try:
                    url = self.manager.open_learning_records()
                except BrowserManagerError as exc:
                    self.learning_records_open_failed.emit(str(exc))
                else:
                    self.learning_records_opened.emit(url)
        except BrowserManagerError as exc:
            self.quiz_failed.emit(str(exc))

    def _scan_quizzes(self, courses) -> None:
        try:
            self.quiz_scan_completed.emit(self.manager.scan_quizzes(courses))
        except BrowserManagerError as exc:
            self.quiz_failed.emit(str(exc))

    def _start_quizzes(self, candidates) -> None:
        try:
            self.quiz_queue_opened.emit(self.manager.start_quiz_queue(candidates))
        except BrowserManagerError as exc:
            self.quiz_failed.emit(str(exc))

    def _next_quiz(self) -> None:
        try:
            self.quiz_queue_opened.emit(self.manager.open_next_quiz())
        except BrowserManagerError as exc:
            self.quiz_failed.emit(str(exc))

    def _search_enrollment(self, keywords) -> None:
        try:
            result = self.manager.search_enrollment_courses(
                keywords, self.enrollment_progress.emit
            )
            self.enrollment_search_completed.emit(result)
        except BrowserManagerError as exc:
            self.enrollment_failed.emit(str(exc))

    def _add_to_pocket(self, courses) -> None:
        try:
            result = self.manager.add_courses_to_pocket(
                courses, self.enrollment_progress.emit
            )
            self.pocket_add_completed.emit(result)
        except BrowserManagerError as exc:
            self.enrollment_failed.emit(str(exc))

    def _enroll_pocket_all(self) -> None:
        try:
            self.pocket_enroll_completed.emit(self.manager.enroll_all_from_pocket())
        except BrowserManagerError as exc:
            self.enrollment_failed.emit(str(exc))

    def _open_learning_records(self) -> None:
        try:
            self.learning_records_opened.emit(self.manager.open_learning_records())
        except BrowserManagerError as exc:
            self.learning_records_open_failed.emit(str(exc))
        except Exception as exc:
            self.learning_records_open_failed.emit(f"未預期錯誤：{exc}")

    def _run(self, action) -> None:
        try:
            self.completed.emit(action())
        except BrowserManagerError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"未預期錯誤：{exc}")

    def _detect_and_open(self, action) -> None:
        try:
            result = action()
            if result.state.value == "已登入":
                url = self.manager.open_learning_records()
                self.completed.emit(result)
                self.learning_records_opened.emit(url)
            else:
                self.completed.emit(result)
        except BrowserManagerError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"未預期錯誤：{exc}")


class MainWindow(QMainWindow):
    open_browser = Signal()
    detect_session = Signal()
    shutdown_browser = Signal()
    scan_learning_records = Signal()
    open_learning_records = Signal()

    def __init__(self, settings: AppSettings, logger: logging.Logger, gui_log: GuiLogEmitter) -> None:
        super().__init__()
        self.logger = logger
        self.setWindowTitle("臺北 e 大學習輔助程式")
        self.resize(1280, 760)
        self.setMinimumSize(960, 600)
        self.dashboard = DashboardPage()
        self.learning = LearningPage()
        self.enrollment = EnrollmentPage(settings.config_file)
        self.quiz = QuizPage()
        self.logs = LogsSettingsPage(str(settings.profile_dir))
        self._build_ui()
        self._build_browser_thread(settings)
        self.dashboard.open_browser_requested.connect(self._request_open)
        self.dashboard.detect_login_requested.connect(self._request_detect)
        self.dashboard.records_button.clicked.connect(self._request_open_learning_records)
        self.learning.scan_requested.connect(self._request_learning_scan)
        self.learning.records_requested.connect(self._request_return_learning_records)
        self.learning.start_requested.connect(self._request_start_course)
        self.learning.pause_requested.connect(lambda: self.worker.submit("pause_queue"))
        self.learning.skip_requested.connect(lambda: self.worker.submit("skip_course"))
        self.learning.stop_requested.connect(lambda: self.worker.submit("stop_queue"))
        self.learning.time_reached.connect(lambda: self.worker.submit("time_reached"))
        self.quiz.fill_requested.connect(lambda answers: self.worker.submit(("fill_quiz", answers)))
        self.quiz.scan_requested.connect(self._request_quiz_scan)
        self.quiz.start_requested.connect(
            lambda candidates: self.worker.submit(("start_quizzes", candidates))
        )
        self.enrollment.search_requested.connect(
            lambda keywords: self.worker.submit(("search_enrollment", keywords))
        )
        self.enrollment.add_to_pocket_requested.connect(
            lambda courses: self.worker.submit(("add_to_pocket", courses))
        )
        self.enrollment.enroll_all_requested.connect(
            lambda: self.worker.submit("enroll_pocket_all")
        )
        gui_log.message.connect(self.logs.append_log)
        self.statusBar().showMessage("就緒")
        self.logger.info("GUI 啟動完成")

    def _build_ui(self) -> None:
        root = QWidget()
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(205)
        sidebar.setMaximumWidth(245)
        side = QVBoxLayout(sidebar)
        brand = QLabel("臺北 e 大\n學習輔助程式")
        brand.setObjectName("brand")
        side.addWidget(brand)
        labels = ("儀表板", "學習紀錄／上課", "選課", "答題", "執行日誌／設定")
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for index, text in enumerate(labels):
            button = QPushButton(text)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setMinimumHeight(46)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda checked=False, i=index: self._select_page(i))
            self.nav_group.addButton(button, index)
            side.addWidget(button)
        self.nav_group.button(0).setChecked(True)
        side.addStretch()
        row.addWidget(sidebar)
        self.stack = QStackedWidget()
        pages = (self.dashboard, self.learning, self.enrollment, self.quiz, self.logs)
        for page in pages:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            container = QWidget()
            content = QVBoxLayout(container)
            content.setContentsMargins(24, 20, 24, 18)
            content.addWidget(page)
            scroll.setWidget(container)
            self.stack.addWidget(scroll)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())

    def _build_browser_thread(self, settings: AppSettings) -> None:
        self.browser_thread = QThread(self)
        self.worker = BrowserWorker(settings, self.logger)
        self.worker.moveToThread(self.browser_thread)
        self.browser_thread.started.connect(self.worker.run)
        self.worker.stopped.connect(self.browser_thread.quit)
        self.worker.completed.connect(self._browser_completed)
        self.worker.learning_scan_completed.connect(self._learning_scan_completed)
        self.worker.learning_scan_failed.connect(self._learning_scan_failed)
        self.worker.learning_records_opened.connect(self._learning_records_opened)
        self.worker.learning_records_open_failed.connect(self._learning_records_open_failed)
        self.worker.failed.connect(self._browser_failed)
        self.worker.course_started.connect(self._course_started)
        self.worker.course_failed.connect(self._course_failed)
        self.worker.queue_state_changed.connect(self._queue_state_changed)
        self.worker.quiz_extracted.connect(self._quiz_extracted)
        self.worker.quiz_failed.connect(self._quiz_failed)
        self.worker.quiz_filled.connect(self._quiz_filled)
        self.worker.quiz_scan_completed.connect(self._quiz_scan_completed)
        self.worker.quiz_queue_opened.connect(self._quiz_queue_opened)
        self.worker.quiz_submitted.connect(self._quiz_submitted)
        self.worker.quiz_queue_completed.connect(self._quiz_queue_completed)
        self.worker.enrollment_search_completed.connect(self._enrollment_search_completed)
        self.worker.pocket_add_completed.connect(self._pocket_add_completed)
        self.worker.pocket_enroll_completed.connect(self._pocket_enroll_completed)
        self.worker.enrollment_progress.connect(self._enrollment_progress)
        self.worker.enrollment_failed.connect(self._enrollment_failed)
        self.browser_thread.start()

    def _select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        button = self.nav_group.button(index)
        if button:
            button.setChecked(True)

    @Slot()
    def _request_open(self) -> None:
        self.dashboard.set_busy(True)
        self.statusBar().showMessage("正在開啟正式 Chrome…")
        self.worker.submit("open")

    @Slot()
    def _request_detect(self) -> None:
        self.dashboard.set_busy(True)
        self.statusBar().showMessage("正在偵測登入狀態…")
        self.worker.submit("detect")

    @Slot()
    def _request_learning_scan(self) -> None:
        self.logger.info("GUI 已送出掃描學習紀錄要求")
        self.learning.set_busy(True)
        self.statusBar().showMessage("正在掃描學習紀錄…")
        self.worker.submit("scan")

    @Slot()
    def _request_open_learning_records(self) -> None:
        self.dashboard.set_busy(True)
        self.statusBar().showMessage("正在進入學習紀錄…")
        self.worker.submit("records")

    @Slot()
    def _request_return_learning_records(self) -> None:
        self.learning.banner.show_state("loading", "正在離開目前課程並回到學習紀錄…")
        self.statusBar().showMessage("正在回到學習紀錄…")
        self.worker.submit("stop_queue")
        self.worker.submit("records")

    @Slot(object)
    def _request_start_course(self, records) -> None:
        if not records:
            self.learning.show_error("請至少勾選一門課程。")
            return
        self.learning.banner.show_state("loading", "正在進入第一門課程與教材…")
        self.worker.submit(("start_queue", records))

    @Slot()
    def _request_quiz_scan(self) -> None:
        records = self.learning.all_records()
        if not records:
            self.quiz.show_error("請先在「學習紀錄／上課」完成掃描。")
            return
        self.statusBar().showMessage("正在掃描未答題課程…")
        self.worker.submit(("scan_quizzes", records))

    @Slot(object)
    def _course_started(self, result) -> None:
        self.learning.show_course_started(result)
        self.statusBar().showMessage("已進入第一門課程")

    @Slot(str)
    def _course_failed(self, message: str) -> None:
        self.learning.show_error(message)
        self.statusBar().showMessage("進入課程失敗")

    @Slot(str, str)
    def _queue_state_changed(self, state: str, detail: str) -> None:
        self.learning.show_queue_state(state, detail)
        self.statusBar().showMessage(f"上課佇列：{state}")

    @Slot(object)
    def _quiz_extracted(self, snapshot) -> None:
        self.quiz.show_snapshot(snapshot)
        self.statusBar().showMessage(f"測驗擷取完成：{len(snapshot.questions)} 題")
        self._bring_to_front()

    @Slot(str)
    def _quiz_failed(self, message: str) -> None:
        self.quiz.show_error(message)
        self.statusBar().showMessage("測驗操作失敗")
        self.logger.error(message)

    @Slot(int)
    def _quiz_filled(self, count: int) -> None:
        self.statusBar().showMessage(f"已填入 {count} 題")

    @Slot(object)
    def _quiz_scan_completed(self, result) -> None:
        self.quiz.show_candidates(result)
        self.statusBar().showMessage(f"找到 {len(result.candidates)} 門待答題課程")
        self._bring_to_front()

    @Slot(int)
    def _quiz_queue_completed(self, count: int) -> None:
        self.quiz.show_completed(count)
        self.statusBar().showMessage("測驗佇列已完成")
        self._bring_to_front()

    @Slot(object)
    def _quiz_submitted(self, result) -> None:
        self.quiz.show_submission(result)
        self.statusBar().showMessage(
            f"測驗已送出；分數：{result.get('score') or '平台未顯示'}"
        )

    @Slot(object)
    def _quiz_queue_opened(self, result) -> None:
        candidate = result["candidate"]
        self.quiz.show_snapshot(
            result["snapshot"], result["position"], result["total"], candidate.course_name
        )
        self.statusBar().showMessage(
            f"測驗 {result['position']}/{result['total']}：{candidate.course_name}"
        )
        self._bring_to_front()

    @Slot(object)
    def _enrollment_search_completed(self, result) -> None:
        self.enrollment.show_search_result(result)
        self.statusBar().showMessage(f"選課搜尋完成：{len(result.courses)} 門")
        self._bring_to_front()

    @Slot(object)
    def _pocket_add_completed(self, result) -> None:
        self.enrollment.show_pocket_add_result(result)
        self.statusBar().showMessage(
            f"已加入選課口袋：{result.success_count}/{len(result.results)} 門"
        )
        self._bring_to_front()

    @Slot(object)
    def _pocket_enroll_completed(self, result) -> None:
        self.enrollment.show_enroll_result(result)
        self.statusBar().showMessage("選課口袋全部報名完成")
        self._bring_to_front()

    @Slot(str)
    def _enrollment_progress(self, message: str) -> None:
        self.enrollment.show_progress(message)
        self.statusBar().showMessage(message)

    @Slot(str)
    def _enrollment_failed(self, message: str) -> None:
        self.enrollment.show_error(message)
        self.statusBar().showMessage("批次選課失敗")
        self.logger.error(message)


    @Slot(str)
    def _learning_records_opened(self, url: str) -> None:
        self.dashboard.set_busy(False)
        self._select_page(1)
        self.learning.banner.show_state("success", f"Chrome 已開啟學習紀錄。\n{url}")
        self.statusBar().showMessage("已進入學習紀錄，可開始掃描")
        self._bring_to_front()

    @Slot(str)
    def _learning_records_open_failed(self, message: str) -> None:
        self.dashboard.set_busy(False)
        self.dashboard.banner.show_state("error", message)
        self.learning.show_error(message)
        self.statusBar().showMessage("進入學習紀錄失敗")
        self.logger.error(message)

    @Slot(object)
    def _learning_scan_completed(self, result) -> None:
        self.learning.set_busy(False)
        self.learning.show_result(result)
        self.statusBar().showMessage(f"掃描完成：{len(result.records)} 門課程")
        self._bring_to_front()

    @Slot(str)
    def _learning_scan_failed(self, message: str) -> None:
        self.learning.set_busy(False)
        self.learning.show_error(message)
        self.statusBar().showMessage("學習紀錄掃描失敗")
        self.logger.error(message)

    @Slot(object)
    def _browser_completed(self, result: SessionResult) -> None:
        self.dashboard.set_busy(False)
        self.dashboard.browser_status.setText("已連線")
        self.dashboard.login_status.setText(result.state.value)
        self.dashboard.banner.show_state("success", f"{result.detail}\n目前頁面：{result.url}")
        self.dashboard.records_button.setEnabled(result.state.value == "已登入")
        self.statusBar().showMessage(f"登入狀態：{result.state.value}")
        self.logger.info("登入狀態=%s url=%s", result.state.value, result.url)

    @Slot(str)
    def _browser_failed(self, message: str) -> None:
        self.dashboard.set_busy(False)
        self.dashboard.browser_status.setText("未連線")
        self.dashboard.login_status.setText("偵測失敗")
        self.dashboard.banner.show_state("error", message)
        self.dashboard.records_button.setEnabled(False)
        self.statusBar().showMessage("操作失敗")
        self.logger.error(message)

    def _bring_to_front(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.browser_thread.isRunning():
            self.worker.submit("shutdown")
        if not self.browser_thread.wait(5_000):
            self.logger.warning("瀏覽器執行緒未於期限內結束")
        event.accept()
