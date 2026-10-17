import yt_dlp
from yt_dlp.networking.exceptions import HTTPError, TransportError


""" Base of every error MP3Vault reports to the user. `user_message` is what the UI shows;
`detail` keeps yt-dlp's original text for the log. The UI decides by TYPE, never by searching
error strings, so yt-dlp rewording a message can only affect classify() below. """
class MP3VaultError(Exception):
    user_message = "Something went wrong."

    def __init__(self, detail: str = ""):
        super().__init__(detail or self.user_message)
        self.detail = detail


class BadRequest(MP3VaultError):
    user_message = "Bad request (Error 400). Please check the URL."


class AccessDenied(MP3VaultError):
    user_message = "Access denied by YouTube (Error 403). Try again later or update yt-dlp."


class NotFound(MP3VaultError):
    user_message = "Video not found (Error 404)."


class ServerError(MP3VaultError):
    user_message = "YouTube server error. Please try again later."


class TruncatedId(MP3VaultError):
    user_message = "The YouTube video ID is incomplete or truncated."


class VideoUnavailable(MP3VaultError):
    user_message = "This video is unavailable (deleted, private or blocked)."


class NetworkError(MP3VaultError):
    user_message = "Network error. Please check your internet connection."


class FFmpegMissing(MP3VaultError):
    user_message = "FFmpeg was not found. Install FFmpeg (or put ffmpeg.exe next to MP3Vault) and try again."


""" Anything not recognized: shows yt-dlp's own text, without its "ERROR:" prefix """
class DownloadFailed(MP3VaultError):
    @property
    def user_message(self):
        return f"Download failed: {self.detail}" if self.detail else "Download failed."


HTTP_STATUS_ERRORS = {400: BadRequest, 403: AccessDenied, 404: NotFound}


def _clean(text: str):
    text = text.strip()
    return text[len("ERROR:"):].strip() if text.startswith("ERROR:") else text


""" Translates any exception from yt-dlp (or the network) into an MP3VaultError subclass.
Prefers the ORIGINAL exception yt-dlp wraps (DownloadError.exc_info and its .cause) over the
message text; the text checks below are the fallback for errors yt-dlp only reports as text
(verified on real errors: unavailable/truncated -> ExtractorError, no network -> TransportError). """
def classify(exc: BaseException) -> MP3VaultError:
    if isinstance(exc, MP3VaultError):
        return exc

    detail = _clean(str(exc))
    candidates = [exc]
    if isinstance(exc, yt_dlp.utils.DownloadError) and exc.exc_info and exc.exc_info[1] is not None:
        candidates.append(exc.exc_info[1])
    candidates += [getattr(c, "cause", None) for c in list(candidates)]

    for candidate in candidates:
        if isinstance(candidate, HTTPError):
            if candidate.status in HTTP_STATUS_ERRORS:
                return HTTP_STATUS_ERRORS[candidate.status](detail)
            if candidate.status >= 500:
                return ServerError(detail)
        if isinstance(candidate, (TransportError, ConnectionError, TimeoutError)):
            return NetworkError(detail)

    lower = detail.lower()
    if "ffmpeg not found" in lower or "ffprobe and ffmpeg not found" in lower:
        return FFmpegMissing(detail)
    if "youtube:truncated_id" in lower or "incomplete youtube id" in lower:
        return TruncatedId(detail)
    for status, errorClass in HTTP_STATUS_ERRORS.items():
        if f"http error {status}" in lower:
            return errorClass(detail)
    if "http error 5" in lower:
        return ServerError(detail)
    if "unavailable" in lower or "private video" in lower:
        return VideoUnavailable(detail)
    return DownloadFailed(detail)
