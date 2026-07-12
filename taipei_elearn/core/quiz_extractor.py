from dataclasses import dataclass
from typing import Literal


QuestionType = Literal["single", "multiple"]


@dataclass(frozen=True)
class QuizOption:
    letter: str
    text: str


@dataclass(frozen=True)
class QuizQuestion:
    number: int
    kind: QuestionType
    text: str
    options: tuple[QuizOption, ...]


@dataclass(frozen=True)
class QuizSnapshot:
    title: str
    url: str
    questions: tuple[QuizQuestion, ...]


class QuizExtractionError(RuntimeError):
    pass


class QuizExtractor:
    """Extract one-page Moodle single/multiple-choice quizzes."""

    def extract(self, page) -> QuizSnapshot:
        raw = page.evaluate(
            r"""
            () => {
              const clean = value => (value || '').replace(/\u00a0/g, ' ')
                .replace(/\s+/g, ' ').trim();
              const rows = [...document.querySelectorAll('.que')];
              return {
                title: clean(document.querySelector('h1')?.innerText || document.title),
                url: location.href,
                hasNext: [...document.querySelectorAll('input, button')].some(el =>
                  /下一頁|next page/i.test(clean(el.value || el.innerText))
                ),
                questions: rows.map((row, index) => {
                  const questionText = clean(row.querySelector('.qtext')?.innerText);
                  const questionImages = row.querySelectorAll('.qtext img').length;
                  const inputs = [...row.querySelectorAll(
                    '.answer input[type="radio"], .answer input[type="checkbox"]'
                  )].filter(input =>
                    !String(input.name || '').endsWith('_:flagged') &&
                    String(input.value) !== '-1' &&
                    !/flaggedcheckbox/i.test(input.id || '')
                  );
                  const options = inputs.map((input, optionIndex) => {
                    let label = input.id
                      ? row.querySelector(`label[for="${input.id}"]`)
                      : null;
                    if (!label) label = input.closest('label');
                    const optionRow = input.closest('.r0, .r1') || input.parentElement;
                    let text = clean(label?.innerText);
                    if (!text) text = clean(optionRow?.querySelector('.flex-fill')?.innerText);
                    if (!text) text = clean(optionRow?.innerText);
                    text = text.replace(/^[A-Za-zＡ-Ｚａ-ｚ][\.、．]\s*/, '');
                    return {
                      letter: String.fromCharCode(65 + optionIndex),
                      text,
                      inputType: input.type,
                    };
                  });
                  const inputTypes = [...new Set(options.map(option => option.inputType))];
                  return {
                    number: index + 1,
                    text: questionText,
                    questionImages,
                    options,
                    inputTypes,
                  };
                }),
              };
            }
            """
        )
        if "/mod/quiz/attempt.php" not in raw["url"]:
            raise QuizExtractionError("目前不是測驗作答頁，請先進入測驗題目頁。")
        if raw["hasNext"]:
            raise QuizExtractionError("目前版本只支援單頁測驗。")
        if not raw["questions"]:
            raise QuizExtractionError("目前頁面找不到測驗題目。")

        questions: list[QuizQuestion] = []
        for item in raw["questions"]:
            number = item["number"]
            if item["questionImages"] and not item["text"]:
                raise QuizExtractionError(f"第 {number} 題為純圖片題，目前不支援。")
            if not item["text"]:
                raise QuizExtractionError(f"第 {number} 題缺少可讀文字。")
            if item["inputTypes"] == ["radio"]:
                kind: QuestionType = "single"
            elif item["inputTypes"] == ["checkbox"]:
                kind = "multiple"
            else:
                raise QuizExtractionError(f"第 {number} 題不是支援的單選或多選題。")
            options = tuple(
                QuizOption(option["letter"], option["text"])
                for option in item["options"]
                if option["text"]
            )
            if len(options) != len(item["options"]) or len(options) < 2:
                raise QuizExtractionError(f"第 {number} 題選項文字不完整。")
            questions.append(QuizQuestion(number, kind, item["text"], options))
        return QuizSnapshot(raw["title"], raw["url"], tuple(questions))
