from contextlib import nullcontext

from taipei_elearn.core.enrollment_service import EnrollmentCourse, EnrollmentService


class FakeSearchLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    def count(self):
        if self.selector == "#keyword":
            return 1
        if self.selector == "#search_pages":
            return 1
        if self.selector == "option":
            return len(self.page.results[self.page.keyword])
        if self.selector == "submit":
            return 1
        return 0

    def locator(self, selector):
        return FakeSearchLocator(self.page, selector)

    def fill(self, value):
        self.page.keyword = value
        self.page.page_number = 1

    def click(self):
        pass

    def select_option(self, value):
        self.page.page_number = int(value)


class FakeSearchPage:
    def __init__(self):
        self.keyword = ""
        self.page_number = 1
        self.results = {
            "環境教育": [
                [{"courseId": "10", "title": "環境課", "hours": "認證時數1小時", "detailUrl": "u10", "status": "直接報名"}],
                [{"courseId": "20", "title": "共同課", "hours": "認證時數2小時", "detailUrl": "u20", "status": "已報名"}],
            ],
            "人工智慧": [
                [{"courseId": "30", "title": "AI課", "hours": "認證時數1小時", "detailUrl": "u30", "status": "直接報名"}],
            ],
        }

    def goto(self, *_args, **_kwargs):
        self.page_number = 1

    def locator(self, selector):
        return FakeSearchLocator(self, selector)

    def get_by_role(self, *_args, **_kwargs):
        return FakeSearchLocator(self, "submit")

    def expect_navigation(self, **_kwargs):
        return nullcontext()

    def evaluate(self, _script):
        return self.results[self.keyword][self.page_number - 1]


def test_batch_search_excludes_already_enrolled_courses():
    progress = []
    result = EnrollmentService().search(
        FakeSearchPage(), ["環境教育", "人工智慧"], progress.append
    )
    assert result.pages_scanned == 3
    assert len(result.courses) == 2
    assert {course.course_id for course in result.courses} == {"10", "30"}
    assert all(course.can_add for course in result.courses)
    assert progress[-1].endswith("累計 2 門")


def test_each_keyword_stops_after_five_and_excludes_zero_hours():
    page = FakeSearchPage()
    page.results = {
        "環境教育": [
            [
                *[
                    {"courseId": str(index), "title": f"課程{index}", "hours": "認證時數1小時", "detailUrl": f"u{index}", "status": "直接報名"}
                    for index in range(1, 8)
                ],
                {"courseId": "zero", "title": "零時數", "hours": "認證時數0小時", "detailUrl": "uz", "status": "直接報名"},
                {"courseId": "done", "title": "已報名", "hours": "認證時數1小時", "detailUrl": "ud", "status": "已報名"},
            ],
            [{"courseId": "later", "title": "下一頁", "hours": "認證時數1小時", "detailUrl": "ul", "status": "直接報名"}],
        ]
    }
    result = EnrollmentService().search(page, ["環境教育"])
    assert result.pages_scanned == 1
    assert len(result.courses) == 5
    assert {course.course_id for course in result.courses} == {"1", "2", "3", "4", "5"}


class FakeResponse:
    ok = True

    @staticmethod
    def json():
        return {"success": True, "message": "已加入選課口袋"}


class FakeRequest:
    def __init__(self):
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return FakeResponse()


class FakeSimpleLocator:
    def __init__(self, count=1, attribute=None):
        self._count = count
        self.attribute = attribute
        self.clicked = False

    def count(self):
        return self._count

    def get_attribute(self, _name):
        return self.attribute

    def click(self):
        self.clicked = True


class FakeDialog:
    message = "全部報名成功"

    def __init__(self):
        self.accepted = False

    def accept(self):
        self.accepted = True


class FakeEventInfo:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeActionPage:
    def __init__(self):
        self.request = FakeRequest()
        self.goto_urls = []
        self.dialog = FakeDialog()
        self.enroll_button = FakeSimpleLocator()

    def goto(self, url, **_kwargs):
        self.goto_urls.append(url)

    def locator(self, selector):
        if selector == 'meta[name="csrf-token"]':
            return FakeSimpleLocator(attribute="token")
        if selector == "#enroll-all":
            return self.enroll_button
        raise AssertionError(selector)

    def get_by_text(self, *_args, **_kwargs):
        return FakeSimpleLocator(count=0)

    def expect_event(self, *_args, **_kwargs):
        return FakeEventInfo(self.dialog)


def course():
    return EnrollmentCourse(
        "10", "環境課", "認證時數1小時", "u10", "直接報名", True, ("環境教育",)
    )


def test_add_to_pocket_posts_course_id_and_opens_pocket():
    page = FakeActionPage()
    result = EnrollmentService().add_to_pocket(page, [course()])
    assert result.success_count == 1
    assert page.request.posts[0][1]["data"] == {"course_id": "10"}
    assert page.goto_urls[-1] == EnrollmentService.POCKET_URL


def test_enroll_all_clicks_pocket_button_and_accepts_result_dialog():
    page = FakeActionPage()
    result = EnrollmentService().enroll_all(page)
    assert result.success
    assert page.enroll_button.clicked
    assert page.dialog.accepted
