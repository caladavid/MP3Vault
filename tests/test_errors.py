import sys

import pytest
import yt_dlp
from yt_dlp.networking.exceptions import HTTPError, TransportError

from core import errors


""" Builds a DownloadError the way yt-dlp does: message text plus the wrapped original """
def _download_error(message, original=None):
    exc_info = None
    if original is not None:
        try:
            raise original
        except Exception:
            exc_info = sys.exc_info()
    return yt_dlp.utils.DownloadError(message, exc_info)


def _http_error(status):
    response = type("Response", (), {"status": status, "reason": "x", "headers": {}, "url": "u", "close": lambda self: None})()
    return HTTPError(response)


@pytest.mark.parametrize("status, expected", [
    (400, errors.BadRequest), (403, errors.AccessDenied), (404, errors.NotFound), (503, errors.ServerError),
])
def test_http_status_from_wrapped_exception(status, expected):
    exc = _download_error("ERROR: something", _http_error(status))
    assert isinstance(errors.classify(exc), expected)


def test_network_error_from_transport_error():
    # Real shape (verified): ExtractorError text, TransportError original, ConnectionRefusedError cause
    original = TransportError("[WinError 10061] No connection could be made", cause=ConnectionRefusedError())
    exc = _download_error("ERROR: [youtube] x: Unable to download API page: [WinError 10061]", original)
    assert isinstance(errors.classify(exc), errors.NetworkError)


@pytest.mark.parametrize("message, expected", [
    # Real texts (verified): the old check for "Video unavailable" never matched this one
    ("ERROR: [youtube] xxxxxxxxxxx: This video is unavailable", errors.VideoUnavailable),
    ("ERROR: [youtube] x: Private video. Sign in if you've been granted access", errors.VideoUnavailable),
    ("ERROR: [youtube:truncated_id] jNQXAC9IV: Incomplete YouTube ID jNQXAC9IV.", errors.TruncatedId),
    ("ERROR: Postprocessing: ffprobe and ffmpeg not found. Please install or provide the path", errors.FFmpegMissing),
    ("ERROR: unable to download video data: HTTP Error 403: Forbidden", errors.AccessDenied),
    ("ERROR: unable to download video data: HTTP Error 502: Bad Gateway", errors.ServerError),
])
def test_classified_from_text(message, expected):
    assert isinstance(errors.classify(_download_error(message)), expected)


def test_unknown_error_keeps_detail_without_prefix():
    classified = errors.classify(_download_error("ERROR: [youtube] x: Something new happened"))
    assert isinstance(classified, errors.DownloadFailed)
    assert classified.user_message == "Download failed: [youtube] x: Something new happened"
    assert not classified.user_message.startswith("Download failed: ERROR")


def test_plain_connection_error():
    assert isinstance(errors.classify(ConnectionResetError()), errors.NetworkError)


def test_already_classified_is_returned_as_is():
    original = errors.AccessDenied("detail")
    assert errors.classify(original) is original


def test_detail_kept_for_log():
    classified = errors.classify(_download_error("ERROR: [youtube] x: This video is unavailable"))
    assert classified.detail == "[youtube] x: This video is unavailable"
    assert classified.user_message == errors.VideoUnavailable.user_message
