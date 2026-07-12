import logging

import pytest

from taipei_elearn.core.learning_record_scanner import (
    format_duration,
    parse_certification_hours,
    parse_duration,
    record_from_cells,
    with_extra_hours,
)


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("1時3分45秒", 3825),
        ("32分0秒", 1920),
        ("2 小時 5 分鐘", 7500),
        ("01:02:03", 3723),
        ("29:19", 1759),
        ("", 0),
        ("未知", None),
    ],
)
def test_parse_duration(text, seconds):
    assert parse_duration(text) == seconds


def test_parse_certification_numeric_is_hours():
    assert parse_certification_hours("2") == 7200
    assert parse_certification_hours("1.5") == 5400


def test_live_compact_row_structure():
    cells = [
        "「增強急救韌性，全民急救課程」", "開課中", "202607-03",
        "1時3分45秒", "2", "-", "-", "-", "100", "-", "填寫", "未完成", "",
    ]
    record = record_from_cells(cells, "https://ap1.elearning.taipei/elearn/course/view.php?id=5542")
    assert record.course_id == "5542"
    assert record.studied_seconds == 3825
    assert record.certification_seconds == 7200
    assert record.required_seconds == 3600
    assert record.remaining_seconds == 0
    assert not record.completed


def test_learning_record_keeps_unfinished_quiz_link():
    cells = [
        "測驗課程", "開課中", "2026-07-12", "30分0秒", "1",
        "-", "-", "-", "未完成", "-", "填寫", "未完成", "",
    ]
    quiz_url = "https://ap1.elearning.taipei/elearn/mod/quiz/view.php?id=16868"
    record = record_from_cells(cells, "course-url", quiz_url, "未完成", "-")
    assert record.quiz_score_text == "未完成"
    assert record.quiz_url == quiz_url
    assert record.quiz_completed_date == "-"


def test_live_completed_short_row():
    cells = [
        "[環境教育]《冰的顏色》", "開課中", "202607-03", "32分0秒",
        "1", "已上傳", "-", "-", "100", "2026-07-07", "填寫", "已完成", "",
    ]
    record = record_from_cells(cells)
    assert record.completed
    assert record.remaining_seconds == 0
    assert format_duration(record.required_seconds) == "30分0秒"


def test_extra_hours_correction_defaults_to_certification_plus_extra():
    cells = ["課程", "開課中", "日期", "30分0秒", "1", "-", "-", "-", "-", "-", "-", "未完成"]
    record = record_from_cells(cells)
    corrected = with_extra_hours(record, 0.5)
    assert corrected.required_seconds == 3600
    assert corrected.remaining_seconds == 1800
    assert with_extra_hours(record, 0).required_seconds == 1800


def test_invalid_row_reports_exact_field():
    cells = ["壞資料", "開課中", "日期", "不明", "2", "-", "-", "-", "-", "-", "-", "未完成"]
    with pytest.raises(ValueError, match="無法解析修課時間"):
        record_from_cells(cells)
