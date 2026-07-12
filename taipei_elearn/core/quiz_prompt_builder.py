from taipei_elearn.core.quiz_extractor import QuizSnapshot


def build_quiz_prompt(snapshot: QuizSnapshot) -> str:
    lines = [
        "請回答以下單選或多選題。只回傳答案列，不要解釋。",
        "格式必須完全如下：",
        "[[ANSWERS]]1=A;2=BD;3=C[[/ANSWERS]]",
        "單選題只能一個字母；多選題可有一個以上字母。",
        "",
    ]
    for question in snapshot.questions:
        kind = "單選" if question.kind == "single" else "多選"
        lines.append(f"{question.number}. [{kind}] {question.text}")
        lines.extend(f"{option.letter}. {option.text}" for option in question.options)
        lines.append("")
    return "\n".join(lines).rstrip()

