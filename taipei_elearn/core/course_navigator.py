from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin


class CourseNavigationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MaterialEntry:
    title: str
    url: str
    strategy: str


class CourseNavigator:
    SKIP_TITLES = ("正式測驗", "問卷", "滿意度", "客服中心")
    BLOCK_TITLES = ("退選", "推薦", "取消", "登出", "問卷", "調查", "測驗", "返回", "上一步", "論壇", "討論區")
    SCORM_ENTER_SELECTORS = (
        'button#n[name="mode"][value="normal"]',
        'form[action*="/mod/scorm/player.php"] button[name="mode"][value="normal"]',
        'form[action*="/mod/scorm/player.php"] input[type="submit"][name="mode"][value="normal"]',
    )
    MATERIAL_SELECTORS = (
        'a[href*="/mod/scorm/view.php"]',
        'a[href*="/mod/scorm/player.php"]',
        'a[href*="/mod/resource/view.php"]',
        'a[href*="/mod/page/view.php"]',
        "a[onclick*='launchActivity']",
    ) + SCORM_ENTER_SELECTORS

    def __init__(self) -> None:
        self.media_started = False

    def open_course(self, page, course_url: str) -> list[MaterialEntry]:
        page.goto(course_url, wait_until="domcontentloaded", timeout=30_000)
        entries = self.discover_materials(page)
        if not entries:
            raise CourseNavigationError("找不到可靠教材入口；已停止，不推測入口。")
        return entries

    def discover_materials(self, page) -> list[MaterialEntry]:
        links = page.locator('a[href*="/mod/scorm/view.php?id="]').evaluate_all(
            "els => els.map(a => ({title:(a.textContent||'').replace(/\\s+/g,' ').trim(), href:a.getAttribute('href')||''}))"
        )
        result = [
            MaterialEntry(item["title"], urljoin(page.url, item["href"]), "scorm")
            for item in links
            if item["title"] and not any(word in item["title"] for word in self.SKIP_TITLES)
        ]
        if result:
            return result
        legacy = page.locator("a[onclick*='launchActivity']").evaluate_all(
            "els => els.map(a => ({title:(a.textContent||'').replace(/\\s+/g,' ').trim(), onclick:a.getAttribute('onclick')||''}))"
        )
        return [
            MaterialEntry(item["title"], item["onclick"], "launchActivity")
            for item in legacy
            if item["title"] and not any(word in item["title"] for word in ("環境檢測", "新手上路", "前言"))
        ]

    def enter_material(self, page, entry: MaterialEntry):
        if entry.strategy == "scorm":
            # 平台有些課程以新分頁開 player；等待原頁 navigation 會永久卡住。
            # 掃描得到的 SCORM URL 已含唯一活動 ID，直接導向最穩定。
            page.goto(entry.url, wait_until="domcontentloaded", timeout=30_000)
            if "/mod/scorm/player.php" not in page.url:
                activity_id = re.search(r"[?&]id=(\d+)", entry.url)
                retry_link = (
                    page.locator(
                        f'a[href*="/mod/scorm/view.php?id={activity_id.group(1)}"]:visible'
                    )
                    if activity_id else page.locator("a[href='__missing_scorm_id__']")
                )
                if retry_link.count() == 1:
                    # 部分課程首次只初始化 SCORM 並返回課程頁；同入口再進一次才有 player。
                    page.goto(entry.url, wait_until="domcontentloaded", timeout=30_000)
            player_page = self.find_player_page(page)
            if player_page is not None:
                player_page.wait_for_timeout(1000)
                self.media_started = self.ensure_media_started(player_page)
                return player_page

            # 部分 SCORM view 頁仍有一層明確的「進入」表單。
            # 交由 penetrate_to_player 持續穿透，不能在此過早判定失敗。
            return page
        match = re.search(r"launchActivity\(this,\s*(['\"])(.*?)\1,\s*(['\"])(.*?)\3\)", entry.url)
        if not match:
            raise CourseNavigationError("無法解析 launchActivity 教材入口。")
        title = entry.title
        locator = page.locator("a[onclick*='launchActivity']", has_text=title)
        if locator.count() != 1:
            raise CourseNavigationError(f"教材入口不唯一：{title}")
        locator.click()
        self._wait_for_terminal_or_next_layer(page)
        return page

    def penetrate_to_player(self, page, max_steps: int = 12):
        """沿平台明確教材入口前進；每個元素只點一次，抵達 player 即停止。"""
        clicked: set[str] = set()
        for _ in range(max_steps):
            player_page = self.find_player_page(page)
            if player_page is not None:
                return player_page
            candidate_locator = page.locator(", ".join(self.MATERIAL_SELECTORS))
            candidates = candidate_locator.evaluate_all(
                """els => els.map((el, index) => ({
                    index,
                    text:(el.textContent||'').replace(/\\s+/g,' ').trim(),
                    href:el.href||'',
                    onclick:el.getAttribute('onclick')||'',
                    tag:(el.tagName||'').toLowerCase(),
                    id:el.id||'',
                    name:el.getAttribute('name')||'',
                    value:el.getAttribute('value')||''
                }))"""
            )
            chosen = None
            for item in candidates:
                signature = (
                    f"{page.url}|{item['href']}|{item['onclick']}|{item['tag']}|"
                    f"{item['id']}|{item['name']}|{item['value']}|{item['text']}"
                )
                if signature in clicked or any(word in item["text"] for word in self.BLOCK_TITLES):
                    continue
                chosen = (item, signature)
                break
            if not chosen:
                raise CourseNavigationError("沒有新的可靠教材入口；停止穿透，避免重複開啟。")
            item, signature = chosen
            clicked.add(signature)
            if item["href"] and "/mod/" in item["href"]:
                page.goto(item["href"], wait_until="domcontentloaded", timeout=30_000)
            elif item["onclick"]:
                locator = page.locator("a[onclick*='launchActivity']", has_text=item["text"])
                if locator.count() != 1:
                    raise CourseNavigationError(f"教材入口不唯一：{item['text']}")
                locator.click()
                self._wait_for_terminal_or_next_layer(page)
            elif (
                item["tag"] in {"button", "input"}
                and item["name"] == "mode"
                and item["value"] == "normal"
            ):
                candidate_locator.nth(item["index"]).click()
                player_page = self._wait_for_player(page)
                if player_page is not None:
                    return player_page
            else:
                raise CourseNavigationError("教材入口類型不受支援；停止穿透。")
        raise CourseNavigationError(f"教材穿透超過 {max_steps} 層；停止避免無限點擊。")

    @classmethod
    def find_player_page(cls, page):
        candidates = [page]
        context = getattr(page, "context", None)
        for candidate in getattr(context, "pages", ()):
            if candidate not in candidates:
                candidates.append(candidate)
        for candidate in reversed(candidates):
            try:
                is_closed = getattr(candidate, "is_closed", lambda: False)
                if not is_closed() and cls.is_player(candidate):
                    return candidate
            except Exception:
                continue
        return None

    def _wait_for_player(self, page, attempts: int = 20):
        for _ in range(attempts):
            player_page = self.find_player_page(page)
            if player_page is not None:
                return player_page
            page.wait_for_timeout(250)
        return None

    @staticmethod
    def is_player(page) -> bool:
        if "/mod/scorm/player.php" in page.url:
            return True
        return page.locator(
            "#scorm_object, #scorm_layout, iframe[id*='scorm'], iframe[name*='scorm']"
        ).count() > 0

    def ensure_media_started(self, page) -> bool:
        """若 SCORM 內容是 HTML5 video，處理 Chrome 阻擋 autoplay 的情況。"""
        iframe = page.locator("#scorm_object, iframe[id*='scorm'], iframe[name*='scorm']")
        if iframe.count():
            try:
                iframe.first.wait_for(state="attached", timeout=15_000)
            except Exception:
                pass
        for frame in page.frames[1:]:
            videos = frame.locator("video")
            if videos.count() == 0:
                continue
            video = videos.first
            result = video.evaluate(
                """async v => {
                    if (!v.paused && v.currentTime > 0) return {ok:true, already:true};
                    try { await v.play(); return {ok:true, already:false}; }
                    catch (error) { return {ok:false, error:String(error)}; }
                }"""
            )
            if not result.get("ok"):
                raise CourseNavigationError(f"影片無法開始播放：{result.get('error', '未知錯誤')}")
            try:
                frame.wait_for_function(
                    "() => { const v=document.querySelector('video'); return v && !v.paused && v.currentTime > 0; }",
                    timeout=10_000,
                )
            except Exception as exc:
                raise CourseNavigationError("已呼叫播放，但影片時間沒有前進。") from exc
            return True
        return False

    def _wait_for_terminal_or_next_layer(self, page) -> None:
        selectors = ", ".join(self.MATERIAL_SELECTORS)
        try:
            page.wait_for_function(
                "selectors => location.href.includes('/mod/scorm/player.php') || "
                "document.querySelector('#scorm_object, #scorm_layout, iframe[id*=scorm], iframe[name*=scorm]') || "
                "document.querySelector(selectors)",
                arg=selectors,
                timeout=15_000,
            )
        except Exception as exc:
            raise CourseNavigationError("教材點擊後未出現 player 或下一層入口。") from exc
