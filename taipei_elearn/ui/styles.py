APP_STYLE = """
QWidget { background: #f4f6f8; color: #17202a; font-family: "Microsoft JhengHei UI"; font-size: 14px; }
QMainWindow, QScrollArea, QAbstractScrollArea::viewport { background: #f4f6f8; }
QFrame#sidebar { background: #18324a; }
QFrame#sidebar QLabel#brand { background: #18324a; color: #ffffff; font-size: 20px; font-weight: 700; padding: 8px; }
QPushButton { min-height: 38px; padding: 0 14px; border: 1px solid #9aa8b5; border-radius: 5px; background: white; }
QPushButton:hover { background: #e8f1f8; border-color: #2878a9; }
QPushButton:pressed { background: #d4e6f1; }
QPushButton:disabled { color: #66737f; background: #e4e8eb; border-color: #b7c0c7; }
QPushButton#primary { background: #176b9c; color: white; border-color: #176b9c; font-weight: 600; }
QPushButton#nav { color: #edf5fa; background: transparent; border: 0; text-align: left; padding-left: 16px; }
QPushButton#nav:hover { background: #264b69; }
QPushButton#nav:checked { background: #2d648c; border-left: 4px solid #70c6f1; }
QLabel#pageTitle { font-size: 23px; font-weight: 700; }
QLabel#courseProgress { background: #eef5ff; border: 1px solid #a9c7eb; border-radius: 6px; padding: 10px 12px; color: #173b63; font-weight: 600; }
QFrame#card { background: white; border: 1px solid #d5dce2; border-radius: 7px; }
QTableWidget { background: white; alternate-background-color: #eef4f7; gridline-color: #d7dee4; selection-background-color: #bfdff0; selection-color: #101820; }
QHeaderView::section { background: #e6edf2; padding: 8px; border: 0; border-right: 1px solid #cbd5dc; font-weight: 600; }
QScrollBar:vertical { background: #edf1f4; width: 16px; margin: 0; }
QScrollBar::handle:vertical { background: #899aa7; min-height: 32px; border-radius: 7px; margin: 2px; }
QScrollBar:horizontal { background: #edf1f4; height: 16px; }
QScrollBar::handle:horizontal { background: #899aa7; min-width: 32px; border-radius: 7px; margin: 2px; }
QStatusBar { background: #e3e9ed; border-top: 1px solid #c7d0d7; }
QLineEdit, QPlainTextEdit { background: white; border: 1px solid #9aa8b5; border-radius: 4px; padding: 7px; }
"""
