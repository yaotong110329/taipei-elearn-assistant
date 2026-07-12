from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from taipei_elearn.core.selector_manager import SelectorGroup, SelectorManager


class LoginState(str, Enum):
    LOGGED_IN = "已登入"
    LOGGED_OUT = "未登入"
    EXPIRED = "登入逾時"
    UNKNOWN = "無法判定"


@dataclass(frozen=True)
class SessionResult:
    state: LoginState
    detail: str
    url: str = ""


class PageLike(Protocol):
    @property
    def url(self) -> str: ...
    def locator(self, selector: str): ...


class SessionDetector:
    def detect(self, page: PageLike) -> SessionResult:
        url = page.url
        if self._visible(page, SelectorManager.SESSION_EXPIRED):
            return SessionResult(LoginState.EXPIRED, "頁面顯示登入逾時", url)
        if self._visible(page, SelectorManager.LOGIN_FORM) or "/login" in url.lower():
            return SessionResult(LoginState.LOGGED_OUT, "目前位於登入頁", url)
        if self._visible(page, SelectorManager.LOGGED_IN):
            return SessionResult(LoginState.LOGGED_IN, "找到會員功能或登出連結", url)
        return SessionResult(LoginState.UNKNOWN, "找不到可靠登入狀態特徵", url)

    @staticmethod
    def _visible(page: PageLike, group: SelectorGroup) -> bool:
        for selector in group.selectors:
            try:
                if page.locator(selector).first.is_visible(timeout=500):
                    return True
            except Exception:
                continue
        return False
