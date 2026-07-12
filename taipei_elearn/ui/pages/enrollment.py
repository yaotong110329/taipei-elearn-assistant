from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from taipei_elearn.ui.widgets import PageHeader, StateBanner, make_button, make_table


class EnrollmentPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(PageHeader("選課", "階段 1 僅用 30 筆模擬搜尋結果驗證清單。"))
        banner = StateBanner()
        banner.show_state("success", "模擬搜尋完成；捲動後每列文字應保持可見。")
        layout.addWidget(banner)
        rows = [["☑", f"常用關鍵字搜尋結果 {i:02d}：完整長名稱課程", f"{1 + i % 3} 小時", f"C{i:04d}", "可報名", "尚未處理"] for i in range(1, 31)]
        self.table = make_table(["選取", "課程名稱", "時數", "課程 ID", "可否報名", "狀態"], rows)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        for text in ("管理常用關鍵字", "搜尋全部關鍵字", "開始報名"):
            button = make_button(text, text == "開始報名")
            button.setEnabled(False)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

