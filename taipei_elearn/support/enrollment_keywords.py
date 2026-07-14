from dataclasses import dataclass, replace
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


@dataclass(frozen=True)
class EnrollmentKeywordSetting:
    keyword: str
    enabled: bool = True
    course_limit: int = 5
    is_default: bool = False


class EnrollmentKeywordRepository:
    SETTINGS_KEY = "enrollment_keyword_settings"
    LEGACY_KEY = "enrollment_keywords"
    PANEL_STATE_KEY = "enrollment_panel_state"

    def __init__(self, config_file: Path) -> None:
        self.config_file = config_file

    def load(self) -> list[EnrollmentKeywordSetting]:
        raw = self._read_config()
        values = raw.get(self.SETTINGS_KEY)
        if isinstance(values, list):
            return self._merge_defaults(self.normalize(values))

        legacy = raw.get(self.LEGACY_KEY)
        custom = []
        if isinstance(legacy, list):
            custom = [
                EnrollmentKeywordSetting(keyword, True, 5, False)
                for keyword in self._normalize_names(legacy)
                if keyword.casefold() not in self._default_keys()
            ]
        return self._merge_defaults(custom)

    def save(
        self, settings: list[EnrollmentKeywordSetting | dict | str],
    ) -> list[EnrollmentKeywordSetting]:
        merged = self._merge_defaults(self.normalize(settings))
        raw = self._read_config()
        raw[self.SETTINGS_KEY] = [
            {
                "keyword": item.keyword,
                "enabled": item.enabled,
                "course_limit": item.course_limit,
                "is_default": item.is_default,
            }
            for item in merged
        ]
        raw.pop(self.LEGACY_KEY, None)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return merged

    def load_panel_state(self) -> dict[str, bool]:
        raw = self._read_config().get(self.PANEL_STATE_KEY)
        if not isinstance(raw, dict):
            raw = {}
        return {
            "keywords_expanded": bool(raw.get("keywords_expanded", False)),
            "courses_expanded": bool(raw.get("courses_expanded", True)),
        }

    def save_panel_state(
        self, keywords_expanded: bool, courses_expanded: bool,
    ) -> dict[str, bool]:
        state = {
            "keywords_expanded": bool(keywords_expanded),
            "courses_expanded": bool(courses_expanded),
        }
        raw = self._read_config()
        raw[self.PANEL_STATE_KEY] = state
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return state

    def _read_config(self) -> dict:
        if not self.config_file.exists():
            return {}
        try:
            raw = json.loads(self.config_file.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    @classmethod
    def normalize(cls, values) -> list[EnrollmentKeywordSetting]:
        result = []
        seen = set()
        for value in values:
            if isinstance(value, EnrollmentKeywordSetting):
                keyword = value.keyword.strip()
                enabled = bool(value.enabled)
                course_limit = value.course_limit
                is_default = bool(value.is_default)
            elif isinstance(value, dict):
                keyword = str(value.get("keyword") or "").strip()
                enabled = bool(value.get("enabled", True))
                course_limit = value.get("course_limit", 5)
                is_default = bool(value.get("is_default", False))
            else:
                keyword = str(value).strip()
                enabled = True
                course_limit = 5
                is_default = False
            key = keyword.casefold()
            if not keyword or key in seen:
                continue
            try:
                course_limit = int(course_limit)
            except (TypeError, ValueError):
                course_limit = 5
            result.append(EnrollmentKeywordSetting(
                keyword=keyword,
                enabled=enabled,
                course_limit=max(1, min(5, course_limit)),
                is_default=is_default,
            ))
            seen.add(key)
        return result

    @classmethod
    def _merge_defaults(
        cls, settings: list[EnrollmentKeywordSetting],
    ) -> list[EnrollmentKeywordSetting]:
        by_key = {item.keyword.casefold(): item for item in settings}
        result = []
        for keyword in DEFAULT_ENROLLMENT_KEYWORDS:
            existing = by_key.pop(keyword.casefold(), None)
            result.append(
                replace(existing, keyword=keyword, is_default=True)
                if existing else EnrollmentKeywordSetting(keyword, True, 5, True)
            )
        result.extend(
            replace(item, is_default=False)
            for item in settings
            if item.keyword.casefold() in by_key
        )
        return result

    @staticmethod
    def _normalize_names(values) -> list[str]:
        result = []
        seen = set()
        for value in values:
            keyword = str(value).strip()
            key = keyword.casefold()
            if keyword and key not in seen:
                result.append(keyword)
                seen.add(key)
        return result

    @staticmethod
    def _default_keys() -> set[str]:
        return {keyword.casefold() for keyword in DEFAULT_ENROLLMENT_KEYWORDS}
