from dataclasses import dataclass
import re

from taipei_elearn.core.learning_record_scanner import CourseRecord, format_duration


@dataclass(frozen=True)
class QuizCandidate:
    course_name: str
    course_url: str
    quiz_title: str
    quiz_url: str
    state: str


@dataclass(frozen=True)
class QuizCourseScanResult:
    candidates: tuple[QuizCandidate, ...]
    scanned_courses: int
    skipped: tuple[str, ...]


class QuizCourseScanner:
    """Find reliable Moodle quiz links and keep only new/in-progress attempts."""

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
            if course.quiz_score_text != "未完成":
                skipped.append(f"{course.name}：測驗成績 {course.quiz_score_text or '-'}")
                continue
            if course.remaining_seconds is None:
                skipped.append(f"{course.name}：無法確認閱讀時數是否達標")
                continue
            if course.remaining_seconds > 0:
                skipped.append(
                    f"{course.name}：閱讀時數不足，尚差 {format_duration(course.remaining_seconds)}"
                )
                continue
            if not course.quiz_url:
                skipped.append(f"{course.name}：顯示未完成，但缺少測驗連結")
                continue
            if course.quiz_url in seen:
                continue
            seen.add(course.quiz_url)
            candidates.append(QuizCandidate(
                course.name, course.course_url,
                "正式測驗", course.quiz_url, "未完成測驗",
            ))
        return QuizCourseScanResult(tuple(candidates), len(courses), tuple(skipped))
