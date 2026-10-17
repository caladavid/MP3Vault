import os

import yt_dlp

from core import naming, tagging, ytdl


""" Downloads and tags a single video URL — the shared core reused by the single-URL button and,
per-item, by the URL queue. Returns a dict rather than reporting anything itself, so a caller
processing many URLs (the queue) can show ONE combined summary:
    {"success", "filename", "error", "cancelled", "tagError"}
`session` is a ytdl.DownloadSession: its hook drives progress/cancel, and it cleans up after a
cancel. """
def download_single(url: str, title: str, uploader: str, album: str, folder: str,
                    audio_format: str, audio_quality: str, session: ytdl.DownloadSession):
    ydl_opts = {
        'format': 'bestaudio/best',
        'writethumbnail': audio_format != 'wav',
        'postprocessors': ytdl.build_audio_postprocessors(audio_format, audio_quality),
        'noplaylist': True,
        'progress_hooks': [session.hook],
        'extract_flat': 'in-playlist',
        'nocolor': True,
        "outtmpl": f'{folder}/%(title)s.%(ext)s',
        'extractor_args': ytdl.EXTRACTOR_ARGS,
    }
    result = {"success": False, "filename": None, "error": None, "cancelled": False, "tagError": None}

    # Snapshot so a cancellation mid-download can clean up the .part/.webp/etc it leaves behind
    # (verified: yt_dlp doesn't clean these up itself when aborted via DownloadCancelled).
    download_path = os.path.normpath(folder)  # Ensure a valid path format
    filesBefore = ytdl.list_folder(download_path)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_downloaded = ydl.extract_info(url, download=True)

            cleanTitle, finalFilename = naming.build_clean_title_and_filename(uploader, title, audio_format)
            file_path = naming.safe_join(download_path, finalFilename)

            # yt-dlp names the file after the ORIGINAL video title, not our (possibly edited)
            # title/artist — ydl.prepare_filename() gives the exact name yt-dlp actually wrote,
            # whereas searching the folder for the edited title silently finds nothing.
            downloadedFilename = os.path.basename(ydl.prepare_filename(info_downloaded))
            downloadedFilename = os.path.splitext(downloadedFilename)[0] + f".{audio_format}"
            old_filepath = naming.safe_join(download_path, downloadedFilename)

        if os.path.exists(old_filepath):
            # os.replace (not os.rename) because on Windows os.rename raises
            # FileExistsError if file_path already exists (e.g. re-downloading a track)
            if old_filepath != file_path:
                os.replace(old_filepath, file_path)
                print(f"File renamed successfully: {file_path}")
            else:
                print(f"No renaming needed, using: {file_path}")
        else:
            print(f"Error: Expected downloaded file not found: {old_filepath}")

        if not os.path.exists(file_path):
            result["error"] = "Downloaded file not found."
            return result

        # A tagging failure doesn't undo a successful download: report it alongside success
        try:
            tagging.write_tags(file_path, cleanTitle, uploader, album)
        except Exception as e:
            result["tagError"] = str(e)

        print(f"Downloaded: {finalFilename}")
        result.update(success=True, filename=finalFilename)
        return result

    except yt_dlp.utils.DownloadCancelled:
        session.remove_cancelled_files(download_path, filesBefore)
        result["cancelled"] = True
        return result

    except Exception as e:
        result["error"] = str(e)
        return result
