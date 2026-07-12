from __future__ import annotations

import logging
import re
from dataclasses import replace
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


class LearningRecordScanError(RuntimeError):
    pass


@dataclass(frozen=True)
class CourseRecord:
    course_id: str
    name: str
    completed: bool
    status_text: str
    raw_studied_time: str
    studied_seconds: int | None
    raw_certification_hours: str
    certification_seconds: int | None
    required_seconds: int | None
    remaining_seconds: int | None
    course_url: str
    quiz_score_text: str = ""
    quiz_url: str = ""
    quiz_completed_date: str = ""


@dataclass(frozen=True)
class UnparsedRow:
    page_number: int
    reason: str
    cells: tuple[str, ...]
    html_features: str


@dataclass(frozen=True)
class ScanResult:
    records: tuple[CourseRecord, ...]
    failures: tuple[UnparsedRow, ...]
    pages_scanned: int


def parse_duration(text: str) -> int | None:
    value = re.sub(r"\s+", "", text or "")
    if not value or value in {"-", "—"}:
        return 0 if not value else None
    match = re.fullmatch(
        r"(?:(\d+(?:\.\d+)?)\s*(?:時|小時|hour|hours|h))?"
        r"(?:(\d+)\s*(?:分|分鐘|minute|minutes|min|m))?"
        r"(?:(\d+)\s*(?:秒|second|seconds|sec|s))?",
        value,
        re.IGNORECASE,
    )
    if not match or not any(match.groups()):
        clock = re.fullmatch(r"(\d+):(\d{1,2})(?::(\d{1,2}))?", value)
        if not clock:
            return None
        first, second, third = clock.groups()
        if third is None:
            return int(first) * 60 + int(second)
        return int(first) * 3600 + int(second) * 60 + int(third)
    hours, minutes, seconds = match.groups()
    return round(float(hours or 0) * 3600) + int(minutes or 0) * 60 + int(seconds or 0)


def parse_certification_hours(text: str) -> int | None:
    value = re.sub(r"\s+", "", text or "")
    if not value or value in {"-", "—"}:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return round(float(value) * 3600)
    return parse_duration(value)


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "待解析"
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}時{minutes}分{secs}秒"
    return f"{minutes}分{secs}秒"


def with_extra_hours(record: CourseRecord, extra_hours: float) -> CourseRecord:
    extra_seconds = round(max(0.0, extra_hours) * 3600)
    certification = record.certification_seconds
    required = None if certification is None else certification // 2 + extra_seconds
    remaining = (
        0 if record.completed else
        None if required is None or record.studied_seconds is None else
        max(0, required - record.studied_seconds)
    )
    return replace(record, required_seconds=required, remaining_seconds=remaining)


def record_from_cells(
    cells: list[str],
    href: str = "",
    quiz_href: str = "",
    quiz_score_text: str | None = None,
    quiz_completed_date: str | None = None,
) -> CourseRecord:
    if len(cells) < 12:
        raise ValueError(f"欄位不足：預期至少 12 欄，實際 {len(cells)} 欄")
    name = cells[0].strip()
    if not name:
        raise ValueError("課程名稱空白")
    studied = parse_duration(cells[3])
    certification = parse_certification_hours(cells[4])
    if studied is None:
        raise ValueError(f"無法解析修課時間：{cells[3]!r}")
    if certification is None:
        raise ValueError(f"無法解析認證時數：{cells[4]!r}")

    required = certification // 2
    status = cells[11].strip()
    completed = status == "已完成"
    course_id = parse_qs(urlparse(href).query).get("id", [""])[0]
    return CourseRecord(
        course_id=course_id,
        name=name,
        completed=completed,
        status_text=status or "狀態空白",
        raw_studied_time=cells[3].strip(),
        studied_seconds=studied,
        raw_certification_hours=cells[4].strip(),
        certification_seconds=certification,
        required_seconds=required,
        remaining_seconds=0 if completed else max(0, required - studied),
        course_url=href,
        quiz_score_text=(quiz_score_text if quiz_score_text is not None else cells[8]).strip(),
        quiz_url=quiz_href,
        quiz_completed_date=(quiz_completed_date if quiz_completed_date is not None else cells[9]).strip(),
    )


class LearningRecordScanner:
    TABLE_SELECTOR = "#applySelection"

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    def scan(self, page) -> ScanResult:
        table = page.locator(self.TABLE_SELECTOR)
        if table.count() != 1:
            raise LearningRecordScanError(
                "找不到唯一的學習紀錄表格 #applySelection；請先開啟「我的課程」。"
            )

        paginator = page.locator("#paginator")
        if paginator.count() == 1:
            paginator.select_option("50")
            page.wait_for_selector(f"{self.TABLE_SELECTOR} tbody tr", timeout=10_000)

        pages = self._page_numbers(page)
        records: dict[str, CourseRecord] = {}
        failures: list[UnparsedRow] = []
        for page_number in pages:
            if page_number != pages[0]:
                self._open_page(page, page_number)
            payload = self._extract_rows(page)
            for row in payload:
                try:
                    record = record_from_cells(
                        row["cells"], row["href"], row["quizHref"],
                        row["quizScore"], row["quizDate"],
                    )
                    key = record.course_id or record.course_url or record.name
                    records[key] = record
                except ValueError as exc:
                    failure = UnparsedRow(
                        page_number=page_number,
                        reason=str(exc),
                        cells=tuple(row["cells"]),
                        html_features=row["features"],
                    )
                    failures.append(failure)
                    self.logger.warning(
                        "學習紀錄列解析失敗 page=%s reason=%s cells=%r features=%s",
                        page_number, failure.reason, failure.cells, failure.html_features,
                    )
        self.logger.info(
            "學習紀錄掃描完成 pages=%s records=%s failures=%s",
            len(pages), len(records), len(failures),
        )
        return ScanResult(tuple(records.values()), tuple(failures), len(pages))

    @staticmethod
    def _page_numbers(page) -> list[int]:
        values = page.locator(".paginate-page[data-page]").evaluate_all(
            "els => [...new Set(els.map(e => Number(e.dataset.page)).filter(Boolean))]"
        )
        return sorted(values) or [1]

    @staticmethod
    def _open_page(page, number: int) -> None:
        previous_href = page.locator(
            '#applySelection tbody tr a[href*="/course/view.php?id="]'
        ).first.get_attribute("href")
        locator = page.locator(f'.pages .paginate-page[data-page="{number}"]')
        if locator.count() != 1:
            raise LearningRecordScanError(f"找不到第 {number} 頁分頁按鈕。")
        locator.click()
        page.wait_for_function(
            "n => document.querySelector('.pages .active')?.dataset.page === String(n)",
            arg=number,
            timeout=10_000,
        )
        page.wait_for_function(
            "oldHref => { const a = document.querySelector('#applySelection tbody tr a[href*=\"/course/view.php?id=\"]'); return a && a.href !== oldHref; }",
            arg=previous_href,
            timeout=10_000,
        )

    @staticmethod
    def _extract_rows(page) -> list[dict]:
        return page.locator("#applySelection tbody tr").evaluate_all(
            """rows => rows.map(row => {
                const cells = [...row.querySelectorAll(':scope > th, :scope > td')];
                const link = cells[0]?.querySelector('a[href*="/course/view.php?id="]');
                const quizCell = cells.find(cell => (cell.dataset.column || '').includes('測驗成績')) || cells[8];
                const quizDateCell = cells.find(cell => (cell.dataset.column || '').includes('完成測驗日期')) || cells[9];
                const quizLink = quizCell?.querySelector('a[href*="/mod/quiz/view.php?id="]');
                return {
                    cells: cells.map(cell => (cell.textContent || '').replace(/\\s+/g, ' ').trim()),
                    href: link?.href || '',
                    quizHref: quizLink?.href || '',
                    quizScore: (quizCell?.textContent || '').replace(/\\s+/g, ' ').trim(),
                    quizDate: (quizDateCell?.textContent || '').replace(/\\s+/g, ' ').trim(),
                    features: `tr.${row.className}; cells=${cells.length}; cellClasses=${cells.map(c => c.className).join('|')}`.slice(0, 500)
                };
            })"""
        )
