import logging
import re
from pathlib import Path
from urllib.parse import urljoin

from taipei_elearn.core.session_detector import SessionDetector, SessionResult
from taipei_elearn.core.learning_record_scanner import LearningRecordScanner, ScanResult
from taipei_elearn.core.course_navigator import CourseNavigator
from taipei_elearn.core.learning_record_scanner import CourseRecord
from taipei_elearn.core.quiz_extractor import QuizExtractor, QuizSnapshot
from taipei_elearn.core.quiz_course_scanner import QuizCandidate, QuizCourseScanner


class BrowserManagerError(RuntimeError):
    pass


class BrowserManager:
    HOME_URL = "https://elearning.taipei/mpage/"
    LEARNING_RECORD_SSO_URL = (
        "https://elearning.taipei/mpage/sso_moodle?redirectPage=courserecord"
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
        return self._context is not None

    def open(self) -> SessionResult:
        if self._context:
            return self.detect_session()
        try:
            from playwright.sync_api import sync_playwright

            self.profile_dir.mkdir(parents=True, exist_ok=True)
            self._playwright = sync_playwright().start()
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                channel="chrome",
                headless=False,
                no_viewport=True,
                args=["--start-maximized"],
            )
            page = self._context.pages[0] if self._context.pages else self._context.new_page()
            if page.url in ("", "about:blank"):
                page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=30_000)
            self.logger.info("Chrome 已啟動，profile=%s", self.profile_dir)
            return SessionDetector().detect(page)
        except Exception as exc:
            self.close()
            raise BrowserManagerError(self._friendly_error(exc)) from exc

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
        old_page = self._context.pages[-1]
        old_is_player = (
            "/mod/scorm/player.php" in old_page.url
            or old_page.locator("#scorm_object, #scorm_layout, iframe[id*='scorm'], iframe[name*='scorm']").count() > 0
        )
        if old_is_player:
            exit_link = old_page.locator('a[href*="transformation.php?fun=courseview"]')
            if exit_link.count() < 1:
                raise BrowserManagerError("目前 player 缺少平台正式離開入口，停止換課。")
            exit_url = urljoin(old_page.url, exit_link.first.get_attribute("href"))
            old_page.goto(exit_url, wait_until="domcontentloaded", timeout=30_000)
            self.logger.info("已透過平台正式離開上一門課程 url=%s", old_page.url)
            page = old_page
        else:
            page = old_page
        try:
            navigator = CourseNavigator()
            entries = navigator.open_course(page, course.course_url)
            entry = entries[0]
            navigator.enter_material(page, entry)
            if not navigator.is_player(page):
                navigator.penetrate_to_player(page)
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

    def open_learning_records(self) -> str:
        if not self._context:
            raise BrowserManagerError("Chrome 尚未連線。")
        pages = self._context.pages
        if not pages:
            raise BrowserManagerError("Chrome 沒有可操作頁面。")
        page = pages[-1]
        try:
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

    def scan_and_open_quizzes(self, courses: list[CourseRecord]) -> dict:
        if not self._context or not self._context.pages:
            raise BrowserManagerError("Chrome 尚未連線。")
        if not courses:
            raise BrowserManagerError("學習紀錄沒有已勾選課程。")
        page = self._context.pages[-1]
        try:
            self._leave_scorm_player(page)
            result = QuizCourseScanner().scan(page, courses)
            self._quiz_candidates = result.candidates
            self._quiz_index = -1
            if not self._quiz_candidates:
                reasons = "；".join(result.skipped[:3])
                raise BrowserManagerError(
                    f"已掃描 {result.scanned_courses} 門，沒有可進入的未完成測驗。"
                    f"{f' 原因：{reasons}' if reasons else ''}"
                )
            opened = self.open_next_quiz()
            opened["scanned_courses"] = result.scanned_courses
            opened["skipped"] = result.skipped
            return opened
        except BrowserManagerError:
            raise
        except Exception as exc:
            raise BrowserManagerError(f"掃描未測驗課程失敗：{str(exc).splitlines()[0]}") from exc

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
            raise BrowserManagerError("未完成測驗連結缺少課程或活動 ID。")
        record_link = page.locator(
            '#applySelection tbody tr:'
            f'has(a[href*="/course/view.php?id={course_id.group(1)}"]) '
            f'a[href*="/mod/quiz/view.php?id={activity_id.group(1)}"]'
        )
        if record_link.count() != 1:
            raise BrowserManagerError(
                f"學習紀錄找不到唯一的「未完成」測驗連結（id={activity_id.group(1)}）。"
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
        if self._context:
            try:
                self._context.close()
            except Exception:
                self.logger.exception("關閉 Chrome context 失敗")
            self._context = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                self.logger.exception("停止 Playwright 失敗")
            self._playwright = None

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        text = str(exc)
        if "Target page, context or browser has been closed" in text:
            return "Chrome 已關閉或專用 profile 正被另一個程式使用；請關閉舊程式後重試。"
        if "Executable doesn't exist" in text or "chrome" in text.lower() and "not found" in text.lower():
            return "找不到正式版 Google Chrome，請先安裝 Chrome。"
        return f"Chrome 啟動失敗：{text.splitlines()[0]}"
