from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from taipei_elearn.ui.widgets import PageHeader, StateBanner


class LogsSettingsPage(QWidget):
    def __init__(self, profile_path: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(PageHeader("執行日誌／設定", "診斷資訊不包含帳號密碼。"))
        banner = StateBanner()
        banner.show_state("success", "日誌系統已就緒。")
        layout.addWidget(banner)
        label = QLabel(f"Chrome 專用 profile：{profile_path}")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("執行日誌會顯示於此。")
        layout.addWidget(self.log_view, 1)

    def append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

