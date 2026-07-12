from taipei_elearn.core.course_queue_service import CourseQueueService, QueueState
from taipei_elearn.core.learning_record_scanner import CourseRecord


def course(name, completed=False):
    return CourseRecord("1", name, completed, "已完成" if completed else "未完成", "0秒", 0, "1", 3600, 1800, 1800, "url")


def test_queue_excludes_completed_and_advances_only_on_platform_complete():
    queue = CourseQueueService()
    state = queue.start([course("完成", True), course("甲"), course("乙")])
    assert state.current.name == "甲"
    assert queue.mark_platform_complete().current.name == "乙"
    assert queue.mark_platform_complete().state is QueueState.COMPLETED


def test_pause_skip_stop_and_block():
    queue = CourseQueueService(); queue.start([course("甲"), course("乙")])
    assert queue.pause().state is QueueState.PAUSED
    assert queue.resume().state is QueueState.RUNNING
    assert queue.block("無法判定").state is QueueState.BLOCKED
    assert queue.skip().current.name == "乙"
    assert queue.stop().state is QueueState.STOPPED


def test_queue_does_not_advance_from_elapsed_time():
    queue = CourseQueueService(); queue.start([course("甲"), course("乙")])
    assert queue.snapshot().current.name == "甲"
    assert queue.snapshot().current.name == "甲"
