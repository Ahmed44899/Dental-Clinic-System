import pytest


@pytest.fixture(autouse=True)
def isolate_test_media(settings, tmp_path):
    """Give every test its own writable, automatically cleaned media folder."""
    settings.MEDIA_ROOT = tmp_path / "media"