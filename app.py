import logging
import queue
import sys
import os
import threading
import customtkinter as ctk
from customtkinter import *
from PIL import Image
from tkinter import messagebox

import yt_dlp

from core import downloader, logs, naming, settings, thumbnail, updates, ytdl
from core.models import BatchResult, DownloadOptions, Progress, TrackResult

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
        
        self.padding = 20
        
        self.regularFont = ctk.CTkFont(family="Lato", size=14);
        self.titleFont = ctk.CTkFont(family="Lato", size=16, weight="bold");
        self.folderImg = Image.open(resourcePath("folder.png"));
        self.editImg = Image.open(resourcePath("editar.png"));
        self.urlValue = StringVar();
        self.editInfoWindow = None
        
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
        
        # Inicializar la Progress Bar (No se muestra hasta que se usa)
        self.progressBar = None
        self.loadingText = None

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


    # Window width is fixed at 750 and never resizes (root.resizable(0, 0)), so the space actually
    # left for the title after the 200px thumbnail, fixed paddings, and the Edit button is a
    # constant too — measured directly from the real widget tree (see conversation/commit notes).
    # CTkLabel needs wraplength AND width set to the same value: wraplength alone still leaves the
    # widget's own canvas at its small default size, and grid can silently shrink a too-large width
    # to fit its column — either mismatch clips the wrapped text instead of showing it in full.
    TITLE_WRAPLENGTH_SINGLE = 340   # single-video view: Edit button shares the same inner frame
    TITLE_WRAPLENGTH_PLAYLIST = 385  # playlist view: Edit button lives in a separate outer column


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

        # Handle specific download errors from yt_dlp
        except yt_dlp.utils.DownloadError as e:
            errorMsg = str(e)
            log.warning("Video info failed for %s: %s", url, errorMsg)
            self.ui(self.showInfoError, generation, self.infoErrorMessage(errorMsg))

        except Exception as e:
            log.exception("Unexpected error fetching info for %s", url)
            self.ui(self.showInfoError, generation, f"Unexpected error: {str(e)}")


    """ User-facing text for a yt-dlp lookup error """
    @staticmethod
    def infoErrorMessage(errorMsg: str):
        if "HTTP Error 400" in errorMsg:
            return "Bad request (Error 400). Please check the URL."
        elif "HTTP Error 404" in errorMsg:
            return "Video not found (Error 404)."
        elif "HTTP Error 403" in errorMsg:
            return "Access denied (Error 403)."
        elif "HTTP Error 500" in errorMsg:
            return "Internal server error (Error 500)."
        elif "youtube:truncated_id" in errorMsg:
            return "The YouTube video ID is incomplete or truncated."
        elif "Video unavailable" in errorMsg:
            return "The YouTube video ID is unavailable."
        return f"Error retrieving video information: {errorMsg}"


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
            selected = [
                video for video, state in zip(getattr(self, "playlist_videos", []), getattr(self, "checkboxStates", []))
                if state.get()
            ]
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
        
    
    """ Closes the pop-up window for editing playlist information """
    def closeEditInfoPopUp(self):
        # Write the popup's own vars back into the real ones, then let them (and their entries'
        # variable traces) get garbage-collected with the window instead of leaking into it.
        self.titleAudioVar.set(self.titleEditUrlEntry.get())
        self.artistAudioVar.set(self.artistEditUrlEntry.get())
        self.albumAudioVar.set(self.albumEditUrlEntry.get())
        self.editInfoWindow.destroy()


    """ Opens a pop-up window to edit the playlist information """
    def editInfoPopUp(self):
        if self.editInfoWindow and self.editInfoWindow.winfo_exists():
            self.editInfoWindow.lift()
            return

        self.editInfoWindow = ctk.CTkToplevel(self.root)
        self.editInfoWindow.geometry("410x250")
        self.editInfoWindow.title("Edit audio details")

        # Separate StringVars scoped to this popup, seeded from the current values — NOT the same
        # titleAudioVar/artistAudioVar/albumAudioVar the main window's labels use. CTkEntry never
        # removes its internal trace on its textvariable when destroyed, so binding these entries
        # directly to the long-lived vars left a dangling trace on every popup open/close that later
        # crashed with `_tkinter.TclError: invalid command name` the next time a new video loaded
        # and the shared var's .set() fired the stale callback.
        self.titleEditUrlEntry = ctk.StringVar(value=self.titleAudioVar.get())
        self.artistEditUrlEntry = ctk.StringVar(value=self.artistAudioVar.get())
        self.albumEditUrlEntry = ctk.StringVar(value=self.albumAudioVar.get())

        self.editInfoUrlFrame = ctk.CTkFrame(self.editInfoWindow, fg_color="transparent")
        self.editInfoUrlFrame.grid(row=0, column=0, sticky='nsew', padx=self.padding, pady=self.padding)
        self.editInfoUrlFrame.columnconfigure((0, 3), weight=1) 
        self.videoInfoFrame.rowconfigure((0, 3), weight=1) 
        
        ### Label and entry for the video URL ###
        self.headLabel = ctk.CTkLabel(self.editInfoUrlFrame, text="Edit details");
        self.headLabel.grid(row=0, column=1)
        self.headLabel.configure(text_color="#FFFFFF", font=self.regularFont, padx=1, pady=1); 
        
        ### Label and entry for the folder destination ###
        self.titleEditLabel = ctk.CTkLabel(self.editInfoUrlFrame, text="Title");
        self.titleEditLabel.configure(text_color="#FFFFFF", font=self.regularFont, pady=1);
        self.titleEditLabel.grid(row=1, column=0, sticky='nsew', padx=(0, 10))

        self.titleEditUrlInput = ctk.CTkEntry(self.editInfoUrlFrame, textvariable=self.titleEditUrlEntry)
        self.titleEditUrlInput.grid(row=1, column=1, pady=10, sticky='nsew')
        self.titleEditUrlInput.configure(font=self.regularFont, text_color="#000000", fg_color="#FFFFFF", width=300, height=30)
        
        
        ### Label and entry for the folder destination ###
        self.artistEditLabel = ctk.CTkLabel(self.editInfoUrlFrame, text="Artist");
        self.artistEditLabel.configure(text_color="#FFFFFF", font=self.regularFont, pady=1);
        self.artistEditLabel.grid(row=2, column=0, sticky='nsew', padx=(0, 10))

        self.artistEditUrlInput = ctk.CTkEntry(self.editInfoUrlFrame, textvariable=self.artistEditUrlEntry)
        self.artistEditUrlInput.grid(row=2, column=1, pady=10, sticky='nsew')
        self.artistEditUrlInput.configure(font=self.regularFont, text_color="#000000", fg_color="#FFFFFF", width=300, height=30)
        
        
        ### Label and entry for the folder destination ###
        self.albumEditLabel = ctk.CTkLabel(self.editInfoUrlFrame, text="Album");
        self.albumEditLabel.configure(text_color="#FFFFFF", font=self.regularFont, pady=1);
        self.albumEditLabel.grid(row=3, column=0, sticky='nsew', padx=(0, 10))

        self.albumEditUrlInput = ctk.CTkEntry(self.editInfoUrlFrame, textvariable=self.albumEditUrlEntry)
        self.albumEditUrlInput.grid(row=3, column=1, pady=10, sticky='nsew')
        self.albumEditUrlInput.configure(font=self.regularFont, text_color="#000000", fg_color="#FFFFFF", width=300, height=30)
        
        # Button to select the download destination folder
        self.editInfoButton = ctk.CTkButton(self.editInfoUrlFrame, text="Confirm", command=self.closeEditInfoPopUp);
        self.editInfoButton.grid(row=4, column=1, pady=2)
        self.editInfoButton.configure(fg_color="#191818", font=self.regularFont, height=35, width=80, hover_color="#FF4C58");


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


    """ Progress updates can arrive after the progress frame was destroyed (e.g. a new URL loaded
    meanwhile); touching its widgets then raises TclError (verified). """
    def progressFrameAlive(self):
        return hasattr(self, "progressFrame") and self.progressFrame.winfo_exists()


    def _updateProgressUI(self, progress: Progress):
        if not self.progressFrameAlive():
            return

        title = progress.title
        if progress.playlist_index is not None:
            title = f"{title} ({progress.playlist_index}/{progress.playlist_count or '?'})"

        if progress.status == 'downloading':
            self.progressVar.set(progress.fraction)
            self.progressLabel.configure(text=f"Descargando: {title}")
            self.speedLabel.configure(text=f"Velocidad: {progress.speed} - ETA: {progress.eta}")

        elif progress.status == 'finished':
            self.progressVar.set(1)  # Set progress bar to 100%
            self.progressLabel.configure(text=f"Descarga completada: {title}")
            self.speedLabel.configure(text="¡Completado!")


    def setProgressText(self, text: str):
        if self.progressFrameAlive():
            self.progressLabel.configure(text=text)


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
            self.displayMessage(f"An error occurred: {result.error}")


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
            self.displayMessage(f"An error occurred: {result.error}")
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
        if getattr(self, "queueWindow", None) and self.queueWindow.winfo_exists():
            self.queueWindow.lift()
            return

        self.queueWindow = ctk.CTkToplevel(self.root)
        self.queueWindow.title("Add multiple URLs")
        self.queueWindow.geometry("420x300")

        self.queueLabel = ctk.CTkLabel(self.queueWindow, text="Paste one YouTube video URL per line:")
        self.queueLabel.configure(text_color="#FFFFFF", font=self.regularFont)
        self.queueLabel.grid(row=0, column=0, padx=20, pady=(20, 5), sticky='w')

        self.queueTextbox = ctk.CTkTextbox(self.queueWindow, width=380, height=180)
        self.queueTextbox.grid(row=1, column=0, padx=20, pady=5)

        self.queueDownloadButton = ctk.CTkButton(self.queueWindow, text="Download All", command=self.startQueueDownload)
        self.queueDownloadButton.configure(fg_color="#191818", font=self.regularFont, height=35, hover_color="#FF4C58")
        self.queueDownloadButton.grid(row=2, column=0, pady=(10, 20))


    """ Validates the pasted URLs and kicks off the sequential background download """
    def startQueueDownload(self):
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
        for line in self.queueTextbox.get("1.0", "end").splitlines():
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

        self.queueWindow.destroy()
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
    
         
    """ Gray box shown until the thumbnail arrives (or permanently, if there is none) """
    def createThumbnailPlaceholder(self, parent, thumbnailUrl):
        return ctk.CTkLabel(
            parent,
            text="Loading image..." if thumbnailUrl else "No image available",
            width=thumbnail.THUMBNAIL_SIZE[0],
            height=thumbnail.THUMBNAIL_SIZE[1],
            fg_color="gray",
            text_color="white",
            corner_radius=8,
            font=("Arial", 12)
        )


    """ Fetches the thumbnail off the Tk main thread so a slow host can't freeze the window, then
    hands the result back via root.after. The label may already be gone by then (user pasted a new
    URL meanwhile), so it is checked before being touched. """
    def loadThumbnailAsync(self, url: str, label):
        def worker():
            try:
                image_pil = thumbnail.fetch_thumbnail(url)
            except Exception as e:
                log.warning("Thumbnail failed for %s: %s", url, e)
                image_pil = None
            self.ui(applyResult, image_pil)

        def applyResult(image_pil):
            if not label.winfo_exists():
                return
            if image_pil is None:
                label.configure(text="No image available")
                return
            # Kept on self so Tk doesn't garbage-collect the image while it's displayed
            self.imageInsideVideoInfoFrame = ctk.CTkImage(light_image=image_pil, size=thumbnail.THUMBNAIL_SIZE)
            label.configure(image=self.imageInsideVideoInfoFrame, text="", fg_color="transparent")

        threading.Thread(target=worker, daemon=True).start()


    """ Updates the video information display, including thumbnail and text fields """
    def updateVideoInfo(self, album_thumbnail):
        self.clearVideoInfo()
        self.updateEditInfoAudio(self.title_video, self.artist_video, self.album_video)
        
        self.singleVideosFrame = ctk.CTkFrame(self.videoInfoFrame, fg_color="transparent")
        self.singleVideosFrame.grid(row=0, column=0, columnspan=2, rowspan=3, sticky='nsew', padx=self.padding, pady=self.padding)
        self.singleVideosFrame.grid_rowconfigure((0,3), weight=1)
        self.singleVideosFrame.grid_columnconfigure((1,3), weight=1)

        # Placeholder now, real thumbnail filled in by a background thread (see loadThumbnailAsync)
        self.imageLabelInsideVideoInfoFrame = self.createThumbnailPlaceholder(self.singleVideosFrame, album_thumbnail)
        if album_thumbnail:
            self.loadThumbnailAsync(album_thumbnail, self.imageLabelInsideVideoInfoFrame)

        self.root.geometry("750x350")
        self.imageLabelInsideVideoInfoFrame.grid(row=0, column=0, sticky='w', padx=(self.padding, 0), pady=self.padding)
        
        self.textInsideVideoInfoFrame = ctk.CTkFrame(self.singleVideosFrame, fg_color="transparent")
        self.textInsideVideoInfoFrame.grid(row=0, column=1, columnspan=3, padx=self.padding, pady=self.padding, sticky='ew')
        self.textInsideVideoInfoFrame.grid_columnconfigure(0, weight=1)  # Asegura que la última columna tenga espacio
        self.textInsideVideoInfoFrame.grid_columnconfigure(1, weight=1)  # Asegura que la última columna tenga espacio
        self.textInsideVideoInfoFrame.grid_rowconfigure((0, 2), weight=1)
        
        # Button to select the download destination folder
        self.editInfoButton = ctk.CTkButton(self.textInsideVideoInfoFrame, text="Edit", command=self.editInfoPopUp, image=CTkImage(dark_image=self.editImg, light_image=self.editImg));
        self.editInfoButton.configure(fg_color="#191818", font=self.regularFont, height=33, width=40, hover_color="#FF4C58");
        self.editInfoButton.grid(row=2, column=3, sticky='se')

        self.titleVideoInfo = ctk.CTkLabel(self.textInsideVideoInfoFrame, width=self.TITLE_WRAPLENGTH_SINGLE, wraplength=self.TITLE_WRAPLENGTH_SINGLE, anchor='w', justify='left', textvariable=self.titleAudioVar, font=self.titleFont )
        self.titleVideoInfo.grid(row=0, column=0, sticky='w')
        self.titleVideoInfo.columnconfigure(0, weight=1)

        self.artistVideoInfo = ctk.CTkLabel(self.textInsideVideoInfoFrame, textvariable=self.artistAudioVar, font=self.regularFont)
        self.artistVideoInfo.grid(row=1, column=0, sticky='w')
        
        self.albumVideoInfo = ctk.CTkLabel(self.textInsideVideoInfoFrame, textvariable=self.albumAudioVar, font=self.regularFont)
        self.albumVideoInfo.grid(row=2, column=0, sticky='w')

        
    def updatePlaylistInfo(self, album_thumbnail: str):
        self.clearVideoInfo()
        self.updateEditInfoAudio(self.playlistTitle, self.playlistArtist, self.playlistAlbum)

        self.videosFromPlaylistFrame = ctk.CTkFrame(self.videoInfoFrame, fg_color="transparent")
        self.videosFromPlaylistFrame.grid(row=0, column=0, columnspan=2, rowspan=3, sticky='nsew', padx=self.padding, pady=self.padding)
        self.videosFromPlaylistFrame.grid_rowconfigure((0,3), weight=1)
        self.videosFromPlaylistFrame.grid_columnconfigure((1,3), weight=1)
        
        # Placeholder now, real thumbnail filled in by a background thread (see loadThumbnailAsync)
        self.imageLabelInsideVideoInfoFrame = self.createThumbnailPlaceholder(self.videosFromPlaylistFrame, album_thumbnail)
        if album_thumbnail:
            self.loadThumbnailAsync(album_thumbnail, self.imageLabelInsideVideoInfoFrame)
        else:
            self.videosFromPlaylistFrame.grid_rowconfigure(0, weight=0)
            self.videosFromPlaylistFrame.grid_columnconfigure(0, weight=0) 
           
               
        self.root.geometry("750x700")
        self.imageLabelInsideVideoInfoFrame.grid(row=0, column=0, sticky='ew', padx=self.padding, pady=self.padding)

        self.textInsideVideoInfoFrame = ctk.CTkFrame(self.videosFromPlaylistFrame, fg_color="transparent")
        self.textInsideVideoInfoFrame.grid(row=0, column=1, columnspan=3, sticky='w', padx=self.padding, pady=self.padding)
        self.textInsideVideoInfoFrame.grid_columnconfigure(0, weight=1)
        self.textInsideVideoInfoFrame.grid_columnconfigure(1, weight=1)
        
        # Button to select the download destination folder
        self.editInfoButton = ctk.CTkButton(self.videosFromPlaylistFrame, text="Edit", command=self.editInfoPopUp, image=CTkImage(dark_image=self.editImg, light_image=self.editImg));
        self.editInfoButton.configure(fg_color="#191818", font=self.regularFont, height=33, width=40, hover_color="#FF4C58");
        self.editInfoButton.grid(row=0, column=3, sticky='ne')
        
        
        self.titleVideoInfo = ctk.CTkLabel(self.textInsideVideoInfoFrame, width=self.TITLE_WRAPLENGTH_PLAYLIST, wraplength=self.TITLE_WRAPLENGTH_PLAYLIST, anchor='w', justify='left', textvariable=self.titleAudioVar, font=self.titleFont)
        self.titleVideoInfo.grid(row=0, column=0, sticky='w')
        self.titleVideoInfo.columnconfigure(0, weight=1)

        self.artistVideoInfo = ctk.CTkLabel(self.textInsideVideoInfoFrame, textvariable=self.artistAudioVar, font=self.regularFont)
        self.artistVideoInfo.grid(row=1, column=0, sticky='w')
        
        
        self.albumVideoInfo = ctk.CTkLabel(self.textInsideVideoInfoFrame, textvariable=self.albumAudioVar, font=self.regularFont)
        self.albumVideoInfo.grid(row=2, column=0, sticky='w')
        
        self.videosListScrollable = ctk.CTkScrollableFrame(self.videosFromPlaylistFrame)
        self.videosListScrollable.grid(row=4, column=0, rowspan=2, columnspan=4, sticky='nsew', padx=self.padding, pady=self.padding)
        self.videosListScrollable.columnconfigure(1, weight=1)
        self.videosListScrollable.columnconfigure(2, weight=1)
        self.videosListScrollable.columnconfigure(3, weight=1)
        self.videosListScrollable.rowconfigure(0, weight=1)
        
        maxTextLength = 80
        
        separator = ctk.CTkFrame(self.videosFromPlaylistFrame, height=2, fg_color="gray")
        separator.grid(row=3, column=0, columnspan=4, sticky="new", pady=5)
        
        self.loadingLabel = ctk.CTkLabel(self.videosListScrollable, text="Loading...", font=self.regularFont)
        self.loadingLabel.grid(row=0, column=0, sticky="w", padx=self.padding, pady=self.padding)
        
        
        def loadPlaylistVideos():
            if self.playlist_videos:
                self.loadingLabel.destroy()  # Eliminar el mensaje "Cargando..."
                
                # Lista para almacenar los estados de los CheckBoxes
                self.checkboxStates = []
                
                for i, video in enumerate(self.playlist_videos, start=1):
                    video_title = video['title']
                    
                    if len(video_title) > maxTextLength:
                        video_title = video_title[:maxTextLength] + "..."
                    
                    checkboxVar = ctk.BooleanVar(value=True)
                    self.checkboxStates.append(checkboxVar)

                    indexVideo = ctk.CTkLabel(self.videosListScrollable, text=f"{i}.", font=self.regularFont)
                    indexVideo.grid(row=i, column=0, sticky="w", padx=10, pady=5)
                    
                    checkboxVideo = ctk.CTkCheckBox(self.videosListScrollable, text=video_title, variable=checkboxVar)
                    checkboxVideo.grid(row=i, column=1, sticky="w")
                    
                
                # Asegurar que el masterCheckbox coincida con el estado inicial
                self.masterCheckboxVar.set(True)
            else:
                self.loadingLabel.configure(text="No se encontraron videos")  # Mantener
         
         
        self.masterCheckboxVar = ctk.BooleanVar(value=True) 
        
        self.masterCheckbox = ctk.CTkCheckBox(self.videosFromPlaylistFrame, text="Deselect all", command=self.toggleAllCheckboxes, variable=self.masterCheckboxVar  )
        self.masterCheckbox.grid(row=3, column=0, sticky="s")  
            
        # Ejecutar `loadPlaylistVideos` después de 500ms (medio segundo) sin congelar la UI
        self.videosListScrollable.after(500, loadPlaylistVideos)
    
    
    """ Clears all video information by removing existing widgets from the frame """
    def clearVideoInfo(self):
        for widget in self.videoInfoFrame.winfo_children():
            widget.destroy()
            
    
    """ Toggles all checkboxes based on the state of the master checkbox """    
    def toggleAllCheckboxes(self):
        newState = self.masterCheckboxVar.get()
        
        # Updates the state of each individual checkbox
        for checkbox in self.checkboxStates:
            checkbox.set(newState)
            
        # Forces an update of the global selection variable    
        self.masterCheckboxVar.set(newState)
        self.masterCheckbox.configure(text="Deselect All" if newState else "Select All")
        

            
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

        
    """ Shows the progress frame when the download starts """
    def show_progress_frame(self):
        for widget in self.videoInfoFrame.winfo_children():
            widget.destroy() # Removes any existing widgets

        # Taller than the other 280px views — videoInfoFrame splits its height 50/50 between two
        # weighted rows (this one and the empty-queue row), and the extra Cancel button row no
        # longer fits in a plain 280px window without overlapping optionsRow/videoConfigFrame below
        # (measured: 350 is the bare minimum, 380 leaves comfortable margin).
        self.root.geometry("750x380")
        self.progressVar = ctk.DoubleVar() # Initializes the progress bar variable
        
        self.progressFrame = ctk.CTkFrame(self.videoInfoFrame, fg_color="transparent")
        self.progressFrame.grid(row=0, column=1, columnspan=4, sticky="nsew", padx=10, pady=10)  # Ajusta según el layout
        self.progressFrame.grid_columnconfigure(1, weight=1)
        self.progressFrame.grid_columnconfigure(2, weight=1)
        self.progressFrame.grid_columnconfigure(3, weight=1)
        self.progressFrame.grid_columnconfigure(4, weight=1)
        
        self.progressLabel = ctk.CTkLabel(self.progressFrame, text="Downloading...")
        self.progressLabel.grid(row=0, column=0, pady=5, columnspan=5)

        
        self.progressBar = ctk.CTkProgressBar(self.progressFrame, variable=self.progressVar)
        self.progressBar.grid(row=1, column=0, sticky="ew", padx=10, pady=10, columnspan=5)
        self.progressBar.set(0)  # Iniciar en 0%

        self.speedLabel = ctk.CTkLabel(self.progressFrame, text="Speed: - ETA: -")
        self.speedLabel.grid(row=2, column=0, pady=5, columnspan=5)

        # Lives only inside this frame, which is created fresh per download and destroyed by
        # hide_progress_frame — so "visible only during an active download" comes for free.
        self.cancelDownloadButton = ctk.CTkButton(self.progressFrame, text="Cancel", command=self.requestCancel)
        self.cancelDownloadButton.configure(fg_color="#191818", font=self.regularFont, height=30, width=100, hover_color="#FF4C58")
        self.cancelDownloadButton.grid(row=3, column=0, pady=(5, 0), columnspan=5)


    """ Signals the active download thread to stop via _progress_hook, and disables the button
    immediately so a second click can't fire while the worker thread unwinds. """
    def requestCancel(self):
        self.cancelRequested.set()
        self.cancelDownloadButton.configure(state="disabled", text="Cancelling...")


    """ Hides the progress frame after the download is completed """
    def hide_progress_frame(self):
        if hasattr(self, "progressFrame"):
            self.progressFrame.destroy()
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
        self.urlInput.bind("<KeyRelease>", lambda _: self.validateURL())

        # Button to select the download destination folder
        self.folderButton = ctk.CTkButton(self.selectFolderFrame, text="", command=self.selectDownloadFolder, image=CTkImage(dark_image=self.folderImg, light_image=self.folderImg));
        self.folderButton.configure(fg_color="#191818", font=self.regularFont, height=33, width=80, hover_color="#FF4C58");
        self.folderButton.grid(row=0, column=2, sticky='n')
      
        self.downloadBtn = ctk.CTkButton(self.videoConfigFrame, text="Download", command=self.conditionalDownload, state="disabled")
        self.downloadBtn.configure(fg_color="transparent", border_width=2, border_color="#FF4C58", hover_color="#FF4C58", height=35, width=170, font=self.regularFont)
        self.downloadBtn.grid(row=0, column=3, sticky='ne')
      

if __name__ == "__main__":
    logFile = logs.setup_logging()
    log.info("MP3Vault %s starting (yt-dlp %s) - https://github.com/caladavid/MP3Vault", APP_VERSION, yt_dlp.version.__version__)
    log.info("Log file: %s", logFile)
    root = ctk.CTk();
    app = MP3Vault(root);
    root.mainloop(); 
    