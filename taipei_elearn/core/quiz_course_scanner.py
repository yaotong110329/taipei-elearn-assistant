from dataclasses import dataclass
import re

from taipei_elearn.core.learning_record_scanner import CourseRecord


@dataclass(frozen=True)
class QuizCandidate:
    course_name: str
    course_url: str
    quiz_title: str
    quiz_url: str
    state: str
    score_text: str = ""
    raw_studied_time: str = ""
    studied_seconds: int | None = None
    eligible: bool = True
    block_reason: str = ""


@dataclass(frozen=True)
class QuizCourseScanResult:
    candidates: tuple[QuizCandidate, ...]
    scanned_courses: int
    skipped: tuple[str, ...]


class QuizCourseScanner:
    """Find quiz items from unfinished courses without guessing a pass score."""

    CONTINUE = re.compile(r"繼續上一次作答|繼續作答|continue.*attempt", re.I)
    START = re.compile(r"開始作答測驗|開始作答|attempt quiz now", re.I)
    RETAKE = re.compile(
        r"再測驗一次|再次測驗|重新測驗|重新作答|再次作答|re-?attempt",
        re.I,
    )

    @classmethod
    def classify_button(cls, text: str) -> str | None:
        if cls.CONTINUE.search(text):
            return "作答中"
        if cls.RETAKE.search(text):
            return "需重新測驗"
        if cls.START.search(text) and not cls.RETAKE.search(text):
            return "尚未作答"
        return None

    def scan(self, page, courses: list[CourseRecord]) -> QuizCourseScanResult:
        candidates: list[QuizCandidate] = []
        skipped: list[str] = []
        seen: set[str] = set()
        for course in courses:
            if course.completed:
                skipped.append(f"{course.name}：課程已完成")
                continue
            if not course.quiz_url:
                skipped.append(f"{course.name}：沒有測驗項目")
                continue
            if self._is_perfect_score(course.quiz_score_text):
                skipped.append(f"{course.name}：測驗成績 100 分")
                continue
            if course.quiz_url in seen:
                continue
            seen.add(course.quiz_url)
            eligible = course.studied_seconds is not None and course.studied_seconds > 0
            block_reason = ""
            if course.studied_seconds is None:
                block_reason = "無法判斷課程閱讀時數，不能進入測驗"
            elif course.studied_seconds <= 0:
                block_reason = "課程閱讀時數為 0，不能進入測驗"
            candidates.append(QuizCandidate(
                course.name, course.course_url,
                "正式測驗", course.quiz_url,
                "可開始答題" if eligible else block_reason,
                course.quiz_score_text or "-", course.raw_studied_time,
                course.studied_seconds, eligible, block_reason,
            ))
        return QuizCourseScanResult(tuple(candidates), len(courses), tuple(skipped))

    @staticmethod
    def _is_perfect_score(text: str) -> bool:
        value = re.sub(r"\s+|分", "", text or "")
        try:
            return float(value) == 100
        except ValueError:
            return False
