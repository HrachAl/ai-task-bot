"""Which user an incoming Redis event is addressed to. The single place that
decides who a realtime event reaches, so it is tested on its own."""

import json

from app.realtime.listener import NO_RECIPIENT, _owner_of


def event(user_id) -> str:
    return json.dumps({"type": "task_created", "task": {"id": 1, "user_id": user_id}})


class TestOwnerOf:
    def test_reads_the_user_id_out_of_the_payload(self):
        assert _owner_of(event(42)) == 42

    def test_a_numeric_string_is_still_understood(self):
        assert _owner_of(event("42")) == 42

    def test_malformed_json_addresses_nobody(self):
        assert _owner_of("{not json") == NO_RECIPIENT

    def test_a_payload_without_a_task_addresses_nobody(self):
        assert _owner_of(json.dumps({"type": "task_created"})) == NO_RECIPIENT

    def test_a_task_without_an_owner_addresses_nobody(self):
        assert _owner_of(json.dumps({"task": {"id": 1}})) == NO_RECIPIENT

    def test_no_recipient_can_never_match_a_real_user(self):
        """User ids come from a bigserial, so they are always positive."""
        assert NO_RECIPIENT < 1
