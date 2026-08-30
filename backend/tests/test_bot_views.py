"""Rendering of the bot's task screens: everything a user taps is generated
here, so it can be pinned down without a live Telegram connection."""

from app.bot.handlers import (
    BUTTON_TITLE_LIMIT,
    LIST_LIMIT,
    _delete_confirm_view,
    _format_created_at,
    _list_view,
    _shorten,
    _task_view,
)


def make_task(**overrides) -> dict:
    return {
        "id": 7,
        "title": "Buy milk",
        "description": None,
        "status": "pending",
        "created_at": "2026-08-31T14:22:05+00:00",
        **overrides,
    }


class TestTaskView:
    def test_shows_title_status_and_id(self):
        text, _ = _task_view(make_task())

        assert "Buy milk" in text
        assert "⏳ Pending" in text
        assert "Task #7" in text

    def test_description_is_included_when_present(self):
        text, _ = _task_view(make_task(description="2 liters, semi-skimmed"))
        assert "2 liters, semi-skimmed" in text

    def test_description_line_is_omitted_when_absent(self):
        text, _ = _task_view(make_task(description=None))
        assert "None" not in text

    def test_offers_every_status_as_a_button(self):
        _, keyboard = _task_view(make_task())
        status_row = keyboard.inline_keyboard[0]

        assert [button.callback_data for button in status_row] == [
            "status:7:pending",
            "status:7:in_progress",
            "status:7:completed",
        ]

    def test_the_current_status_is_marked(self):
        _, keyboard = _task_view(make_task(status="in_progress"))
        marked = [b.text for b in keyboard.inline_keyboard[0] if b.text.startswith("• ")]

        assert marked == ["• 🔧 In Progress"]

    def test_offers_delete_and_a_way_back_to_the_list(self):
        _, keyboard = _task_view(make_task())
        actions = {b.callback_data for b in keyboard.inline_keyboard[-1]}
        assert actions == {"askdel:7", "list"}


class TestDeleteConfirmView:
    """The first tap only asks; deleting is irreversible."""

    def test_asks_before_deleting(self):
        text, keyboard = _delete_confirm_view(make_task())

        assert "Delete this task?" in text
        assert "can't be undone" in text
        assert [b.callback_data for b in keyboard.inline_keyboard[0]] == [
            "del:7",
            "open:7",
        ]

    def test_quotes_the_task_being_deleted(self):
        text, _ = _delete_confirm_view(make_task(title="Cancel the subscription"))
        assert "Cancel the subscription" in text

    def test_keeping_it_goes_back_to_the_task_not_the_list(self):
        """The safe choice returns you exactly where you were."""
        _, keyboard = _delete_confirm_view(make_task())
        assert keyboard.inline_keyboard[0][1].callback_data == "open:7"

    def test_the_ask_prefix_is_not_mistaken_for_the_confirm_prefix(self):
        """`askdel:` must not match the `del:` handler, or the first tap would
        delete outright."""
        assert not "askdel:7".startswith("del:")


class TestListView:
    def test_one_button_per_task_opening_that_task(self):
        text, keyboard = _list_view([make_task(id=1), make_task(id=2, title="Call Ana")])

        assert "Your tasks (2)" in text
        assert [row[0].callback_data for row in keyboard.inline_keyboard] == [
            "open:1",
            "open:2",
        ]

    def test_long_lists_are_capped_and_say_so(self):
        tasks = [make_task(id=i) for i in range(LIST_LIMIT + 5)]

        text, keyboard = _list_view(tasks)

        assert len(keyboard.inline_keyboard) == LIST_LIMIT
        assert f"({len(tasks)})" in text
        assert "most recent" in text

    def test_button_labels_stay_short(self):
        long_title = "Remember to " + "very " * 30 + "long task"
        _, keyboard = _list_view([make_task(title=long_title)])

        label = keyboard.inline_keyboard[0][0].text
        assert len(label) <= BUTTON_TITLE_LIMIT + 4  # status emoji + space


class TestHelpers:
    def test_shorten_collapses_whitespace(self):
        assert _shorten("a\n  b   c", 20) == "a b c"

    def test_shorten_truncates_with_an_ellipsis(self):
        assert _shorten("abcdefghij", 5) == "abcd…"

    def test_format_created_at_is_human_readable(self):
        assert _format_created_at("2026-08-31T14:22:05+00:00") == "31 Aug 2026, 14:22"

    def test_format_created_at_tolerates_junk(self):
        assert _format_created_at("not-a-date") == "not-a-date"
        assert _format_created_at(None) == "—"
