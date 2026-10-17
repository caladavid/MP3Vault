from unittest import mock

import pytest

from core import updates


@pytest.mark.parametrize("a, b", [("2026.07.04", "2026.7.4"), ("2026.10.01", "2026.10.1")])
def test_same_release_different_format_is_equal(a, b):
    assert updates.parse_version_tuple(a) == updates.parse_version_tuple(b)


def test_newer_release_compares_greater():
    assert updates.parse_version_tuple("2026.10.1") > updates.parse_version_tuple("2026.07.04")


def _pypi(version):
    response = mock.Mock()
    response.json.return_value = {"info": {"version": version}}
    return response


def test_newer_version_reported():
    with mock.patch.object(updates.yt_dlp.version, "__version__", "2026.07.04"), \
         mock.patch.object(updates.requests, "get", return_value=_pypi("2026.10.1")):
        assert updates.newer_ytdlp_version() == "2026.10.1"


def test_same_version_not_reported():
    with mock.patch.object(updates.yt_dlp.version, "__version__", "2026.07.04"), \
         mock.patch.object(updates.requests, "get", return_value=_pypi("2026.7.4")):
        assert updates.newer_ytdlp_version() is None
