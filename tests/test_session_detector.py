from taipei_elearn.core.session_detector import LoginState, SessionDetector


class Locator:
    def __init__(self, visible): self.visible = visible
    @property
    def first(self): return self
    def is_visible(self, timeout): return self.visible


class Page:
    def __init__(self, url, visible=()):
        self.url = url
        self.visible = set(visible)
    def locator(self, selector): return Locator(selector in self.visible)


def test_logged_out_from_login_url():
    assert SessionDetector().detect(Page("https://elearning.taipei/mpage/login")).state is LoginState.LOGGED_OUT


def test_logged_in_selector_wins():
    page = Page("https://elearning.taipei/mpage/home", ("a[href*='logout']:has-text('登出')",))
    assert SessionDetector().detect(page).state is LoginState.LOGGED_IN


def test_expired_wins_over_login():
    page = Page("https://elearning.taipei/mpage/login", ("text=登入逾時", "input[type='password']"))
    assert SessionDetector().detect(page).state is LoginState.EXPIRED


def test_login_form_wins_over_member_words_on_public_page():
    page = Page(
        "https://elearning.taipei/mpage/home",
        ("input[type='password']", "nav a:has-text('學習紀錄')"),
    )
    assert SessionDetector().detect(page).state is LoginState.LOGGED_OUT


def test_unknown_page():
    assert SessionDetector().detect(Page("https://example.invalid/")).state is LoginState.UNKNOWN
