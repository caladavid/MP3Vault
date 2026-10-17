import logging
import os

import yt_dlp

from core import naming, tagging, ytdl
from core.models import BatchResult, DownloadOptions, TrackResult


log = logging.getLogger(__name__)


""" Metadata-only lookup (no download). Errors propagate to the caller. """
def fetch_info(url: str):
    with yt_dlp.YoutubeDL(ytdl.info_options()) as ydl:
        return ydl.extract_info(url, download=False)


""" yt-dlp options shared by every real download """
def _download_options(opts: DownloadOptions, session: ytdl.DownloadSession, **extra):
    ydl_opts = {
        'format': 'bestaudio/best',
        'writethumbnail': opts.audio_format != 'wav',
        'postprocessors': ytdl.build_audio_postprocessors(opts.audio_format, opts.audio_quality),
        'progress_hooks': [session.hook],
        "outtmpl": f'{opts.folder}/%(title)s.%(ext)s',
        'extractor_args': ytdl.EXTRACTOR_ARGS,
        'logger': ytdl.YTDLP_LOGGER,
        'color': ytdl.NO_COLOR,
    }
    ydl_opts.update(extra)
    return ydl_opts


""" Renames the file yt-dlp produced to its final name and tags it — the last step shared by the
single and playlist flows. Returns (exists, tagError). """
def _finalize_track(old_path: str, new_path: str, title: str, artist: str, album: str, track_number=None):
    if os.path.exists(old_path):
        # os.replace (not os.rename) because on Windows os.rename raises
        # FileExistsError if new_path already exists (e.g. re-downloading a track)
        if old_path != new_path:
            os.replace(old_path, new_path)
            log.info("Renamed to %s", new_path)
        else:
            log.info("No renaming needed: %s", new_path)
    else:
        log.error("Expected downloaded file not found: %s", old_path)

    if not os.path.exists(new_path):
        return False, None

    # A tagging failure doesn't undo a successful download: report it alongside success
    try:
        tagging.write_tags(new_path, title, artist, album, track_number=track_number)
    except Exception as e:
        log.exception("Tagging failed for %s", new_path)
        return True, str(e)
    return True, None


""" Downloads and tags a single video URL — reused by the single-URL button and, per-item, by the
URL queue. `session` is a ytdl.DownloadSession: its hook drives progress/cancel, and it cleans
up after a cancel or error. """
def download_single(url: str, title: str, uploader: str, album: str,
                    opts: DownloadOptions, session: ytdl.DownloadSession) -> TrackResult:
    ydl_opts = _download_options(opts, session, noplaylist=True, extract_flat='in-playlist')

    # Snapshot so a cancellation mid-download can clean up the .part/.webp/etc it leaves behind
    # (verified: yt_dlp doesn't clean these up itself when aborted via DownloadCancelled).
    folder = os.path.normpath(opts.folder)
    filesBefore = ytdl.list_folder(folder)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            session.attach(ydl)
            info_downloaded = ydl.extract_info(url, download=True)
            # yt-dlp names the file after the ORIGINAL video title, not our (possibly edited)
            # title/artist — ydl.prepare_filename() gives the exact name yt-dlp actually wrote,
            # whereas searching the folder for the edited title silently finds nothing.
            downloadedBase = os.path.splitext(os.path.basename(ydl.prepare_filename(info_downloaded)))[0]

        cleanTitle, finalFilename = naming.build_clean_title_and_filename(uploader, title, opts.audio_format)
        exists, tagError = _finalize_track(
            naming.safe_join(folder, f"{downloadedBase}.{opts.audio_format}"),
            naming.safe_join(folder, finalFilename),
            cleanTitle, uploader, album,
        )
        if not exists:
            return TrackResult("error", error="Downloaded file not found.")

        log.info("Downloaded: %s", finalFilename)
        return TrackResult("ok", filename=finalFilename, tag_error=tagError)

    except yt_dlp.utils.DownloadCancelled:
        log.info("Download cancelled: %s", url)
        session.remove_leftovers(folder, filesBefore)
        return TrackResult("cancelled")

    except Exception as e:
        log.exception("Download failed for %s", url)
        session.remove_leftovers(folder, filesBefore, partial_only=True)
        return TrackResult("error", error=str(e))


""" Downloads the given playlist videos (dicts from ytdl.extract_playlist_videos, already
filtered to the user's selection) and tags each one with its playlist position. Videos whose
final file already exists are skipped — asking per-song would be impractical for a multi-track
playlist. """
def download_playlist(url: str, videos: list, uploader: str, album: str,
                      opts: DownloadOptions, session: ytdl.DownloadSession) -> BatchResult:
    result = BatchResult()
    folder = os.path.normpath(opts.folder)
    uploaderClean = naming.clean_uploader(uploader.strip())

    # Predicts each selected video's final filename with the same helper the rename below uses
    selectedIndices = []
    for video in videos:
        predictedName = naming.predict_playlist_filename(uploaderClean, video['title'], opts.audio_format)
        if os.path.exists(os.path.join(folder, predictedName)):
            result.skipped_existing += 1
        else:
            selectedIndices.append(str(video['playlistIndex']))

    if not selectedIndices:
        return result
    result.attempted = len(selectedIndices)

    ydl_opts = _download_options(
        opts, session,
        add_metadata=True,
        socket_timeout=60,
        playlist_items=",".join(selectedIndices),  # Descargar solo los videos seleccionados
    )

    # yt-dlp writes a thumbnail for the playlist itself (not just each video), and nothing ever
    # embeds/deletes that one — snapshot the folder now so it can be removed afterwards.
    filesBefore = ytdl.list_folder(folder)
    playlistThumbStem = None

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            session.attach(ydl)
            playlist_info = ydl.extract_info(url, download=True)
            # The playlist-level thumbnail is named after the playlist itself (verified:
            # "Popular Music Videos.NA" from prepare_filename -> "Popular Music Videos.jpg").
            playlistThumbStem = os.path.splitext(os.path.basename(ydl.prepare_filename(playlist_info)))[0]

            for fallbackIndex, video in enumerate(playlist_info.get("entries") or [], start=1):
                title = (video.get('title') or 'Desconocido').strip()
                # playlist_index is the video's real position in the playlist (yt_dlp sets it
                # during playlist processing); fall back to loop position only if it's missing.
                trackNumber = video.get('playlist_index') or fallbackIndex

                # yt-dlp wrote "<its sanitized title>.<ext>"; after conversion the extension is the
                # selected format. Renamed through the SAME helper the prediction above uses.
                baseFilename = os.path.splitext(os.path.basename(ydl.prepare_filename(video)).strip())[0]
                exists, tagError = _finalize_track(
                    naming.safe_join(folder, f"{baseFilename}.{opts.audio_format}"),
                    naming.safe_join(folder, naming.playlist_filename(uploaderClean, baseFilename, opts.audio_format)),
                    naming.clean_filename(title), uploaderClean, album, track_number=trackNumber,
                )
                if exists:
                    result.downloaded += 1
                    if tagError:
                        result.tag_errors.append(tagError)
                else:
                    result.failed += 1

    except yt_dlp.utils.DownloadCancelled:
        log.info("Playlist download cancelled: %s", url)
        session.remove_leftovers(folder, filesBefore)
        result.cancelled = True
        return result

    except Exception as e:
        log.exception("Playlist download failed for %s", url)
        session.remove_leftovers(folder, filesBefore, partial_only=True)
        result.error = str(e)
        return result

    # Remove the orphaned playlist-level thumbnail — only the new image named exactly after the
    # playlist, never any other image that showed up in the folder meanwhile.
    for newFile in ytdl.list_folder(folder) - filesBefore:
        stem, ext = os.path.splitext(newFile)
        if stem == playlistThumbStem and ext.lower() in ('.jpg', '.jpeg', '.webp', '.png'):
            try:
                os.remove(os.path.join(folder, newFile))
            except OSError:
                pass

    return result


""" Downloads each URL sequentially through download_single. Each item gets its own metadata
lookup and a fresh session from `new_session()`; `on_item(i, total)` is called before each.
Already-downloaded items are skipped. Cancel (the sessions' shared cancel_event) stops the whole
remaining queue, consistent with the single Cancel button. """
def download_queue(urls: list, opts: DownloadOptions, new_session, on_item=None) -> BatchResult:
    result = BatchResult()
    total = len(urls)

    for i, url in enumerate(urls, start=1):
        session = new_session()
        # Checked here too (not just inside the progress hook) in case Cancel arrives between
        # items, e.g. during the metadata lookup below, which has no progress hook.
        if session.cancel_event.is_set():
            result.cancelled = True
            break

        if on_item:
            on_item(i, total)

        try:
            info = fetch_info(url)
        except Exception as e:
            log.warning("Queue: info failed for %s: %s", url, e)
            result.failed += 1
            continue

        title = (info.get('title') or 'Unknown').strip()
        artist = info.get('artist', info.get('channel', ''))
        album = info.get('album', '')

        _, predictedName = naming.build_clean_title_and_filename(artist, title, opts.audio_format)
        if os.path.exists(os.path.join(os.path.normpath(opts.folder), predictedName)):
            result.skipped_existing += 1
            continue

        result.attempted += 1
        track = download_single(url, title, artist, album, opts, session)
        if track.cancelled:
            result.cancelled = True
            break
        elif track.ok:
            result.downloaded += 1
            if track.tag_error:
                result.tag_errors.append(track.tag_error)
        else:
            result.failed += 1

    return result
