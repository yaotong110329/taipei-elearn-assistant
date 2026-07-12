import pytest

from taipei_elearn.core.answer_parser import AnswerValidationError, parse_and_validate_answers
from taipei_elearn.core.quiz_extractor import QuizOption, QuizQuestion, QuizSnapshot
from taipei_elearn.core.quiz_prompt_builder import build_quiz_prompt


@pytest.fixture
def snapshot():
    return QuizSnapshot(
        "正式測驗",
        "https://example.test/mod/quiz/attempt.php?attempt=1",
        (
            QuizQuestion(1, "single", "第一題？", (
                QuizOption("A", "甲"), QuizOption("B", "乙"),
            )),
            QuizQuestion(2, "multiple", "第二題？", (
                QuizOption("A", "一"), QuizOption("B", "二"), QuizOption("C", "三"),
            )),
        ),
    )


def test_parse_valid_answers_normalizes_case_and_full_width(snapshot):
    result = parse_and_validate_answers(
        "[[answers]]１＝ａ；２＝ｂｃ[[/answers]]", snapshot
    )
    assert result == {1: ("A",), 2: ("B", "C")}


@pytest.mark.parametrize("text, message", [
    ("1=A;2=BC", "格式錯誤"),
    ("[[ANSWERS]]1=A[[/ANSWERS]]", "缺少題號"),
    ("[[ANSWERS]]1=A;2=B;3=A[[/ANSWERS]]", "多出題號"),
    ("[[ANSWERS]]1=A;1=B;2=C[[/ANSWERS]]", "重複"),
    ("[[ANSWERS]]1=AB;2=C[[/ANSWERS]]", "單選"),
    ("[[ANSWERS]]1=C;2=A[[/ANSWERS]]", "超出範圍"),
    ("[[ANSWERS]]1=A;2=AA[[/ANSWERS]]", "重複選項"),
])
def test_invalid_answers_are_rejected(snapshot, text, message):
    with pytest.raises(AnswerValidationError, match=message):
        parse_and_validate_answers(text, snapshot)


def test_prompt_has_fixed_format_and_question_types(snapshot):
    prompt = build_quiz_prompt(snapshot)
    assert "[[ANSWERS]]1=A;2=BD;3=C[[/ANSWERS]]" in prompt
    assert "1. [單選] 第一題？" in prompt
    assert "2. [多選] 第二題？" in prompt

