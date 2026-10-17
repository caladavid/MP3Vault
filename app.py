import logging
import queue
import sys
import os
import threading
import types
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

import yt_dlp

from core import downloader, errors, ffmpeg, logs, naming, settings, updates, ytdl
from core.models import BatchResult, DownloadOptions, Progress, TrackResult
from ui import theme
from ui.dialogs import EditInfoDialog, QueueDialog
from ui.progress_view import ProgressView
from ui.video_views import PlaylistView, SingleVideoView

log = logging.getLogger("mp3vault")

APP_VERSION = "1.2"


# Resolves asset paths both for normal `python app.py` runs and for a PyInstaller-frozen .exe
# (PyInstaller sets sys._MEIPASS, in both onefile and onedir mode, to the bundle's extract folder).
def resourcePath(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)


class MP3Vault:
    def __init__(self, root):
        # Create the main application window
        self.root = root
        self.root.title("MP3Vault")
        self.root.geometry("750x280")
        self.root.resizable(0, 0)
        
        # grid layout
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)  # videoInfoFrame — the only row that should stretch;
        # optionsRow (row 2) and videoConfigFrame (row 3) keep weight=0 (default) so they always get
        # exactly their natural height instead of competing with videoInfoFrame for leftover space —
        # giving row 2 weight=1 here once squeezed optionsRow down to ~1px in the taller (350/700) views.
        
        self.padding = theme.PADDING

        self.regularFont = ctk.CTkFont(family="Lato", size=14);
        self.titleFont = ctk.CTkFont(family="Lato", size=16, weight="bold");
        self.fonts = types.SimpleNamespace(regular=self.regularFont, title=self.titleFont)
        self.folderImg = Image.open(resourcePath("folder.png"));
        self.editImg = Image.open(resourcePath("editar.png"));
        self.urlValue = ctk.StringVar();

        # Views currently on screen (None when not shown); see the ui package
        self.videoView = None       # SingleVideoView or PlaylistView
        self.progressView = None
        self.editDialog = None
        self.queueDialog = None

        self.titleAudioVar = ctk.StringVar()
        self.artistAudioVar = ctk.StringVar()
        self.albumAudioVar = ctk.StringVar()

        # Last folder/format/quality are restored from %APPDATA%\MP3Vault\settings.json and
        # saved again whenever the user changes one of them.
        self.settings = settings.load_settings()
        self.downloadPath = self.settings.last_folder
        self.audioFormatVar = ctk.StringVar(value=self.settings.audio_format)
        self.audioQualityVar = ctk.StringVar(value=self.settings.audio_quality)

        # Set right before spawning a download thread, checked inside DownloadSession.hook (which
        # runs ON that thread) to abort cleanly via yt_dlp.utils.DownloadCancelled instead of
        # killing the thread outright.
        self.cancelRequested = threading.Event()

        # Worker threads post UI work here (see ui / _drainUiQueue)
        self.uiQueue = queue.Queue()
        # Bumped on every new lookup/clear; answers from older lookups are discarded
        self.infoGeneration = 0

        # Inicializar variables para almacenar la información del video
        self.title_video = ""
        self.album_video = ""
        self.channel_video = ""
        self.artist_video = ""
        self.albumArtistVideo = ""
        self.album_thumbnail = ""
        
        #self.root.set_appearance_mode("dark") ARREGLAR

        # Set the application icon
        self.iconPath = resourcePath('icon.ico')
        self.root.iconbitmap(self.iconPath)

        # Tk swallows exceptions raised inside callbacks (button clicks, root.after) and only
        # prints them; send them to the log file too.
        self.root.report_callback_exception = lambda *exc: log.error("Error in UI callback", exc_info=exc)

        self.setupUI();
        self.noURL()
        self.applySettingsToUI()
        self._drainUiQueue()

        threading.Thread(target=self.checkYtDlpUpdate, daemon=True).start()


    """ Open a folder dialog to select the download destination folder """
    def selectDownloadFolder(self):
        folder = filedialog.askdirectory(initialdir=self.downloadPath or os.path.expanduser("~"))
        # askdirectory returns "" when the dialog is cancelled; keep the current folder then
        # instead of clearing it (and the saved one)
        if not folder:
            return
        self.downloadPath = folder
        self.folderInput.configure(text=self.downloadPath)
        log.info("Download folder: %s", self.downloadPath)
        self.saveSettings()


    """ Shows restored settings in widgets that only exist after setupUI """
    def applySettingsToUI(self):
        if self.downloadPath:
            self.folderInput.configure(text=self.downloadPath)
        self.updateQualityVisibility(self.audioFormatVar.get())


    """ Persists the current folder/format/quality """
    def saveSettings(self):
        self.settings.last_folder = self.downloadPath
        self.settings.audio_format = self.audioFormatVar.get()
        self.settings.audio_quality = self.audioQualityVar.get()
        settings.save_settings(self.settings)


    """ Hides the quality dropdown for lossless/uncompressed formats where bitrate is meaningless """
    def updateQualityVisibility(self, value):
        if value in ytdl.LOSSLESS_FORMATS:
            self.qualityLabel.grid_remove()
            self.qualityMenu.grid_remove()
        else:
            self.qualityLabel.grid()
            self.qualityMenu.grid()


    def onFormatChange(self, value):
        self.updateQualityVisibility(value)
        self.saveSettings()


    """ Opens the log folder in Explorer, so a user can attach mp3vault.log to a bug report """
    def openLogFolder(self):
        try:
            os.makedirs(logs.log_dir(), exist_ok=True)
            os.startfile(logs.log_dir())
        except (OSError, AttributeError) as e:  # AttributeError: os.startfile is Windows-only
            messagebox.showinfo("Logs", f"Log folder: {logs.log_dir()}\n\n({e})")


    """ Checks PyPI for a newer yt-dlp release — notify only, never auto-installs. Runs on a
    background thread at startup; any failure (offline, PyPI down, unexpected response shape) is
    swallowed silently so a flaky network never disrupts opening the app. """
    def checkYtDlpUpdate(self):
        try:
            latestVersion = updates.newer_ytdlp_version()
            if latestVersion:
                self.ui(self.showUpdateNotice, latestVersion)
        except Exception as e:
            log.info("yt-dlp update check skipped: %s", e)


    """ Lights up the (always-present, normally blank/disabled) notice button in optionsRow """
    def showUpdateNotice(self, latestVersion):
        self.updateNoticeButton.configure(text=f"yt-dlp {latestVersion} available", state="normal", fg_color="#191818")


    """ Runs the actual update when the user clicks the notice — packaged .exe builds have no pip
    to call, so those just get an informational message instead of an update attempt. """
    def onUpdateNoticeClick(self):
        if updates.is_frozen():
            messagebox.showinfo("Update yt-dlp", "This is a packaged .exe — it can't run pip from inside itself. Rebuild the .exe with a newer yt-dlp installed, or check the yt-dlp GitHub releases page.")
            return

        self.updateNoticeButton.configure(state="disabled", text="Updating...")
        threading.Thread(target=self._runYtDlpUpdate, daemon=True).start()


    def _runYtDlpUpdate(self):
        message = updates.update_ytdlp()
        self.ui(lambda: messagebox.showinfo("Update yt-dlp", message))
        self.ui(lambda: self.updateNoticeButton.configure(state="disabled", text=""))


    """ Start a new thread to fetch video information when a URL is provided. Each lookup gets a
    generation number: if the user pastes another URL before this one answers, the late (stale)
    answer is discarded instead of overwriting the newer one. """
    def threadingButton(self, url: str):
        if url:
            self.infoGeneration += 1
            self.displayMessage("Loading... Please wait")
            threading.Thread(target=self.fetchVideoInfo, args=(url, self.infoGeneration), daemon=True).start()


    """ alidate the provided URL and enable or disable the download button accordingly """
    def validateURL(self):
        # If there is an existing timer, cancel it
        if hasattr(self, "url_delay") and self.url_delay:
            self.root.after_cancel(self.url_delay)

        # Set a new 500ms delay before executing the validation
        self.url_delay = self.root.after(500, self.processURL)
    
    
    """ Process the URL, determine its type (video or playlist), and update the UI """
    def processURL(self):
        url = self.urlInput.get().strip()
        
        if not url:
            self.infoGeneration += 1
            self.isPlaylist = None
            self.downloadBtn.configure(state="disabled")
            self.resetToDefault(isEmpty=True) 
            return  
            
        video_match = naming.YOUTUBE_VIDEO_URL_RE.match(url)
        if video_match:
            self.isPlaylist = False

            # Extract the video ID and validate its length
            video_id = video_match.group("id")
            if len(video_id) < 11:
                self.displayMessage("The YouTube video ID is incomplete or truncated.")
                return

            self.downloadBtn.configure(state="normal")
            self.threadingButton(url)

        elif naming.YOUTUBE_PLAYLIST_URL_RE.match(url):
            self.isPlaylist = True
            self.downloadBtn.configure(state="normal")
            self.threadingButton(url)
        else:
            self.infoGeneration += 1
            self.isPlaylist = None
            self.downloadBtn.configure(state="disabled")
            self.resetToDefault(isEmpty=False)


    """ Look-up URL for what the user pasted: a playlist link as is, but a video link opened from a
    playlist ("watch?v=X&list=Y", "youtu.be/X?list=Y") means only that video (see video_only_url) """
    def lookupUrl(self, url: str):
        if naming.YOUTUBE_PLAYLIST_URL_RE.match(url):
            return url
        return naming.video_only_url(url)


    """ Extract video information in a background thread """
    def fetchVideoInfo(self, url: str, generation: int):
        try:
            info_video = downloader.fetch_info(self.lookupUrl(url))
            self.ui(self.getInfoVideo, generation, url, info_video)

        except errors.MP3VaultError as e:
            log.warning("Video info failed for %s: %s", url, e.detail)
            self.ui(self.showInfoError, generation, e.user_message)

        except Exception as e:
            log.exception("Unexpected error fetching info for %s", url)
            self.ui(self.showInfoError, generation, f"Unexpected error: {str(e)}")


    def showInfoError(self, generation: int, message: str):
        if generation == self.infoGeneration:
            self.displayMessage(message)


    """ Clears the URL input field and resets UI elements """
    def cleanURL(self):
        if self.urlValue.get() != "":
            self.infoGeneration += 1  # a lookup still in flight must not repaint the cleared view
            self.urlValue.set("");
            self.downloadBtn.configure(state="disabled")
            self.root.geometry("750x280")
            self.clearVideoInfo()
            self.noURL()


    """ Current folder/format/quality, snapshotted for a download about to start """
    def currentOptions(self):
        return DownloadOptions(self.downloadPath, self.audioFormatVar.get(), self.audioQualityVar.get())


    """ Determines whether to download a single video or a playlist. Everything the worker needs
    is read HERE, on the main thread: Tk variables and widgets must not be touched from a worker
    thread, and a snapshot also keeps mid-download UI edits from affecting a running download. """
    def conditionalDownload(self):
        if self.isPlaylist is None:
            return

        if not self.downloadPath:
            messagebox.showwarning("Warning", "Please select a download folder first.")
            return

        # Prevents a double-click from starting two overlapping download threads on the same file
        if getattr(self, "isDownloading", False):
            return

        opts = self.currentOptions()
        url = self.urlInput.get()
        title = self.titleAudioVar.get()
        uploader = self.artistAudioVar.get()
        album = self.albumAudioVar.get()

        if self.isPlaylist:
            selected = self.videoView.selected_videos() if isinstance(self.videoView, PlaylistView) else []
            if not selected:
                messagebox.showwarning("Warning", "Please select at least one video to download.")
                return
            target, args = self.downloadPlaylist, (url, selected, uploader, album, opts)
        else:
            _, predictedName = naming.build_clean_title_and_filename(uploader, title, opts.audio_format)
            if os.path.exists(os.path.join(os.path.normpath(opts.folder), predictedName)):
                if not messagebox.askyesno("Already downloaded", f'"{predictedName}" already exists in that folder. Download again and overwrite it?'):
                    return
            target, args = self.downloadAudio, (self.lookupUrl(url), title, uploader, album, opts)

        self.isDownloading = True
        self.cancelRequested.clear()
        threading.Thread(target=target, args=args, daemon=True).start()


    """ Handles video information retrieval and processes accordingly (main thread) """
    def getInfoVideo(self, generation: int, url: str, info_video):
        if generation != self.infoGeneration:
            log.info("Discarding stale video info for %s", url)
            return

        self.videoUrl = url
        if "entries" in info_video:
            self.handlePlaylistInfo(info_video)
        else:
            self.handleSingleVideoInfo(info_video)


    """ Extract and store playlist metadata such as title, artist, and videos """
    def handlePlaylistInfo(self, info_video: str):
        self.playlistTitle  = info_video.get('title')
        self.playlistAlbum  = info_video.get('album', self.playlistTitle)
        self.playlistChannel = (
            info_video.get("channel")
            or (info_video["entries"][0].get("channel") if info_video.get("entries") else "")
        )
        self.playlistArtist = info_video.get('artist', self.playlistChannel)
        self.albumArtistVideo = info_video.get('uploader', '')
        
         # Extract the first available thumbnail URL, if present
        self.playlist_thumbnail  = (
            info_video['thumbnails'][0]['url']
            if info_video.get('thumbnails') and len(info_video['thumbnails']) > 0
            else None
        )
        
        # Each video keeps its REAL playlist position (see extract_playlist_videos), so a checkbox
        # still points at the right song when a deleted/private video sits before it.
        self.playlist_videos = ytdl.extract_playlist_videos(info_video.get("entries", []))

        self.updatePlaylistInfo(self.playlist_thumbnail)  
    
    
    """ Handles processing of a single video """    
    def handleSingleVideoInfo(self, info_video: str):                                        
        self.title_video = (info_video.get('title') or '').strip()
        self.album_video = info_video.get('album', '')
        self.channel_video = info_video.get('channel', '')
        self.artist_video = info_video.get('artist', self.channel_video)
        self.album_thumbnail = info_video.get('thumbnail') 
        self.updateVideoInfo(self.album_thumbnail)
        
    
    """ Opens the popup to edit title/artist/album (one at a time) """
    def editInfoPopUp(self):
        if self.editDialog and self.editDialog.exists():
            self.editDialog.lift()
            return
        self.editDialog = EditInfoDialog(
            self.root, self.regularFont,
            self.titleAudioVar.get(), self.artistAudioVar.get(), self.albumAudioVar.get(),
            on_confirm=self.updateEditInfoAudio,
        )


    """ Runs fn(*args) on the Tk main thread. Worker threads must never touch widgets directly;
    instead they post here, and _drainUiQueue (the ONLY place these calls run) executes them in
    order every UI_POLL_MS. FIFO order matters: e.g. show_progress_frame always runs before the
    first progress update posted after it. """
    def ui(self, fn, *args):
        self.uiQueue.put((fn, args))


    UI_POLL_MS = 50

    def _drainUiQueue(self):
        try:
            while True:
                fn, args = self.uiQueue.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    log.exception("Error in UI update %s", getattr(fn, "__name__", fn))
        except queue.Empty:
            pass
        self.root.after(self.UI_POLL_MS, self._drainUiQueue)


    """ New per-download session (cancel flag + files this run writes, see DownloadSession). Its
    progress updates are posted through self.ui because the hook runs on the worker thread.
    `title` replaces the video's own title in the progress text (the user's edited title). """
    def newDownloadSession(self, title=None):
        return ytdl.DownloadSession(
            self.cancelRequested,
            on_progress=lambda progress: self.ui(self._updateProgressUI, progress),
            title=title,
        )


    def _updateProgressUI(self, progress: Progress):
        if self.progressView:
            self.progressView.update(progress)


    def setProgressText(self, text: str):
        if self.progressView:
            self.progressView.set_text(text)


    """ Worker: downloads one video (see downloader.download_single) """
    def downloadAudio(self, url: str, title: str, uploader: str, album: str, opts: DownloadOptions):
        try:
            self.ui(self.show_progress_frame)
            result = downloader.download_single(url, title, uploader, album, opts, self.newDownloadSession(title))
            self.ui(self.showTrackResult, result)
        finally:
            self.isDownloading = False


    """ Main thread: reports a single download. Cancel/error messages stay on screen (the URL is
    kept so the user can retry); only a success clears the view. """
    def showTrackResult(self, result: TrackResult):
        if result.ok:
            message = f"{result.filename} - Downloaded Successfully"
            if result.tag_error:
                message += f"\n\nTags could not be written: {result.tag_error}"
            messagebox.showinfo("Download Success", message)
            self.hide_progress_frame()
        elif result.cancelled:
            self.displayMessage("Download cancelled.")
        else:
            self.displayMessage(result.error)


    """ Worker: downloads the selected playlist videos (see downloader.download_playlist) """
    def downloadPlaylist(self, url: str, videos: list, uploader: str, album: str, opts: DownloadOptions):
        try:
            self.ui(self.show_progress_frame)
            result = downloader.download_playlist(url, videos, uploader, album, opts, self.newDownloadSession())
            self.ui(self.showPlaylistResult, result)
        finally:
            self.isDownloading = False


    """ Main thread: reports a playlist download with counts instead of a single filename — a
    playlist has many files, and every selected video may legitimately fail or be skipped. """
    def showPlaylistResult(self, result: BatchResult):
        if result.cancelled:
            self.displayMessage("Download cancelled.")
            return
        if result.error:
            self.displayMessage(result.error)
            return

        if not result.attempted:
            messagebox.showinfo("Nothing to download", f"All {result.skipped_existing} selected song(s) already exist in that folder.")
        elif result.downloaded:
            message = f"{result.downloaded} song(s) downloaded successfully"
            if result.skipped_existing:
                message += f" ({result.skipped_existing} already existed, skipped)"
            if result.tag_errors:
                message += f"\n\n{len(result.tag_errors)} song(s) could not be tagged (see Logs)."
            messagebox.showinfo("Download Success", message)
        else:
            messagebox.showwarning("Warning", "No videos were downloaded.")
        self.hide_progress_frame()


    """ Opens the popup for pasting multiple video URLs (kept hidden until "+ Agregar" is clicked) """
    def toggleQueueWindow(self):
        if self.queueDialog and self.queueDialog.exists():
            self.queueDialog.lift()
            return
        self.queueDialog = QueueDialog(self.root, self.regularFont, on_submit=self.startQueueDownload)


    """ Validates the pasted URLs and kicks off the sequential background download """
    def startQueueDownload(self, text: str):
        if not self.downloadPath:
            messagebox.showwarning("Warning", "Please select a download folder first.")
            return

        if getattr(self, "isDownloading", False):
            messagebox.showwarning("Warning", "A download is already in progress.")
            return

        # Only single-video URLs are supported in the queue — a playlist URL here would need its
        # own per-video checkbox selection, which contradicts keeping this flow simple/headless.
        urls = []
        invalidCount = 0
        playlistCount = 0
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            elif naming.YOUTUBE_VIDEO_URL_RE.match(line):
                urls.append(line)
            elif naming.YOUTUBE_PLAYLIST_URL_RE.match(line):
                playlistCount += 1
            else:
                invalidCount += 1

        if not urls:
            messagebox.showwarning("Warning", "No valid single-video URLs found.")
            return

        notes = []
        if invalidCount:
            notes.append(f"{invalidCount} invalid line(s) ignored")
        if playlistCount:
            notes.append(f"{playlistCount} playlist URL(s) ignored (not supported in the queue)")
        if notes:
            messagebox.showinfo("Queue", f"Queuing {len(urls)} video(s). " + "; ".join(notes) + ".")

        self.queueDialog.close()
        self.isDownloading = True
        self.cancelRequested.clear()
        threading.Thread(target=self._runQueueWorker, args=(urls, self.currentOptions()), daemon=True).start()


    """ Worker: downloads each queued URL sequentially (see downloader.download_queue) """
    def _runQueueWorker(self, urls: list, opts: DownloadOptions):
        try:
            self.ui(self.show_progress_frame)
            result = downloader.download_queue(
                urls, opts, self.newDownloadSession,
                on_item=lambda i, total: self.ui(self.setProgressText, f"Descargando {i}/{total}..."),
            )
            self.ui(self.showQueueResult, result)
        finally:
            self.isDownloading = False


    def showQueueResult(self, result: BatchResult):
        summary = "Cancelled. " if result.cancelled else ""
        summary += f"{result.downloaded} downloaded"
        if result.skipped_existing:
            summary += f", {result.skipped_existing} already existed (skipped)"
        if result.failed:
            summary += f", {result.failed} failed"
        if result.tag_errors:
            summary += f", {len(result.tag_errors)} without tags"
        messagebox.showinfo("Queue finished", summary)
        self.hide_progress_frame()


    """ Updates the editable audio information fields with new values """
    def updateEditInfoAudio(self, title_video: str, artist_video: str, album_video: str):
        self.titleAudioVar.set(title_video)
        self.artistAudioVar.set(artist_video)
        self.albumAudioVar.set(album_video)
    
         
    """ Shows the single-video view (thumbnail, title/artist/album, Edit) """
    def updateVideoInfo(self, album_thumbnail):
        self.clearVideoInfo()
        self.updateEditInfoAudio(self.title_video, self.artist_video, self.album_video)
        self.root.geometry("750x350")
        self.videoView = SingleVideoView(
            self.videoInfoFrame, (self.titleAudioVar, self.artistAudioVar, self.albumAudioVar), self.fonts,
            self.editImg, self.editInfoPopUp, album_thumbnail, self.ui,
        )


    """ Shows the playlist view (header + one checkbox per video) """
    def updatePlaylistInfo(self, album_thumbnail: str):
        self.clearVideoInfo()
        self.updateEditInfoAudio(self.playlistTitle, self.playlistArtist, self.playlistAlbum)
        self.root.geometry("750x700")
        self.videoView = PlaylistView(
            self.videoInfoFrame, (self.titleAudioVar, self.artistAudioVar, self.albumAudioVar), self.fonts,
            self.editImg, self.editInfoPopUp, album_thumbnail, self.ui, self.playlist_videos,
        )


    """ Clears all video information by removing existing widgets from the frame """
    def clearVideoInfo(self):
        self.videoView = None
        for widget in self.videoInfoFrame.winfo_children():
            widget.destroy()
            
    
    """ Displays a message inside the video info frame """        
    def displayMessage(self, message: str):
        
        # Clears any existing content inside the video info frame
        if hasattr(self, "videoInfoFrame") and self.videoInfoFrame.winfo_exists():
            for widget in self.videoInfoFrame.winfo_children():
                try:
                    widget.destroy()
                except Exception as e:
                    log.warning("Error destroying widget: %s", e)
        
        self.customText = ctk.CTkLabel(self.videoInfoFrame, text=message, text_color="#FFFFFF", font=self.titleFont, wraplength=450);
        self.customText.grid(row=0, column=1, sticky='nsew')
                            
                            
    
    """ Handles the case when there is no URL or the URL is invalid """        
    def noURL(self, isEmpty=True):
        for widget in self.videoInfoFrame.winfo_children():
            widget.destroy()
            
        self.noUrlFrame = ctk.CTkFrame(self.videoInfoFrame, fg_color="transparent");
        self.noUrlFrame.grid(row=1, column=1, sticky='nsew' , padx=self.padding, pady=self.padding)
        self.noUrlFrame.columnconfigure(1, weight=1)
        self.noUrlFrame.rowconfigure(1, weight=1) 
        
         # Texto principal
        main_text = "Your queue is empty" if isEmpty else "Invalid URL"
        self.noUrlText = ctk.CTkLabel(self.noUrlFrame, text=main_text)
        self.noUrlText.grid(row=0, column=1, sticky='nsew')
        self.noUrlText.configure(text_color="#FFFFFF", font=self.titleFont)
        
        # Texto secundario
        sub_text = "Type or paste a link above" if isEmpty else "Please enter a valid YouTube link"
        self.noUrlSubText = ctk.CTkLabel(self.noUrlFrame, text=sub_text)
        self.noUrlSubText.grid(row=1, column=1, sticky='nsew')
        self.noUrlSubText.configure(text_color="#FFFFFF", font=self.regularFont)

        
    """ Shows the progress view when the download starts """
    def show_progress_frame(self):
        self.clearVideoInfo()
        # Taller than the other 280px views — videoInfoFrame splits its height 50/50 between two
        # weighted rows (this one and the empty-queue row), and the extra Cancel button row no
        # longer fits in a plain 280px window without overlapping optionsRow/videoConfigFrame below
        # (measured: 350 is the bare minimum, 380 leaves comfortable margin).
        self.root.geometry("750x380")
        self.progressView = ProgressView(self.videoInfoFrame, self.regularFont, on_cancel=self.requestCancel)


    """ Signals the active download thread to stop (checked in DownloadSession.hook) """
    def requestCancel(self):
        self.cancelRequested.set()
        if self.progressView:
            self.progressView.set_cancelling()


    """ Hides the progress view after the download is completed """
    def hide_progress_frame(self):
        if self.progressView:
            self.progressView.destroy()
            self.progressView = None
            self.cleanURL()


    """ Resets the UI to default view after the download or when there's no URL """        
    def resetToDefault(self, isEmpty=False):
        self.noURL(isEmpty=isEmpty)
        self.root.geometry("750x280")
        

    """ Initializes the main UI components for the application """
    def setupUI(self):
        self.urlFrame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.urlFrame.grid(row=0, column=0, sticky='nsew', padx=self.padding, pady=(self.padding, 0))
        self.urlFrame.columnconfigure(1, weight=1) 
        
        self.videoInfoFrame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.videoInfoFrame.grid(row=1, column=0, sticky='nsew' , padx=self.padding, pady=self.padding)
        self.videoInfoFrame.columnconfigure(1, weight=1)
        self.videoInfoFrame.rowconfigure(0, weight=1)
        self.videoInfoFrame.rowconfigure(1, weight=1)

        # Row 2 sits between the video info and the download button row, created once here (unlike
        # videoInfoFrame's contents, this never gets destroyed/rebuilt per view) — output format and
        # quality live here rather than being crammed into videoConfigFrame, which is already close
        # to its 750px width budget with the folder picker + Download button.
        self.optionsRow = ctk.CTkFrame(self.root, fg_color="transparent")
        self.optionsRow.grid(row=2, column=0, sticky='nsew', padx=self.padding, pady=(0, self.padding))

        self.formatLabel = ctk.CTkLabel(self.optionsRow, text="Format:")
        self.formatLabel.configure(text_color="#FFFFFF", font=self.regularFont)
        self.formatLabel.grid(row=0, column=0, sticky='w', padx=(0, 10))

        self.formatMenu = ctk.CTkOptionMenu(self.optionsRow, values=ytdl.AUDIO_FORMATS, variable=self.audioFormatVar, command=self.onFormatChange)
        self.formatMenu.configure(font=self.regularFont, fg_color="#191818", button_color="#191818", button_hover_color="#FF4C58", width=90, height=30)
        self.formatMenu.grid(row=0, column=1, sticky='w', padx=(0, 20))

        self.qualityLabel = ctk.CTkLabel(self.optionsRow, text="Quality:")
        self.qualityLabel.configure(text_color="#FFFFFF", font=self.regularFont)
        self.qualityLabel.grid(row=0, column=2, sticky='w', padx=(0, 10))

        self.qualityMenu = ctk.CTkOptionMenu(self.optionsRow, values=ytdl.AUDIO_QUALITIES, variable=self.audioQualityVar, command=lambda _: self.saveSettings())
        self.qualityMenu.configure(font=self.regularFont, fg_color="#191818", button_color="#191818", button_hover_color="#FF4C58", width=90, height=30)
        self.qualityMenu.grid(row=0, column=3, sticky='w')

        # Always present (rather than grid()/grid_remove()'d in only when relevant) so its
        # appearance never changes this row's height or triggers a geometry recalculation — it's
        # just blank/disabled until checkYtDlpUpdate finds a newer release.
        self.optionsRow.columnconfigure(4, weight=1)
        self.updateNoticeButton = ctk.CTkButton(self.optionsRow, text="", command=self.onUpdateNoticeClick, state="disabled")
        self.updateNoticeButton.configure(fg_color="transparent", font=self.regularFont, height=30, hover_color="#FF4C58", text_color="#FFFFFF")
        self.updateNoticeButton.grid(row=0, column=4, sticky='e')

        self.logsButton = ctk.CTkButton(self.optionsRow, text="Logs", command=self.openLogFolder)
        self.logsButton.configure(fg_color="#191818", font=self.regularFont, height=30, width=60, hover_color="#FF4C58")
        self.logsButton.grid(row=0, column=5, sticky='e', padx=(10, 0))

        self.videoConfigFrame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.videoConfigFrame.grid(row=3, sticky='nsew', padx=self.padding, pady=(0, self.padding))
        self.videoConfigFrame.rowconfigure(0, weight=1)
        
        self.videoConfigFrame.columnconfigure(3, weight=1) 
        
        self.selectFolderFrame = ctk.CTkFrame(self.videoConfigFrame, fg_color="transparent")
        self.selectFolderFrame.grid(row=0, column=0, sticky='n')
        self.selectFolderFrame.configure(height=30)


        ### Label and entry for the video URL ###
        self.headLabel = ctk.CTkLabel(self.urlFrame, text="URL:");
        self.headLabel.grid(row=0, column=0, sticky='w', padx=(0, 10))
        self.headLabel.configure(text_color="#FFFFFF", font=self.regularFont, pady=1);

        self.urlInput = ctk.CTkEntry(self.urlFrame, textvariable=self.urlValue )
        self.urlInput.grid(row=0, column=1, pady=10, sticky='nsew')
        self.urlInput.configure(font=self.regularFont, text_color="#000000", fg_color="#FFFFFF", width=300, height=30)
        self.urlInput.bind("<KeyRelease>", lambda _: self.validateURL())

        self.deleteButton = ctk.CTkButton(self.urlFrame, text="X", command=self.cleanURL);
        self.deleteButton.grid(row=0, column=1, sticky='e')
        self.deleteButton.configure(fg_color="#191818", font=self.regularFont, height=30, width=40, hover_color="#FF4C58");

        # Opens the (hidden-by-default) multi-URL queue popup — kept out of the main window
        # entirely rather than an inline expand/collapse, since this window is a fixed 750px wide
        # and doesn't have slack to spare.
        self.queueButton = ctk.CTkButton(self.urlFrame, text="+ Agregar", command=self.toggleQueueWindow)
        self.queueButton.grid(row=0, column=2, sticky='e', padx=(10, 0))
        self.queueButton.configure(fg_color="#191818", font=self.regularFont, height=30, width=100, hover_color="#FF4C58");


        ### Label and entry for the folder destination ###
        self.folderLabel = ctk.CTkLabel(self.selectFolderFrame, text="Save:");
        self.folderLabel.configure(text_color="#FFFFFF", font=self.regularFont, pady=1);
        self.folderLabel.grid(row=0, column=0, sticky='n', padx=(0, 10))

        self.folderInput = ctk.CTkLabel(self.selectFolderFrame, text="Select Download Folder")
        self.folderInput.configure(font=self.regularFont, text_color="#000000", fg_color="#FFFFFF", width=260, height=30, corner_radius=5, justify="left")
        self.folderInput.grid(row=0, column=1, sticky='n')

        # Button to select the download destination folder
        self.folderButton = ctk.CTkButton(self.selectFolderFrame, text="", command=self.selectDownloadFolder, image=ctk.CTkImage(dark_image=self.folderImg, light_image=self.folderImg));
        self.folderButton.configure(fg_color="#191818", font=self.regularFont, height=33, width=80, hover_color="#FF4C58");
        self.folderButton.grid(row=0, column=2, sticky='n')
      
        self.downloadBtn = ctk.CTkButton(self.videoConfigFrame, text="Download", command=self.conditionalDownload, state="disabled")
        self.downloadBtn.configure(fg_color="transparent", border_width=2, border_color="#FF4C58", hover_color="#FF4C58", height=35, width=170, font=self.regularFont)
        self.downloadBtn.grid(row=0, column=3, sticky='ne')
      

if __name__ == "__main__":
    logFile = logs.setup_logging()
    log.info("MP3Vault %s starting (yt-dlp %s) - https://github.com/caladavid/MP3Vault", APP_VERSION, yt_dlp.version.__version__)
    log.info("Log file: %s", logFile)
    ffmpegFolder = ffmpeg.find_ffmpeg()
    if ffmpegFolder:
        log.info("Using ffmpeg from %s", ffmpegFolder)
    else:
        log.warning("ffmpeg not found (bundle or absolute PATH folder); downloads will be refused")
    root = ctk.CTk();
    app = MP3Vault(root);
    root.mainloop(); 
    