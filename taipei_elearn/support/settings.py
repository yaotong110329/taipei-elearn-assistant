import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    data_dir: Path
    profile_dir: Path
    log_dir: Path
    config_file: Path

    @classmethod
    def load(cls, base_dir: Path | None = None) -> "AppSettings":
        root = base_dir or Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData/Local")) / "TaipeiELearnAssistant"
        config_file = root / "settings.json"
        profile_dir = root / "chrome-profile"
        if config_file.exists():
            try:
                raw = json.loads(config_file.read_text(encoding="utf-8"))
                profile_dir = Path(raw.get("profile_dir", profile_dir))
            except (OSError, ValueError, TypeError):
                pass
        result = cls(root, profile_dir, root / "logs", config_file)
        result.ensure_directories()
        result.save()
        return result

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        raw = {}
        if self.config_file.exists():
            try:
                current = json.loads(self.config_file.read_text(encoding="utf-8"))
                if isinstance(current, dict):
                    raw = current
            except (OSError, ValueError, TypeError):
                pass
        raw["profile_dir"] = str(self.profile_dir)
        self.config_file.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
