import logging
import re
from pathlib import Path
from urllib.parse import urljoin

from taipei_elearn.core.session_detector import SessionDetector, SessionResult
from taipei_elearn.core.learning_record_scanner import LearningRecordScanner, ScanResult
from taipei_elearn.core.course_navigator import CourseNavigationError, CourseNavigator
from taipei_elearn.core.learning_record_scanner import CourseRecord
from taipei_elearn.core.quiz_extractor import QuizExtractor, QuizSnapshot
from taipei_elearn.core.quiz_course_scanner import QuizCandidate, QuizCourseScanner
from taipei_elearn.core.enrollment_service import EnrollmentError, EnrollmentService


class BrowserManagerError(RuntimeError):
    pass


class BrowserManager:
    HOME_URL = "https://elearning.taipei/mpage/"
    LEARNING_RECORD_SSO_URL = (
        "https://elearning.taipei/mpage/sso_moodle?redirectPage=courserecord"
    )
    QUESTIONNAIRE_MARKERS = re.compile(
        r"問卷|滿意度|questionnaire|survey|feedback", re.I
    )

    def __init__(self, profile_dir: Path, logger: logging.Logger) -> None:
        self.profile_dir = profile_dir
        self.logger = logger
        self._playwright = None
        self._context = None
        self._quiz_snapshot: QuizSnapshot | None = None
        self._quiz_candidates: tuple[QuizCandidate, ...] = ()
        self._quiz_index = -1

    @property
    def connected(self) -> bool:
        return self._has_live_pages()

    def open(self) -> SessionResult:
        if self._context:
            if self._has_live_pages():
                return self.detect_session()
            self.logger.info("偵測到失效 Chrome context，清理後重新啟動")
            self._reset_browser_state(log_errors=False)
        try:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            self._launch_browser_context()
            page = self._context.pages[0] if self._context.pages else self._context.new_page()
            if page.url in ("", "about:blank"):
                page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=30_000)
            self.logger.info("Chrome 已啟動，profile=%s", self.profile_dir)
            return SessionDetector().detect(page)
        except Exception as exc:
            self.close()
            raise BrowserManagerError(self._friendly_error(exc)) from exc

    def _launch_browser_context(self) -> None:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            channel="chrome",
            headless=False,
            no_viewport=True,
            args=["--start-maximized"],
        )

    def _has_live_pages(self) -> bool:
        if not self._context:
            return False
        try:
            return any(not page.is_closed() for page in self._context.pages)
        except Exception:
            return False

    def detect_session(self) -> SessionResult:
        if not self._context:
            raise BrowserManagerError("Chrome 尚未連線。")
        pages = self._context.pages
        if not pages:
            raise BrowserManagerError("Chrome 沒有可偵測頁面。")
        page = pages[-1]
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except Exception:
            self.logger.warning("頁面載入等待逾時，使用目前 DOM 偵測。")
        return SessionDetector().detect(page)

    def scan_learning_records(self) -> ScanResult:
        if not self._context:
            raise BrowserManagerError("Chrome 尚未連線。")
        pages = self._context.pages
        if not pages:
            raise BrowserManagerError("Chrome 沒有可掃描頁面。")
        page = pages[-1]
        try:
            self.logger.info("開始掃描學習紀錄 url=%s", page.url)
            if page.locator("#applySelection").count() != 1:
                self.open_learning_records()
                page = self._context.pages[-1]
            return LearningRecordScanner(self.logger).scan(page)
        except BrowserManagerError:
            raise
        except Exception as exc:
            raise BrowserManagerError(f"學習紀錄掃描失敗：{str(exc).splitlines()[0]}") from exc

    def start_course(self, course: CourseRecord) -> dict[str, str]:
        if not self._context:
            raise BrowserManagerError("Chrome 尚未連線。")
        old_page = self._select_course_page()
        old_is_player = (
            "/mod/scorm/player.php" in old_page.url
            or old_page.locator("#scorm_object, #scorm_layout, iframe[id*='scorm'], iframe[name*='scorm']").count() > 0
        )
        if old_is_player:
            page = self._leave_course_and_close_questionnaire(old_page)
        else:
            page = old_page
        try:
            try:
                page, navigator, entry = self._enter_course(page, course)
            except Exception as exc:
                if not self._is_target_closed_error(exc):
                    raise
                self.logger.warning("換課時原分頁已關閉，重新選取主頁後重試一次")
                page, navigator, entry = self._enter_course(
                    self._select_course_page(), course
                )
            self.logger.info(
                "已進入課程=%s 教材=%s strategy=%s player=%s media_started=%s",
                course.name, entry.title, entry.strategy, navigator.is_player(page), navigator.media_started,
            )
            return {
                "course": course.name, "material": entry.title, "url": page.url,
                "media_started": navigator.media_started,
            }
        except Exception as exc:
            raise BrowserManagerError(f"進入課程失敗：{str(exc).splitlines()[0]}") from exc

    @staticmethod
    def _is_target_closed_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return "target page, context or browser has been closed" in text or "page closed" in text

    def _enter_course(self, page, course: CourseRecord):
        navigator = CourseNavigator()
        self.logger.info("換課：開啟課程頁 course=%s url=%s", course.name, course.course_url)
        entries = navigator.open_course(page, course.course_url)
        entry = entries[0]
        self.logger.info("換課：開啟教材 title=%s url=%s", entry.title, entry.url)
        page = navigator.enter_material(page, entry)
        player_page = self._find_player_page()
        if player_page is not None:
            page = player_page
        if not navigator.is_player(page):
            page = navigator.penetrate_to_player(page)
        if not navigator.is_player(page):
            raise CourseNavigationError(f"教材穿透後仍未進入 player：{page.url}")
        if not navigator.media_started:
            navigator.media_started = navigator.ensure_media_started(page)
        return page, navigator, entry

    def _find_player_page(self):
        for page in reversed(tuple(self._context.pages)):
            if page.is_closed():
                continue
            try:
                if CourseNavigator.is_player(page):
                    return page
            except Exception:
                continue
        return None

    def _select_course_page(self):
        pages = [page for page in self._context.pages if not page.is_closed()]
        if not pages:
            raise BrowserManagerError("Chrome 沒有可操作頁面。")
        for page in reversed(pages):
            try:
                if (
                    "/mod/scorm/player.php" in page.url
                    or page.locator(
                        "#scorm_object, #scorm_layout, iframe[id*='scorm'], iframe[name*='scorm']"
                    ).count() > 0
                ):
                    return page
            except Exception:
                continue
        for page in reversed(pages):
            if not self._looks_like_questionnaire(page):
                return page
        return pages[-1]

    def _leave_course_and_close_questionnaire(self, page):
        exit_link = page.locator('a[href*="transformation.php?fun=courseview"]')
        if exit_link.count() < 1:
            raise BrowserManagerError("目前 player 缺少平台正式離開入口，停止換課。")
        exit_url = urljoin(page.url, exit_link.first.get_attribute("href"))
        page.goto(exit_url, wait_until="domcontentloaded", timeout=30_000)

        # 問卷可能延遲開啟成新分頁或同頁 modal；等待並清掉後才換課。
        closed = 0
        for _ in range(12):
            if page.is_closed():
                break
            try:
                page.wait_for_timeout(250)
                self._dismiss_questionnaire_modal(page)
            except Exception as exc:
                if self._is_target_closed_error(exc):
                    break
                raise
            for popup in tuple(self._context.pages):
                if popup is page or popup.is_closed():
                    continue
                if self._looks_like_questionnaire(popup):
                    self.logger.info("關閉問卷視窗 url=%s", popup.url)
                    popup.close()
                    closed += 1
        self.logger.info("已正式離開上一門課程，關閉問卷視窗=%s", closed)
        if page.is_closed():
            self.logger.info("離開後原播放器分頁已關閉，改用目前主頁")
            return self._select_course_page()
        return page

    @classmethod
    def _looks_like_questionnaire(cls, page) -> bool:
        try:
            return bool(cls.QUESTIONNAIRE_MARKERS.search(f"{page.url} {page.title()}"))
        except Exception:
            return False

    @classmethod
    def _dismiss_questionnaire_modal(cls, page) -> bool:
        dialogs = page.locator(
            '[role="dialog"]:visible, .modal.show:visible, .modal-dialog:visible'
        ).filter(has_text=cls.QUESTIONNAIRE_MARKERS)
        if dialogs.count() < 1:
            return False
        dialog = dialogs.last
        close_button = dialog.locator(
            'button[data-dismiss="modal"]:visible, button[data-bs-dismiss="modal"]:visible, '
            'button.close:visible, .btn-close:visible, '
            'button[aria-label*="close" i]:visible, button[aria-label*="關閉"]:visible'
        )
        if close_button.count() < 1:
            close_button = dialog.locator("button:visible").filter(
                has_text=re.compile(r"關閉|取消|稍後|略過|×|close", re.I)
            )
        if close_button.count() < 1:
            return False
        close_button.last.click()
        return True

    def open_learning_records(self) -> str:
        if not self._has_live_pages():
            self.open()
        page = self._select_course_page()
        try:
            if CourseNavigator.is_player(page):
                page = self._leave_course_and_close_questionnaire(page)
            if page.locator("#applySelection").count() == 1:
                self._prepare_unfinished_records(page)
                return page.url
            page.goto(
                self.LEARNING_RECORD_SSO_URL,
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            page.locator("#applySelection").wait_for(state="visible", timeout=20_000)
            self._prepare_unfinished_records(page)
            self.logger.info("已開啟學習紀錄 url=%s", page.url)
            return page.url
        except Exception as exc:
            raise BrowserManagerError(
                f"無法進入學習紀錄：{str(exc).splitlines()[0]}"
            ) from exc

    def extract_current_quiz(self) -> QuizSnapshot:
        if not self._context or not self._context.pages:
            raise BrowserManagerError("Chrome 尚未連線。")
        page = self._context.pages[-1]
        try:
            snapshot = QuizExtractor().extract(page)
            self._quiz_snapshot = snapshot
            self.logger.info("已擷取測驗：%s，共 %s 題", snapshot.title, len(snapshot.questions))
            return snapshot
        except Exception as exc:
            raise BrowserManagerError(f"擷取測驗失敗：{str(exc).splitlines()[0]}") from exc

    def search_enrollment_courses(self, keywords, progress=None):
        page = self._active_page_for_enrollment()
        try:
            return EnrollmentService().search(page, keywords, progress)
        except EnrollmentError as exc:
            raise BrowserManagerError(str(exc)) from exc
        except Exception as exc:
            raise BrowserManagerError(f"批次搜尋課程失敗：{str(exc).splitlines()[0]}") from exc

    def add_courses_to_pocket(self, courses, progress=None):
        page = self._active_page_for_enrollment()
        try:
            return EnrollmentService().add_to_pocket(page, courses, progress)
        except EnrollmentError as exc:
            raise BrowserManagerError(str(exc)) from exc
        except Exception as exc:
            raise BrowserManagerError(f"加入選課口袋失敗：{str(exc).splitlines()[0]}") from exc

    def enroll_all_from_pocket(self):
        page = self._active_page_for_enrollment()
        try:
            return EnrollmentService().enroll_all(page)
        except EnrollmentError as exc:
            raise BrowserManagerError(str(exc)) from exc
        except Exception as exc:
            raise BrowserManagerError(f"選課口袋全部報名失敗：{str(exc).splitlines()[0]}") from exc

    def _active_page_for_enrollment(self):
        if not self._context or not self._context.pages:
            raise BrowserManagerError("Chrome 尚未連線。")
        return self._context.pages[-1]

    def scan_quizzes(self, courses: list[CourseRecord]):
        if not self._context or not self._context.pages:
            raise BrowserManagerError("Chrome 尚未連線。")
        if not courses:
            raise BrowserManagerError("請先掃描學習紀錄。")
        page = self._context.pages[-1]
        try:
            self._leave_scorm_player(page)
            result = QuizCourseScanner().scan(page, courses)
            if not result.candidates:
                reasons = "；".join(result.skipped[:3])
                raise BrowserManagerError(
                    f"已掃描 {result.scanned_courses} 門，沒有符合條件的測驗。"
                    f"{f' 原因：{reasons}' if reasons else ''}"
                )
            return result
        except BrowserManagerError:
            raise
        except Exception as exc:
            raise BrowserManagerError(f"掃描未測驗課程失敗：{str(exc).splitlines()[0]}") from exc

    def start_quiz_queue(self, candidates: list[QuizCandidate] | tuple[QuizCandidate, ...]) -> dict:
        selected = tuple(candidate for candidate in candidates if candidate.eligible)
        if not selected:
            raise BrowserManagerError("請至少勾選一門閱讀時數大於 0 的課程。")
        self._quiz_candidates = selected
        self._quiz_index = -1
        return self.open_next_quiz()

    def scan_and_open_quizzes(self, courses: list[CourseRecord]) -> dict:
        """Backward-compatible shortcut used by older callers."""
        result = self.scan_quizzes(courses)
        opened = self.start_quiz_queue(result.candidates)
        opened["scanned_courses"] = result.scanned_courses
        opened["skipped"] = result.skipped
        return opened

    def has_next_quiz(self) -> bool:
        return self._quiz_index + 1 < len(self._quiz_candidates)

    def open_next_quiz(self) -> dict:
        next_index = self._quiz_index + 1
        if next_index >= len(self._quiz_candidates):
            raise BrowserManagerError("測驗佇列已完成，沒有下一個測驗。")
        candidate = self._quiz_candidates[next_index]
        page = self._context.pages[-1]
        try:
            if page.locator("#applySelection").count() != 1:
                self.open_learning_records()
                page = self._context.pages[-1]
            self._open_quiz_view(page, candidate)
            self._enter_quiz_attempt(page)
            snapshot = QuizExtractor().extract(page)
            self._quiz_snapshot = snapshot
            self._quiz_index = next_index
            self.logger.info(
                "已進入測驗 %s/%s：%s", next_index + 1,
                len(self._quiz_candidates), candidate.course_name,
            )
            return {
                "snapshot": snapshot,
                "candidate": candidate,
                "position": next_index + 1,
                "total": len(self._quiz_candidates),
            }
        except Exception as exc:
            raise BrowserManagerError(
                f"進入測驗失敗（{candidate.course_name}）：{str(exc).splitlines()[0]}"
            ) from exc

    @staticmethod
    def _open_quiz_view(page, candidate: QuizCandidate) -> None:
        course_id = re.search(r"[?&]id=(\d+)", candidate.course_url)
        activity_id = re.search(r"[?&]id=(\d+)", candidate.quiz_url)
        if not course_id or not activity_id:
            raise BrowserManagerError("測驗連結缺少課程或活動 ID。")
        record_link = page.locator(
            '#applySelection tbody tr:'
            f'has(a[href*="/course/view.php?id={course_id.group(1)}"]) '
            f'a[href*="/mod/quiz/view.php?id={activity_id.group(1)}"]'
        )
        if record_link.count() != 1:
            raise BrowserManagerError(
                f"學習紀錄找不到唯一的測驗連結（id={activity_id.group(1)}）。"
            )
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            record_link.click()

        # 「未完成」可能進入課程頁，也可能直接進入測驗首頁。
        # 導頁瞬間網址可能仍是舊值，因此以 DOM 當作完成條件。
        transition = page.locator(
            '.que:visible, '
            'form[action*="startattempt.php"]:visible, '
            f'a[href*="/mod/quiz/view.php?id={activity_id.group(1)}"] button:visible'
        )
        try:
            transition.first.wait_for(state="visible", timeout=20_000)
        except Exception as exc:
            raise BrowserManagerError(f"點擊未完成後未出現測驗入口：{page.url}") from exc

        if page.locator(".que:visible").count() or page.locator(
            'form[action*="startattempt.php"]:visible'
        ).count():
            return

        formal_button = page.locator(
            f'a[href*="/mod/quiz/view.php?id={activity_id.group(1)}"] button:visible'
        )
        if formal_button.count() == 0:
            formal_button = page.locator("button:visible").filter(
                has_text=re.compile(
                    r"正式測驗|繼續上一次作答|繼續作答|再測驗一次|再次測驗|重新測驗|重新作答"
                )
            )
        if formal_button.count() != 1:
            raise BrowserManagerError(
                f"課程頁找不到唯一的測驗入口（正式／繼續／重測，id={activity_id.group(1)}）。"
            )
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            formal_button.click()
        quiz_page = page.locator(
            '.que:visible, form[action*="startattempt.php"]:visible'
        )
        try:
            quiz_page.first.wait_for(state="visible", timeout=20_000)
        except Exception as exc:
            raise BrowserManagerError(f"點擊正式測驗後未進入測驗頁：{page.url}") from exc

    @staticmethod
    def _enter_quiz_attempt(page) -> None:
        if page.locator(".que:visible").count():
            return
        button = page.locator(
            'form[action*="startattempt.php"] button[type="submit"]:visible, '
            'form[action*="startattempt.php"] input[type="submit"]:visible'
        )
        try:
            button.first.wait_for(state="visible", timeout=20_000)
        except Exception as exc:
            raise BrowserManagerError("測驗頁缺少開始／繼續作答按鈕。") from exc
        if button.count() != 1:
            raise BrowserManagerError("測驗頁缺少唯一的開始／繼續作答按鈕。")
        button.click()
        try:
            page.locator(".que:visible").first.wait_for(state="visible", timeout=5_000)
            return
        except Exception:
            confirm = page.locator('.modal-dialog button, [role="dialog"] button').filter(
                has_text=re.compile(r"開始作答|start attempt", re.I)
            )
            confirm_count = confirm.count()
            if confirm_count == 1:
                confirm.last.click()
            elif confirm_count > 1:
                raise BrowserManagerError("開始作答確認按鈕不唯一，停止操作。")
        try:
            page.locator(".que:visible").first.wait_for(state="visible", timeout=20_000)
        except Exception as exc:
            raise BrowserManagerError(f"點擊作答後未出現測驗題目：{page.url}") from exc

    @staticmethod
    def _leave_scorm_player(page) -> None:
        if "/mod/scorm/player.php" not in page.url:
            return
        exit_link = page.locator('a[href*="transformation.php?fun=courseview"]')
        if exit_link.count() < 1:
            raise BrowserManagerError("目前 player 缺少平台正式離開入口，無法掃描測驗。")
        exit_url = urljoin(page.url, exit_link.first.get_attribute("href"))
        page.goto(exit_url, wait_until="domcontentloaded", timeout=30_000)

    def fill_quiz_answers(self, answers: dict[int, tuple[str, ...]]) -> int:
        if not self._context or not self._context.pages:
            raise BrowserManagerError("Chrome 尚未連線。")
        if self._quiz_snapshot is None:
            raise BrowserManagerError("尚未擷取測驗，不能填入答案。")
        page = self._context.pages[-1]
        if page.url != self._quiz_snapshot.url:
            raise BrowserManagerError("測驗頁已變更，請重新擷取後再填入。")
        try:
            rows = page.locator(".que")
            if rows.count() != len(self._quiz_snapshot.questions):
                raise BrowserManagerError("題目數已變更，請重新擷取。")
            for index, question in enumerate(self._quiz_snapshot.questions):
                row = rows.nth(index)
                inputs = row.locator(
                    '.answer input[type="radio"], .answer input[type="checkbox"]'
                )
                usable = [
                    inputs.nth(i) for i in range(inputs.count())
                    if inputs.nth(i).get_attribute("value") != "-1"
                    and not (inputs.nth(i).get_attribute("name") or "").endswith("_:flagged")
                    and "flaggedcheckbox" not in (inputs.nth(i).get_attribute("id") or "").lower()
                ]
                selected = {ord(letter) - ord("A") for letter in answers[question.number]}
                if question.kind == "multiple":
                    for option_index, locator in enumerate(usable):
                        locator.check() if option_index in selected else locator.uncheck()
                else:
                    usable[next(iter(selected))].check()
            self.logger.info("測驗答案已填入，共 %s 題；未送出", len(answers))
            return len(answers)
        except BrowserManagerError:
            raise
        except Exception as exc:
            raise BrowserManagerError(f"填入答案失敗：{str(exc).splitlines()[0]}") from exc

    def submit_quiz_answers(self, answers: dict[int, tuple[str, ...]]) -> dict:
        count = self.fill_quiz_answers(answers)
        page = self._context.pages[-1]
        try:
            self._submit_quiz_attempt(page)
            score = self._read_quiz_score(page)
            self.logger.info("測驗答案已自動送出，共 %s 題", count)
            return {"count": count, "score": score, "url": page.url}
        except BrowserManagerError:
            raise
        except Exception as exc:
            raise BrowserManagerError(f"送出測驗失敗：{str(exc).splitlines()[0]}") from exc

    @staticmethod
    def _read_quiz_score(page) -> str:
        for table_selector in (
            ".quizreviewsummary",
            "table.quizattemptsummary",
            "table.generaltable",
        ):
            try:
                row = page.locator(f"{table_selector} tr").filter(
                    has_text=re.compile(r"成績|分數")
                )
                if row.count():
                    cells = row.first.locator("td")
                    if cells.count():
                        text = re.sub(r"\s+", " ", cells.last.inner_text()).strip()
                        if text:
                            return text
            except Exception:
                continue
        try:
            body_text = page.locator("body").inner_text()
            match = re.search(
                r"(?:成績|分數)\s*[:：]?\s*([^\r\n]{1,60})",
                body_text,
            )
            if match:
                return re.sub(r"\s+", " ", match.group(1)).strip()
        except Exception:
            pass
        return "平台未顯示"

    @staticmethod
    def _submit_quiz_attempt(page) -> None:
        finish = page.locator(
            'form#responseform input[name="next"]:visible, '
            'form#responseform button[name="next"]:visible, '
            'form#responseform .mod_quiz-next-nav:visible'
        )
        if finish.count() == 0:
            finish = page.locator('button:visible, input[type="submit"]:visible').filter(
                has_text=re.compile(r"完成作答|finish attempt", re.I)
            )
        if finish.count() != 1:
            raise BrowserManagerError("測驗頁找不到唯一的「完成作答」按鈕，停止送出。")
        finish.click()

        summary = page.locator('form#frm-finishattempt:visible')
        try:
            summary.wait_for(state="visible", timeout=20_000)
        except Exception as exc:
            if re.search(r"/mod/quiz/(?:review|view)\.php", page.url):
                return
            raise BrowserManagerError(f"完成作答後未進入作答摘要：{page.url}") from exc

        submit_all = page.locator(
            'form#frm-finishattempt button[name="submitall"]:visible, '
            'form#frm-finishattempt input[name="submitall"]:visible, '
            'form#frm-finishattempt button[type="submit"]:visible'
        )
        if submit_all.count() != 1:
            raise BrowserManagerError("作答摘要找不到唯一的「提交所有答案並完成」按鈕。")
        submit_all.click()

        confirm = page.locator(
            '.modal-dialog button[data-action="save"]:visible, '
            '[role="dialog"] button[data-action="save"]:visible'
        )
        try:
            confirm.first.wait_for(state="visible", timeout=5_000)
        except Exception:
            confirm = page.locator('.modal-dialog button:visible, [role="dialog"] button:visible').filter(
                has_text=re.compile(r"提交所有答案並完成|submit all and finish", re.I)
            )
        if confirm.count() == 1:
            confirm.click()
        elif confirm.count() > 1:
            raise BrowserManagerError("送出測驗確認按鈕不唯一，停止操作。")

        try:
            page.wait_for_function(
                "() => !document.querySelector('form#frm-finishattempt')",
                timeout=20_000,
            )
        except Exception as exc:
            raise BrowserManagerError(f"送出測驗後頁面沒有完成跳轉：{page.url}") from exc

    def _prepare_unfinished_records(self, page) -> None:
        radio = page.locator("#r2s3_old")
        update_button = page.get_by_role("button", name="更新我的課程", exact=True)
        if radio.count() != 1 or update_button.count() != 1:
            raise BrowserManagerError("學習紀錄頁缺少「未完成」或「更新我的課程」控制項。")
        radio.check()
        self.logger.info("學習紀錄篩選：已選擇未完成")
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            update_button.click()
        page.locator("#applySelection").wait_for(state="visible", timeout=20_000)
        paginator = page.locator("#paginator")
        if paginator.count() != 1:
            raise BrowserManagerError("學習紀錄頁缺少每頁顯示筆數控制項。")
        paginator.select_option("50")
        page.wait_for_function(
            "() => document.querySelector('#paginator')?.value === '50'",
            timeout=10_000,
        )
        self.logger.info(
            "學習紀錄已更新：未完成、每頁50筆、目前列數=%s",
            page.locator("#applySelection tbody tr").count(),
        )

    def close(self) -> None:
        self._reset_browser_state(log_errors=True)

    def _reset_browser_state(self, log_errors: bool) -> None:
        context, self._context = self._context, None
        if context:
            try:
                context.close()
            except Exception as exc:
                if log_errors and not self._is_target_closed_error(exc):
                    self.logger.exception("關閉 Chrome context 失敗")
        playwright, self._playwright = self._playwright, None
        if playwright:
            try:
                playwright.stop()
            except Exception as exc:
                if log_errors and not self._is_target_closed_error(exc):
                    self.logger.exception("停止 Playwright 失敗")

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        text = str(exc)
        if "Target page, context or browser has been closed" in text:
            return "Chrome 已關閉或專用 profile 正被另一個程式使用；請關閉舊程式後重試。"
        if "Executable doesn't exist" in text or "chrome" in text.lower() and "not found" in text.lower():
            return "找不到正式版 Google Chrome，請先安裝 Chrome。"
        return f"Chrome 啟動失敗：{text.splitlines()[0]}"
