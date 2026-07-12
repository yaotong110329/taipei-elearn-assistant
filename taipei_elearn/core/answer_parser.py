import re
import unicodedata

from taipei_elearn.core.quiz_extractor import QuizSnapshot


class AnswerValidationError(ValueError):
    pass


def parse_and_validate_answers(text: str, snapshot: QuizSnapshot) -> dict[int, tuple[str, ...]]:
    normalized = unicodedata.normalize("NFKC", text).strip().upper()
    match = re.fullmatch(r"\[\[ANSWERS\]\](.*?)\[\[/ANSWERS\]\]", normalized, re.DOTALL)
    if not match:
        raise AnswerValidationError("格式錯誤：需要 [[ANSWERS]]...[[/ANSWERS]]。")
    body = match.group(1).strip()
    if not body:
        raise AnswerValidationError("答案列不可空白。")

    answers: dict[int, tuple[str, ...]] = {}
    for part in re.split(r"\s*;\s*", body):
        item = re.fullmatch(r"(\d+)\s*=\s*([A-Z]+)", part.strip())
        if not item:
            raise AnswerValidationError(f"答案片段格式錯誤：{part}")
        number = int(item.group(1))
        letters = tuple(item.group(2))
        if number in answers:
            raise AnswerValidationError(f"第 {number} 題重複。")
        if len(set(letters)) != len(letters):
            raise AnswerValidationError(f"第 {number} 題含重複選項。")
        answers[number] = letters

    expected = {question.number for question in snapshot.questions}
    actual = set(answers)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        raise AnswerValidationError(f"缺少題號：{', '.join(map(str, missing))}")
    if extra:
        raise AnswerValidationError(f"多出題號：{', '.join(map(str, extra))}")

    for question in snapshot.questions:
        letters = answers[question.number]
        allowed = {option.letter for option in question.options}
        invalid = sorted(set(letters) - allowed)
        if invalid:
            raise AnswerValidationError(
                f"第 {question.number} 題選項超出範圍：{''.join(invalid)}"
            )
        if question.kind == "single" and len(letters) != 1:
            raise AnswerValidationError(f"第 {question.number} 題為單選，只能填一個選項。")
        if not letters:
            raise AnswerValidationError(f"第 {question.number} 題沒有答案。")
    return answers

