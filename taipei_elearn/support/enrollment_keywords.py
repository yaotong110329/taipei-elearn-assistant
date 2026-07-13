import json
from pathlib import Path


DEFAULT_ENROLLMENT_KEYWORDS = (
    "環境教育",
    "性別平等",
    "人權教育",
    "轉型正義",
    "資通安全",
    "ODF",
    "職場霸凌",
    "人工智慧",
    "廉政與服務倫理",
    "行政中立",
    "多元族群文化",
    "公民參與",
)


class EnrollmentKeywordRepository:
    def __init__(self, config_file: Path) -> None:
        self.config_file = config_file

    def load(self) -> list[str]:
        raw = self._read_config()
        values = raw.get("enrollment_keywords")
        if not isinstance(values, list):
            return list(DEFAULT_ENROLLMENT_KEYWORDS)
        cleaned = self.normalize(values)
        return cleaned or list(DEFAULT_ENROLLMENT_KEYWORDS)

    def save(self, keywords: list[str]) -> list[str]:
        cleaned = self.normalize(keywords)
        if not cleaned:
            raise ValueError("常用關鍵字至少需要一筆。")
        raw = self._read_config()
        raw["enrollment_keywords"] = cleaned
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return cleaned

    def _read_config(self) -> dict:
        if not self.config_file.exists():
            return {}
        try:
            raw = json.loads(self.config_file.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    @staticmethod
    def normalize(values) -> list[str]:
        result = []
        seen = set()
        for value in values:
            keyword = str(value).strip()
            key = keyword.casefold()
            if keyword and key not in seen:
                seen.add(key)
                result.append(keyword)
        return result
