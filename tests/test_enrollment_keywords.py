import json

from taipei_elearn.support.enrollment_keywords import (
    DEFAULT_ENROLLMENT_KEYWORDS, EnrollmentKeywordRepository,
)
from taipei_elearn.support.settings import AppSettings


def test_default_keywords_include_annual_training_topics(tmp_path):
    repository = EnrollmentKeywordRepository(tmp_path / "settings.json")
    assert repository.load() == list(DEFAULT_ENROLLMENT_KEYWORDS)
    assert "環境教育" in repository.load()
    assert "資通安全" in repository.load()
    assert "人工智慧" in repository.load()


def test_keyword_save_deduplicates_and_preserves_other_settings(tmp_path):
    config = tmp_path / "settings.json"
    config.write_text(json.dumps({"profile_dir": "profile"}), encoding="utf-8")
    repository = EnrollmentKeywordRepository(config)
    saved = repository.save(["環境教育", "環境教育", " ODF ", ""])
    assert saved == ["環境教育", "ODF"]
    raw = json.loads(config.read_text(encoding="utf-8"))
    assert raw["profile_dir"] == "profile"


def test_app_settings_save_preserves_enrollment_keywords(tmp_path):
    config = tmp_path / "settings.json"
    config.write_text(
        json.dumps({"enrollment_keywords": ["人權教育"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    settings = AppSettings(tmp_path, tmp_path / "profile", tmp_path / "logs", config)
    settings.save()
    raw = json.loads(config.read_text(encoding="utf-8"))
    assert raw["enrollment_keywords"] == ["人權教育"]
