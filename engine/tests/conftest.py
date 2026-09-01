from __future__ import annotations

import pytest

from engine.app.verification.media_fixture import NalPayloadSource, reset_nal_source


@pytest.fixture(autouse=True)
def _reset_specimen_nal_cursor() -> None:
    reset_nal_source()
    NalPayloadSource().reset()
