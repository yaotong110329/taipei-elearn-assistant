from dataclasses import dataclass, replace
import re
from typing import Callable


class EnrollmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnrollmentCourse:
    course_id: str
    title: str
    certification_text: str
    detail_url: str
    site_status: str
    can_add: bool
    matched_keywords: tuple[str, ...]


@dataclass(frozen=True)
class EnrollmentSearchResult:
    courses: tuple[EnrollmentCourse, ...]
    keywords: tuple[str, ...]
    pages_scanned: int


@dataclass(frozen=True)
class PocketCourseResult:
    course_id: str
    title: str
    success: bool
    message: str


@dataclass(frozen=True)
class PocketAddResult:
    results: tuple[PocketCourseResult, ...]

    @property
    def success_count(self) -> int:
        return sum(item.success for item in self.results)


@dataclass(frozen=True)
class PocketEnrollResult:
    success: bool
    message: str


class EnrollmentService:
    COURSE_CENTER_URL = "https://elearning.taipei/mpage/view_type_list"
    POCKET_URL = "https://elearning.taipei/mpage/pocket/show"
    POCKET_ADD_URL = "https://elearning.taipei/mpage/pocket/add"
    MAX_PER_KEYWORD = 5

    def search(
        self, page, keywords: list[str],
        progress: Callable[[str], None] | None = None,
    ) -> EnrollmentSearchResult:
        cleaned = self._normalize_keywords(keywords)
        if not cleaned:
            raise EnrollmentError("常用關鍵字清單是空的。")
        courses: dict[str, EnrollmentCourse] = {}
        pages_scanned = 0
        for keyword_index, keyword in enumerate(cleaned, 1):
            keyword_course_count = 0
            if progress:
                progress(f"搜尋 {keyword_index}/{len(cleaned)}：{keyword}")
            page.goto(self.COURSE_CENTER_URL, wait_until="domcontentloaded", timeout=30_000)
            keyword_input = page.locator("#keyword")
            submit = page.get_by_role("button", name="送出查詢", exact=True)
            if keyword_input.count() != 1 or submit.count() != 1:
                raise EnrollmentError("選課中心缺少唯一的課程名稱欄或送出查詢按鈕。")
            keyword_input.fill(keyword)
            with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
                submit.click()

            paginator = page.locator("#search_pages")
            total_pages = (
                paginator.locator("option").count() if paginator.count() == 1 else 1
            )
            for page_number in range(1, total_pages + 1):
                if page_number > 1:
                    paginator = page.locator("#search_pages")
                    if paginator.count() != 1:
                        raise EnrollmentError(f"搜尋「{keyword}」時分頁控制項消失。")
                    with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
                        paginator.select_option(str(page_number))
                pages_scanned += 1
                keyword_course_count += self._merge_page_results(
                    courses, keyword, self._extract_page(page),
                    self.MAX_PER_KEYWORD - keyword_course_count,
                )
                if progress:
                    progress(
                        f"搜尋 {keyword_index}/{len(cleaned)}：{keyword}｜"
                        f"第 {page_number}/{total_pages} 頁｜"
                        f"本關鍵字 {keyword_course_count}/{self.MAX_PER_KEYWORD} 門｜"
                        f"累計 {len(courses)} 門"
                    )
                if keyword_course_count >= self.MAX_PER_KEYWORD:
                    break
        ordered = tuple(sorted(courses.values(), key=lambda item: item.course_id, reverse=True))
        return EnrollmentSearchResult(ordered, tuple(cleaned), pages_scanned)

    def add_to_pocket(
        self, page, courses: list[EnrollmentCourse],
        progress: Callable[[str], None] | None = None,
    ) -> PocketAddResult:
        selected = [course for course in courses if course.can_add]
        if not selected:
            raise EnrollmentError("沒有已勾選且可加入選課口袋的課程。")
        page.goto(self.COURSE_CENTER_URL, wait_until="domcontentloaded", timeout=30_000)
        token = page.locator('meta[name="csrf-token"]').get_attribute("content")
        if not token:
            raise EnrollmentError("選課中心缺少 CSRF token，停止加入選課口袋。")
        results = []
        for index, course in enumerate(selected, 1):
            if progress:
                progress(f"加入選課口袋 {index}/{len(selected)}：{course.title}")
            try:
                response = page.request.post(
                    self.POCKET_ADD_URL,
                    headers={"X-CSRF-TOKEN": token, "Accept": "application/json"},
                    data={"course_id": course.course_id},
                    timeout=30_000,
                )
                payload = response.json()
                message = str(payload.get("message") or "")
                success = bool(response.ok and payload.get("success"))
                if not success and any(word in message for word in ("已在選課口袋", "已加入")):
                    success = True
                if not message:
                    message = "已加入選課口袋" if success else "加入失敗"
            except Exception as exc:
                success = False
                message = str(exc).splitlines()[0]
            results.append(PocketCourseResult(
                course.course_id, course.title, success, message,
            ))
        page.goto(self.POCKET_URL, wait_until="domcontentloaded", timeout=30_000)
        return PocketAddResult(tuple(results))

    def enroll_all(self, page) -> PocketEnrollResult:
        page.goto(self.POCKET_URL, wait_until="domcontentloaded", timeout=30_000)
        if page.get_by_text("選課口袋中尚無課程", exact=True).count() == 1:
            raise EnrollmentError("選課口袋中尚無課程。")
        button = page.locator("#enroll-all")
        if button.count() != 1:
            raise EnrollmentError("選課口袋缺少唯一的「全部報名」按鈕。")
        try:
            with page.expect_event("dialog", timeout=60_000) as dialog_info:
                button.click()
            dialog = dialog_info.value
            message = dialog.message
            dialog.accept()
        except Exception as exc:
            raise EnrollmentError(f"全部報名未取得平台結果：{str(exc).splitlines()[0]}") from exc
        failed = any(word in message for word in ("失敗", "錯誤", "無法", "沒有", "尚無"))
        return PocketEnrollResult(not failed, message)

    @staticmethod
    def _normalize_keywords(keywords: list[str]) -> list[str]:
        result = []
        seen = set()
        for raw in keywords:
            keyword = str(raw).strip()
            key = keyword.casefold()
            if keyword and key not in seen:
                seen.add(key)
                result.append(keyword)
        return result

    @staticmethod
    def _merge_page_results(
        target: dict[str, EnrollmentCourse], keyword: str,
        rows: list[dict], max_new: int,
    ) -> int:
        added = 0
        for row in rows:
            if added >= max_new:
                break
            course_id = str(row.get("courseId") or "").strip()
            title = str(row.get("title") or "").strip()
            status = str(row.get("status") or "狀態不明").strip()
            certification = str(row.get("hours") or "-").strip()
            if (
                not course_id or not title or status != "直接報名"
                or not EnrollmentService._has_positive_certification(certification)
            ):
                continue
            if course_id in target:
                current = target[course_id]
                if keyword not in current.matched_keywords:
                    target[course_id] = replace(
                        current, matched_keywords=current.matched_keywords + (keyword,)
                    )
                continue
            target[course_id] = EnrollmentCourse(
                course_id=course_id,
                title=title,
                certification_text=certification,
                detail_url=str(row.get("detailUrl") or "").strip(),
                site_status=status,
                can_add=status == "直接報名",
                matched_keywords=(keyword,),
            )
            added += 1
        return added

    @staticmethod
    def _has_positive_certification(text: str) -> bool:
        match = re.search(r"認證時數\s*(\d+(?:\.\d+)?)", text or "")
        if not match:
            return True
        return float(match.group(1)) > 0

    @staticmethod
    def _extract_page(page) -> list[dict]:
        return page.evaluate(
            r"""
            () => {
              const clean = value => (value || '').replace(/\u00a0/g, ' ')
                .replace(/\s+/g, ' ').trim();
              return [...document.querySelectorAll('button[data-course-id]')].map(button => {
                const card = button.closest('div.relative') || button.parentElement?.parentElement;
                const title = clean(card?.querySelector('h2')?.innerText);
                const statusButton = [...(card?.querySelectorAll('button') || [])].find(item =>
                  /直接報名|已報名|不可報名|停止報名/.test(clean(item.innerText))
                );
                const hours = [...(card?.querySelectorAll('*') || [])]
                  .map(item => clean(item.innerText))
                  .find(text => /^認證時數/.test(text) && text.length < 30) || '-';
                const detail = card?.querySelector('a[href*="/elearn/courseinfo/so.php"]');
                return {
                  courseId: button.dataset.courseId || '',
                  title,
                  hours,
                  detailUrl: detail?.href || '',
                  status: clean(statusButton?.innerText) || '狀態不明',
                };
              });
            }
            """
        )
