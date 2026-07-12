from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from taipei_elearn.ui.widgets import PageHeader, StateBanner, make_button


class DashboardPage(QWidget):
    open_browser_requested = Signal()
    detect_login_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(PageHeader("儀表板", "正式 Chrome 與臺北 e 大登入狀態。帳密只由使用者在 Chrome 輸入。"))
        grid = QGridLayout()
        grid.addWidget(QLabel("Chrome 連線狀態"), 0, 0)
        self.browser_status = QLabel("尚未連線")
        grid.addWidget(self.browser_status, 0, 1)
        grid.addWidget(QLabel("臺北 e 大登入狀態"), 1, 0)
        self.login_status = QLabel("尚未偵測")
        grid.addWidget(self.login_status, 1, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        self.banner = StateBanner()
        self.banner.show_state("empty", "請開啟 Chrome；首次使用請在瀏覽器手動登入。")
        layout.addWidget(self.banner)
        actions = QGridLayout()
        self.open_button = make_button("開啟正式 Chrome", True)
        self.detect_button = make_button("重新偵測登入")
        self.records_button = make_button("重新開啟學習紀錄")
        self.records_button.setEnabled(False)
        actions.addWidget(self.open_button, 0, 0)
        actions.addWidget(self.detect_button, 0, 1)
        actions.addWidget(self.records_button, 1, 0, 1, 2)
        layout.addLayout(actions)
        layout.addStretch()
        self.open_button.clicked.connect(self.open_browser_requested)
        self.detect_button.clicked.connect(self.detect_login_requested)

    def set_busy(self, busy: bool) -> None:
        self.open_button.setEnabled(not busy)
        self.detect_button.setEnabled(not busy)
        if busy:
            self.banner.show_state("loading", "處理中，GUI 仍可操作。")
