import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from taipei_elearn.support.logging_setup import configure_logging
from taipei_elearn.support.settings import AppSettings
from taipei_elearn.ui.main_window import MainWindow
from taipei_elearn.ui.styles import APP_STYLE


def run() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("臺北 e 大學習輔助程式")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    settings = AppSettings.load()
    logger, gui_log = configure_logging(settings.log_dir)
    window = MainWindow(settings, logger, gui_log)
    window.show()
    return app.exec()

