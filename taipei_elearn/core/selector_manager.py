from dataclasses import dataclass


@dataclass(frozen=True)
class SelectorGroup:
    name: str
    selectors: tuple[str, ...]


class SelectorManager:
    """集中管理實站 selectors 與備援策略。"""

    LOGIN_FORM = SelectorGroup(
        "登入表單",
        (
            "input[placeholder*='身分證字號']",
            "input[type='password']",
            "form:has-text('驗證碼')",
            "a:has-text('台北通登入')",
        ),
    )
    LOGGED_IN = SelectorGroup(
        "已登入",
        (
            "a[href*='logout']:has-text('登出')",
            "nav a:has-text('我的課程')",
            "nav a:has-text('學習紀錄')",
        ),
    )
    SESSION_EXPIRED = SelectorGroup(
        "登入逾時",
        (
            "text=登入逾時",
            "text=連線逾時",
            "text=Session expired",
            "text=請重新登入",
        ),
    )
    LEARNING_RECORD_TABLE = SelectorGroup(
        "學習紀錄表格",
        ("#applySelection", "table.fet-table"),
    )
