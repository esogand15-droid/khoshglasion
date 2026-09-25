import pytest
from fastapi import HTTPException

from backend.app.content.links import channel_message_url
from backend.app.models.automation import DraftPost
from backend.app.security.deps import assert_editor, assert_publisher
from backend.app.services.autopost import remember_version


class Admin:
    def __init__(self, role):
        self.role = role


def test_published_link_uses_username_or_private_channel_path():
    assert channel_message_url(-100123, 9, "Rotbeland1") == "https://t.me/Rotbeland1/9"
    assert channel_message_url(-100123456, 9, None) == "https://t.me/c/123456/9"
    assert channel_message_url(None, 9, "Rotbeland1") is None


def test_viewer_cannot_publish_and_editor_cannot_either():
    assert_editor(Admin("EDITOR"))
    assert_publisher(Admin("ADMIN"))
    with pytest.raises(HTTPException):
        assert_editor(Admin("VIEWER"))
    with pytest.raises(HTTPException):
        assert_publisher(Admin("EDITOR"))


def test_version_history_keeps_the_previous_body():
    draft = DraftPost(body="نسخه اول که برای تاریخچه کافی است", source_content="منبع دست نخورده", version=1)
    remember_version(draft, "نسخه دوم که جایگزین شد و هنوز بلند است", "edit")
    assert "نسخه اول" in (draft.versions_json or "")
    assert draft.body.startswith("نسخه دوم")
    assert draft.source_content == "منبع دست نخورده"
