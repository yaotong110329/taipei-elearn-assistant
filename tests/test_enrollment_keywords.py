import json

from taipei_elearn.support.enrollment_keywords import (
    DEFAULT_ENROLLMENT_KEYWORDS, EnrollmentKeywordRepository,
    EnrollmentKeywordSetting,
)
from taipei_elearn.support.settings import AppSettings


def test_default_keywords_are_permanent_rows(tmp_path):
    repository = EnrollmentKeywordRepository(tmp_path / "settings.json")
    settings = repository.load()
    assert [item.keyword for item in settings] == list(DEFAULT_ENROLLMENT_KEYWORDS)
    assert all(item.is_default for item in settings)
    assert all(item.enabled and item.course_limit == 5 for item in settings)


def test_keyword_settings_save_state_limit_and_custom_rows(tmp_path):
    config = tmp_path / "settings.json"
    config.write_text(json.dumps({"profile_dir": "profile"}), encoding="utf-8")
    repository = EnrollmentKeywordRepository(config)
    settings = repository.load()
    settings[0] = EnrollmentKeywordSetting("環境教育", False, 2, True)
    settings.append(EnrollmentKeywordSetting("自訂主題", True, 3, False))

    saved = repository.save(settings)
    restored = repository.load()

    assert saved == restored
    assert restored[0] == EnrollmentKeywordSetting("環境教育", False, 2, True)
    assert restored[-1] == EnrollmentKeywordSetting("自訂主題", True, 3, False)
    raw = json.loads(config.read_text(encoding="utf-8"))
    assert raw["profile_dir"] == "profile"
    assert "enrollment_keywords" not in raw


def test_legacy_keywords_migrate_without_removing_defaults(tmp_path):
    config = tmp_path / "settings.json"
    config.write_text(
        json.dumps({"enrollment_keywords": ["人權教育", "自訂舊關鍵字"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    restored = EnrollmentKeywordRepository(config).load()
    names = [item.keyword for item in restored]
    assert names[:len(DEFAULT_ENROLLMENT_KEYWORDS)] == list(DEFAULT_ENROLLMENT_KEYWORDS)
    assert names[-1] == "自訂舊關鍵字"


def test_app_settings_save_preserves_enrollment_keyword_settings(tmp_path):
    config = tmp_path / "settings.json"
    values = [{
        "keyword": "人權教育", "enabled": False,
        "course_limit": 2, "is_default": True,
    }]
    config.write_text(
        json.dumps({"enrollment_keyword_settings": values}, ensure_ascii=False),
        encoding="utf-8",
    )
    settings = AppSettings(tmp_path, tmp_path / "profile", tmp_path / "logs", config)
    settings.save()
    raw = json.loads(config.read_text(encoding="utf-8"))
    assert raw["enrollment_keyword_settings"] == values


def test_panel_state_defaults_and_restores(tmp_path):
    repository = EnrollmentKeywordRepository(tmp_path / "settings.json")
    assert repository.load_panel_state() == {
        "keywords_expanded": False,
        "courses_expanded": True,
    }
    repository.save_panel_state(True, False)
    assert repository.load_panel_state() == {
        "keywords_expanded": True,
        "courses_expanded": False,
    }
