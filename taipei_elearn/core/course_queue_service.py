from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from taipei_elearn.core.learning_record_scanner import CourseRecord


class QueueState(Enum):
    IDLE = "未開始"
    RUNNING = "執行中"
    PAUSED = "已暫停"
    STOPPED = "已停止"
    COMPLETED = "全部完成"
    BLOCKED = "等待人工處理"


@dataclass(frozen=True)
class QueueSnapshot:
    state: QueueState
    current_index: int
    total: int
    current: CourseRecord | None
    reason: str = ""


class CourseQueueService:
    def __init__(self) -> None:
        self._courses: list[CourseRecord] = []
        self._index = -1
        self._state = QueueState.IDLE
        self._reason = ""

    def start(self, courses: list[CourseRecord]) -> QueueSnapshot:
        self._courses = [course for course in courses if not course.completed]
        self._index = 0 if self._courses else -1
        self._state = QueueState.RUNNING if self._courses else QueueState.COMPLETED
        self._reason = ""
        return self.snapshot()

    def pause(self) -> QueueSnapshot:
        if self._state is QueueState.RUNNING:
            self._state = QueueState.PAUSED
        return self.snapshot()

    def resume(self) -> QueueSnapshot:
        if self._state is QueueState.PAUSED:
            self._state = QueueState.RUNNING
        return self.snapshot()

    def skip(self) -> QueueSnapshot:
        if self._state in {QueueState.RUNNING, QueueState.PAUSED, QueueState.BLOCKED}:
            self._advance()
        return self.snapshot()

    def mark_platform_complete(self) -> QueueSnapshot:
        if self._state is QueueState.RUNNING:
            self._advance()
        return self.snapshot()

    def block(self, reason: str) -> QueueSnapshot:
        self._state = QueueState.BLOCKED
        self._reason = reason
        return self.snapshot()

    def stop(self) -> QueueSnapshot:
        self._state = QueueState.STOPPED
        return self.snapshot()

    def snapshot(self) -> QueueSnapshot:
        current = self._courses[self._index] if 0 <= self._index < len(self._courses) else None
        return QueueSnapshot(self._state, self._index, len(self._courses), current, self._reason)

    def _advance(self) -> None:
        self._index += 1
        self._reason = ""
        if self._index >= len(self._courses):
            self._state = QueueState.COMPLETED
            self._index = -1
        else:
            self._state = QueueState.RUNNING
