import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QObject, Signal


class GuiLogEmitter(QObject):
    message = Signal(str)


class GuiLogHandler(logging.Handler):
    def __init__(self, emitter: GuiLogEmitter) -> None:
        super().__init__()
        self.emitter = emitter

    def emit(self, record: logging.LogRecord) -> None:
        self.emitter.message.emit(self.format(record))


def configure_logging(log_dir: Path) -> tuple[logging.Logger, GuiLogEmitter]:
    logger = logging.getLogger("taipei_elearn")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        emitter = next((h.emitter for h in logger.handlers if isinstance(h, GuiLogHandler)), GuiLogEmitter())
        return logger, emitter
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = RotatingFileHandler(log_dir / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    emitter = GuiLogEmitter()
    gui_handler = GuiLogHandler(emitter)
    gui_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(gui_handler)
    return logger, emitter

