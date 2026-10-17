import re
import sys
import os
import threading
import customtkinter as ctk
from customtkinter import *
from PIL import Image
from tkinter import messagebox

import yt_dlp

from core import downloader, naming, tagging, thumbnail, updates, ytdl

# Welcome message
print("Welcome to MP3Vault!")
print("Get started by entering a YouTube URL below.\n")

# Print information about the application's creator and GitHub repository
print("MP3Vault - Created by David Cala")
print("Version 1.2")
print("GitHub Repository: https://github.com/caladavid/MP3Vault\n")

# Define a regular expression pattern to clean filenames


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
        self.downloadPath = "";
        self.urlValue = StringVar();
        self.editInfoWindow = None
        
        self.titleAudioVar = ctk.StringVar()
        self.artistAudioVar = ctk.StringVar()
        self.albumAudioVar = ctk.StringVar()

        # Not persisted across restarts by design — resets to mp3/192kbps every launch.
        self.audioFormatVar = ctk.StringVar(value="mp3")
        self.audioQualityVar = ctk.StringVar(value="192")

        # Set right before spawning a download thread, checked inside DownloadSession.hook (which
        # runs ON that thread) to abort cleanly via yt_dlp.utils.DownloadCancelled instead of
        # killing the thread outright.
        self.cancelRequested = threading.Event()

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

        self.setupUI();
        self.noURL()

        threading.Thread(target=self.checkYtDlpUpdate, daemon=True).start()


    """ Open a folder dialog to select the download destination folder """
    def selectDownloadFolder(self):
        self.downloadPath = filedialog.askdirectory(initialdir=os.path.expanduser("~"))
        self.folderInput.configure(text=self.downloadPath)
        print(self.downloadPath)


    """ Hides the quality dropdown for lossless/uncompressed formats where bitrate is meaningless """
    def onFormatChange(self, value):
        if value in ytdl.LOSSLESS_FORMATS:
            self.qualityLabel.grid_remove()
            self.qualityMenu.grid_remove()
        else:
            self.qualityLabel.grid()
            self.qualityMenu.grid()


    """ Checks PyPI for a newer yt-dlp release — notify only, never auto-installs. Runs on a
    background thread at startup; any failure (offline, PyPI down, unexpected response shape) is
    swallowed silently so a flaky network never disrupts opening the app. """
    def checkYtDlpUpdate(self):
        try:
            latestVersion = updates.newer_ytdlp_version()
            if latestVersion:
                self.root.after(0, self.showUpdateNotice, latestVersion)
        except Exception:
            pass


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
        self.root.after(0, lambda: messagebox.showinfo("Update yt-dlp", message))
        self.root.after(0, lambda: self.updateNoticeButton.configure(state="disabled", text=""))


    # Window width is fixed at 750 and never resizes (root.resizable(0, 0)), so the space actually
    # left for the title after the 200px thumbnail, fixed paddings, and the Edit button is a
    # constant too — measured directly from the real widget tree (see conversation/commit notes).
    # CTkLabel needs wraplength AND width set to the same value: wraplength alone still leaves the
    # widget's own canvas at its small default size, and grid can silently shrink a too-large width
    # to fit its column — either mismatch clips the wrapped text instead of showing it in full.
    TITLE_WRAPLENGTH_SINGLE = 340   # single-video view: Edit button shares the same inner frame
    TITLE_WRAPLENGTH_PLAYLIST = 385  # playlist view: Edit button lives in a separate outer column


    """ Start a new thread to fetch video information when a URL is provided """
    def threadingButton(self, url: str):
        if url:
            self.displayMessage("Loading... Please wait")
            threading.Thread(target=self.fetchVideoInfo, args=(url,), daemon=True).start()


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
            self.isPlaylist = None
            self.downloadBtn.configure(state="disabled")
            self.resetToDefault(isEmpty=False)


    """ Extract video information in a background thread """
    def fetchVideoInfo(self, url: str):
         # Store the video URL and set youtube-dl options
        self.videoUrl = url
        # Local var, not self.ydl_opts: fetchVideoInfo can be re-triggered in a new thread while
        # a download thread is still running, and a shared instance attribute would race between them.
        ydl_opts = ytdl.info_options()

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_video = ydl.extract_info(url, download=False)


                self.root.after(0, self.getInfoVideo, info_video)

        # Handle specific download errors from yt_dlp
        # This except block runs on the worker thread, so every UI call is routed through root.after
        except yt_dlp.utils.DownloadError as e:
            errorMsg = str(e)

            if "HTTP Error 400" in errorMsg:
                self.root.after(0, self.displayMessage, "Bad request (Error 400). Please check the URL.")
            elif "HTTP Error 404" in errorMsg:
                self.root.after(0, self.displayMessage, "Video not found (Error 404).")
            elif "HTTP Error 403" in errorMsg:
                self.root.after(0, self.displayMessage, "Access denied (Error 403).")
            elif "HTTP Error 500" in errorMsg:
                self.root.after(0, self.displayMessage, "Internal server error (Error 500).")
            elif "youtube:truncated_id" in errorMsg:
                self.root.after(0, self.displayMessage, "The YouTube video ID is incomplete or truncated.")
            elif "Video unavailable" in errorMsg:
                self.root.after(0, self.displayMessage, "The YouTube video ID is unavailable.")
            else:
                self.root.after(0, self.displayMessage, f"Error retrieving video information: {errorMsg}")


        except Exception as e:
            self.root.after(0, self.displayMessage, f"Unexpected error: {str(e)}")
            
   
    """ Clears the URL input field and resets UI elements """
    def cleanURL(self):
        if self.urlValue.get() != "":
            self.urlValue.set("");
            self.downloadBtn.configure(state="disabled")
            self.root.geometry("750x280")
            self.clearVideoInfo()
            self.noURL()
            
            
    """ Determines whether to download a single video or a playlist """
    def conditionalDownload(self):
        if self.isPlaylist is None:
            return

        if not self.downloadPath:
            messagebox.showwarning("Warning", "Please select a download folder first.")
            return

        # Runs on the main thread (conditionalDownload isn't a worker thread), so a blocking
        # askyesno here is safe — no root.after needed, unlike everything inside the download threads.
        if not self.isPlaylist:
            _, predictedName = naming.build_clean_title_and_filename(self.artistAudioVar.get(), self.titleAudioVar.get(), self.audioFormatVar.get())
            predictedPath = os.path.join(os.path.normpath(self.downloadPath), predictedName)
            if os.path.exists(predictedPath):
                if not messagebox.askyesno("Already downloaded", f'"{predictedName}" already exists in that folder. Download again and overwrite it?'):
                    return

        # Prevents a double-click from starting two overlapping download threads on the same file
        if getattr(self, "isDownloading", False):
            return
        self.isDownloading = True
        self.cancelRequested.clear()

        if self.isPlaylist:
            threading.Thread(target=self.downloadPlaylist, daemon=True).start()
        else:

            threading.Thread(target=self.downloadAudio, daemon=True).start()
        
                    
            
    """ Update metadata for an audio file using the provided information """
    def updateMetadata(self, title: str, artist: str, album: str, filePath: str, trackNumber=None):
        # Called from the download worker threads (downloadPlaylist), so any displayMessage here
        # must go through root.after rather than touching widgets directly.
        try:
            tagging.write_tags(filePath, title, artist, album, track_number=trackNumber)
        except FileNotFoundError as e:
            self.root.after(0, self.displayMessage, f"Error: {e}")
        except Exception as e:
            self.root.after(0, self.displayMessage, f"Error updating metadata: {e}")


    """ Handles video information retrieval and processes accordingly """
    def getInfoVideo(self, info_video: str):
         # If the URL contains 'list=', it's a playlist
        if "list=" in self.videoUrl:
            self.videoInPlaylist = self.videoUrl.split("&list=")[0]
            self.processPlaylist(self.videoInPlaylist, info_video)
        else:
            self.processSingleVideo(info_video)


         
    """ Process a YouTube playlist and extract video information """
    def processPlaylist(self, videoInPlaylist: str, info_video: str):
        self.getVideoFromPlaylist(videoInPlaylist)
        if "entries" in info_video:  
            self.handlePlaylistInfo(info_video)
         
            
    """ Process a single video and extract information """        
    def processSingleVideo(self, info_video: str):
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
        self.title_video = info_video.get('title').strip()
        self.album_video = info_video.get('album', '')
        self.channel_video = info_video.get('channel', '')
        self.artist_video = info_video.get('artist', self.channel_video)
        self.album_thumbnail = info_video.get('thumbnail') 
        self.updateVideoInfo(self.album_thumbnail)
        
    
    """ Extracts video information from a playlist """
    def getVideoFromPlaylist(self, videoInPlaylist: str):
        # Own local options dict, not self.ydl_opts — see the note in fetchVideoInfo about the race.
        ydl_opts = ytdl.info_options()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_video_in_playlist = ydl.extract_info(videoInPlaylist, download=False)
            self.title_video = info_video_in_playlist.get('title').strip()
            self.album_video = info_video_in_playlist.get('album', '')
            self.channel_video = info_video_in_playlist.get('channel', '')
            self.artist_video = info_video_in_playlist.get('artist', self.channel_video)
            self.album_thumbnail = info_video_in_playlist.get('thumbnail')
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


    """ New per-download session: cancel flag + list of files this run writes (see DownloadSession).
    Its progress callback hands off to _updateProgressUI via root.after, because the hook runs on
    the download worker thread and widget access must stay on the main thread. """
    def newDownloadSession(self):
        return ytdl.DownloadSession(
            self.cancelRequested,
            on_progress=lambda d: self.root.after(0, self._updateProgressUI, d),
        )


    def _updateProgressUI(self, d):
        # Updates queued via root.after can arrive after the progress frame was destroyed (e.g. a
        # new URL loaded meanwhile); touching its widgets then raises TclError (verified).
        if not (hasattr(self, "progressFrame") and self.progressFrame.winfo_exists()):
            return

        # If downloading from a playlist, get the dynamic title
        # playlist_index lives in d['info_dict'], not at the top level of the hook dict (verified),
        # and is the REAL playlist position, so look the title up by it instead of by list offset.
        info = d.get('info_dict') or {}
        currentIndex = info.get('playlist_index')
        videoTitle = next((v['title'] for v in getattr(self, 'playlist_videos', []) if v['playlistIndex'] == currentIndex), None)
        if currentIndex is not None and videoTitle:
            title = f"{videoTitle} ({currentIndex}/{info.get('playlist_count', '?')})"
        else:
            title = self.titleAudioVar.get()

        # Remove ANSI escape sequences from speed and ETA (not every progress dict has these keys)
        speed = re.sub(r'\x1b\[[0-9;]*m', '', d.get('_speed_str', '')).strip()
        eta = re.sub(r'\x1b\[[0-9;]*m', '', d.get('_eta_str', 'N/A')).strip()

        if d['status'] == 'downloading':
            percent_str = re.sub(r'\x1b\[[0-9;]*m', '', d.get('_percent_str', '0%'))
            percent = float(percent_str.strip('%'))  # Convert percentage to decimal (0-1)
            self.progressVar.set(percent / 100)  # Update progress bar variable
            self.progressBar.update_idletasks()  # Refresh the UI

            self.progressLabel.configure(text=f"Descargando: {title}")
            self.speedLabel.configure(text=f"Velocidad: {speed} - ETA: {eta}")

        elif d['status'] == 'finished':
            self.progressLabel.configure(text=f"Descarga completada: {title}")
            self.speedLabel.configure(text="¡Completado!")
            self.progressVar.set(1)  # Set progress bar to 100%
           
   
    """ Downloads and tags a single video URL (see downloader.download_single), shared by the
    single-URL button and the URL queue. A tagging failure is shown but still counts as success. """
    def _downloadSingleUrl(self, url: str, title: str, uploader: str, album: str):
        result = downloader.download_single(
            url, title, uploader, album, self.downloadPath,
            self.audioFormatVar.get(), self.audioQualityVar.get(), self.newDownloadSession(),
        )
        if result["tagError"]:
            self.root.after(0, self.displayMessage, f"Error updating metadata: {result['tagError']}")
        return result


    """ Initiates audio download from a given URL """
    def downloadAudio(self):
        self.videoUrl = self.urlInput.get()

        if "list=" in self.videoUrl:
            self.videoUrl = self.videoInPlaylist

        self.root.after(0, self.show_progress_frame)

        title = self.titleAudioVar.get()
        uploader = self.artistAudioVar.get()
        album = self.albumAudioVar.get()

        try:
            result = self._downloadSingleUrl(self.videoUrl, title, uploader, album)

            if result["success"]:
                self.root.after(0, lambda: messagebox.showinfo("Download Success", f"{result['filename']} - Downloaded Successfully"))
            elif result.get("cancelled"):
                self.root.after(0, self.displayMessage, "Download cancelled.")
            else:
                self.root.after(0, self.displayMessage, f"An error occurred: {result['error']}")

            # Ocultar ProgressBar al finalizar
            self.root.after(0, self.hide_progress_frame)

        finally:
            self.isDownloading = False
   
   
    """ Downloads selected videos from a playlist """
    def downloadPlaylist(self):
        # Wrapping the whole method in try/finally (instead of just around the yt-dlp call)
        # guarantees isDownloading resets even on the early-return guard clauses below.
        try:
            self.videoUrl = self.urlInput.get()
            uploader = self.artistAudioVar.get().strip()
            album = self.albumAudioVar.get()

            # Validates if at least one video is selected before proceeding with download
            if not any(state.get() for state in self.checkboxStates):
                self.root.after(0, lambda: messagebox.showwarning("Warning", "Please select at least one video to download."))
                return

            # Schedules the transition to the progress frame in the main event loop
            self.root.after(0, self.show_progress_frame)

            # Predicts each selected video's final filename (same helper as the single-video check)
            # and skips any that already exist — asking per-song would be impractical for a
            # multi-track playlist, so this auto-skips instead of prompting.
            uploaderClean = naming.clean_uploader(uploader)
            download_path_check = os.path.normpath(self.downloadPath)
            selected_indices = []
            skippedExisting = 0
            for i, state in enumerate(self.checkboxStates):
                if not state.get():
                    continue
                predictedName = naming.predict_playlist_filename(uploaderClean, self.playlist_videos[i]['title'], self.audioFormatVar.get())
                if os.path.exists(os.path.join(download_path_check, predictedName)):
                    skippedExisting += 1
                else:
                    selected_indices.append(str(self.playlist_videos[i]['playlistIndex']))

            # Ensures that at least one video is selected before proceeding
            if not selected_indices:
                if skippedExisting:
                    self.root.after(0, lambda: messagebox.showinfo("Nothing to download", f"All {skippedExisting} selected song(s) already exist in that folder."))
                else:
                    self.root.after(0, lambda: messagebox.showwarning("Warning", "No videos selected for download."))
                return

            # Joins selected indices into a comma-separated string for further processing
            playlistItems = ",".join(selected_indices)

            audioFormat = self.audioFormatVar.get()
            session = self.newDownloadSession()
            ydl_opts = {
                'format': 'bestaudio/best',
                'writethumbnail': audioFormat != 'wav',
                'postprocessors': ytdl.build_audio_postprocessors(audioFormat, self.audioQualityVar.get()),
                'add_metadata': True,
                'socket_timeout': 60,
                'progress_hooks': [session.hook],
                "outtmpl": f'{self.downloadPath}/%(title)s.%(ext)s',
                'playlist_items': playlistItems,  # Descargar solo los videos seleccionados
                'extractor_args': ytdl.EXTRACTOR_ARGS,
            }

            # yt-dlp writes a thumbnail for the playlist itself (not just each video), and nothing
            # ever embeds/deletes that one — snapshot the folder now so we can remove it afterwards
            # without having to guess yt-dlp's own filename-sanitizing rules for the playlist title.
            download_path_before = os.path.normpath(self.downloadPath)
            filesBeforeDownload = ytdl.list_folder(download_path_before)

            downloadedCount = 0
            playlistThumbStem = None
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                playlist_info = ydl.extract_info(self.videoUrl, download=True)
                # The playlist-level thumbnail is named after the playlist itself (verified:
                # "Popular Music Videos.NA" from prepare_filename -> "Popular Music Videos.jpg").
                playlistThumbStem = os.path.splitext(os.path.basename(ydl.prepare_filename(playlist_info)))[0]
                if "entries" in playlist_info:
                    # If the URL is a playlist, we loop through each video in the playlist
                    for fallbackIndex, video in enumerate(playlist_info["entries"], start=1):
                        title = (video.get('title') or 'Desconocido').strip()
                        # playlist_index reflects the video's real position in the playlist (yt_dlp
                        # sets it during playlist processing); fall back to loop position only if
                        # yt_dlp didn't provide one.
                        trackNumber = video.get('playlist_index') or fallbackIndex

                        # yt-dlp wrote "<its sanitized title>.<ext>"; after conversion the extension
                        # is the selected format. Renamed through the SAME helper the
                        # already-downloaded prediction uses, so the two can't drift apart.
                        baseFilename = os.path.splitext(os.path.basename(ydl.prepare_filename(video)).strip())[0]
                        old_filepath = naming.safe_join(download_path_before, f"{baseFilename}.{audioFormat}")
                        new_filepath = naming.safe_join(download_path_before, naming.playlist_filename(uploaderClean, baseFilename, audioFormat))

                        # os.replace (not os.rename) because on Windows os.rename raises
                        # FileExistsError if new_filepath already exists (e.g. re-downloading a track)
                        if os.path.exists(old_filepath) and old_filepath != new_filepath:
                            os.replace(old_filepath, new_filepath)
                            print("File renamed successfully:", new_filepath)
                        else:
                            print("No renaming needed, using:", new_filepath)

                        if os.path.exists(new_filepath):
                            self.updateMetadata(naming.clean_filename(title), uploaderClean, album, new_filepath, trackNumber=trackNumber)
                            downloadedCount += 1
                        else:
                            print(f"Error: File not found: {new_filepath}")

                # Reports a count instead of a single filename — a playlist has many files, and
                # "entries" can legitimately be empty (e.g. every selected video was deleted/private).
                skippedSuffix = f" ({skippedExisting} already existed, skipped)" if skippedExisting else ""
                if downloadedCount:
                    self.root.after(0, lambda: messagebox.showinfo("Download Success", f"{downloadedCount} song(s) downloaded successfully{skippedSuffix}"))
                else:
                    self.root.after(0, lambda: messagebox.showwarning("Warning", "No videos were downloaded."))

            # Clean up the orphaned playlist-level thumbnail (see snapshot comment above) — only the
            # new image named exactly after the playlist, never any other image that showed up in
            # the folder meanwhile (per-video thumbnails are already consumed by EmbedThumbnail).
            for newFile in ytdl.list_folder(download_path_before) - filesBeforeDownload:
                stem, ext = os.path.splitext(newFile)
                if stem == playlistThumbStem and ext.lower() in ('.jpg', '.jpeg', '.webp', '.png'):
                    try:
                        os.remove(os.path.join(download_path_before, newFile))
                    except OSError:
                        pass

            self.root.after(0, self.hide_progress_frame)

        except yt_dlp.utils.DownloadCancelled:
            # Cancellation jumps straight here from inside the `with` block, skipping the
            # thumbnail cleanup above entirely — so it needs to run again here, and also cover
            # partial audio downloads (.part/.ytdl), not just leftover thumbnail images.
            session.remove_cancelled_files(download_path_before, filesBeforeDownload)
            self.root.after(0, self.displayMessage, "Download cancelled.")

        except Exception as e:
            self.root.after(0, self.displayMessage, f"An error occurred: {e}")

        finally:
            self.isDownloading = False


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
        threading.Thread(target=self._runQueueWorker, args=(urls,), daemon=True).start()


    """ Downloads each queued URL sequentially, reusing the same core as the single-URL flow """
    def _runQueueWorker(self, urls):
        self.root.after(0, self.show_progress_frame)

        successCount = 0
        failCount = 0
        skippedExisting = 0
        wasCancelled = False
        total = len(urls)

        for i, url in enumerate(urls, start=1):
            # Checked here too (not just inside _progress_hook) in case Cancel arrives while
            # between items — e.g. during the metadata fetch below, which has no progress hook.
            if self.cancelRequested.is_set():
                wasCancelled = True
                break

            self.root.after(0, lambda i=i: self.progressLabel.configure(text=f"Descargando {i}/{total}..."))

            # The queue never touches urlInput/titleAudioVar (those belong to the single-URL flow),
            # so each item needs its own lightweight metadata fetch — same options as fetchVideoInfo,
            # but run synchronously here since we're already on a background thread.
            ydl_opts = ytdl.info_options()
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception:
                failCount += 1
                continue

            title = (info.get('title') or 'Unknown').strip()
            channel = info.get('channel', '')
            artist = info.get('artist', channel)
            album = info.get('album', '')

            # Same already-downloaded check as the single-URL/playlist flows, auto-skipping rather
            # than prompting — a queue can have many items, asking per-song isn't practical here either.
            _, predictedName = naming.build_clean_title_and_filename(artist, title, self.audioFormatVar.get())
            if os.path.exists(os.path.join(os.path.normpath(self.downloadPath), predictedName)):
                skippedExisting += 1
                continue

            result = self._downloadSingleUrl(url, title, artist, album)
            if result.get("cancelled"):
                # Cancel aborts the whole remaining queue, not just the current item — same
                # simplification as the playlist flow, and consistent with a single Cancel button.
                wasCancelled = True
                break
            elif result["success"]:
                successCount += 1
            else:
                failCount += 1

        summary = "Cancelled. " if wasCancelled else ""
        summary += f"{successCount} downloaded"
        if skippedExisting:
            summary += f", {skippedExisting} already existed (skipped)"
        if failCount:
            summary += f", {failCount} failed"
        self.root.after(0, lambda: messagebox.showinfo("Queue finished", summary))
        self.root.after(0, self.hide_progress_frame)
        self.isDownloading = False


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
                print(f"Error loading thumbnail: {e}")
                image_pil = None
            self.root.after(0, applyResult, image_pil)

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
                    print(f"Error destroying widget: {e}")
        
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

        self.formatMenu = ctk.CTkOptionMenu(self.optionsRow, values=["mp3", "m4a", "flac", "wav"], variable=self.audioFormatVar, command=self.onFormatChange)
        self.formatMenu.configure(font=self.regularFont, fg_color="#191818", button_color="#191818", button_hover_color="#FF4C58", width=90, height=30)
        self.formatMenu.grid(row=0, column=1, sticky='w', padx=(0, 20))

        self.qualityLabel = ctk.CTkLabel(self.optionsRow, text="Quality:")
        self.qualityLabel.configure(text_color="#FFFFFF", font=self.regularFont)
        self.qualityLabel.grid(row=0, column=2, sticky='w', padx=(0, 10))

        self.qualityMenu = ctk.CTkOptionMenu(self.optionsRow, values=["128", "192", "320"], variable=self.audioQualityVar)
        self.qualityMenu.configure(font=self.regularFont, fg_color="#191818", button_color="#191818", button_hover_color="#FF4C58", width=90, height=30)
        self.qualityMenu.grid(row=0, column=3, sticky='w')

        # Always present (rather than grid()/grid_remove()'d in only when relevant) so its
        # appearance never changes this row's height or triggers a geometry recalculation — it's
        # just blank/disabled until checkYtDlpUpdate finds a newer release.
        self.optionsRow.columnconfigure(4, weight=1)
        self.updateNoticeButton = ctk.CTkButton(self.optionsRow, text="", command=self.onUpdateNoticeClick, state="disabled")
        self.updateNoticeButton.configure(fg_color="transparent", font=self.regularFont, height=30, hover_color="#FF4C58", text_color="#FFFFFF")
        self.updateNoticeButton.grid(row=0, column=4, sticky='e')

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
    root = ctk.CTk();
    app = MP3Vault(root);
    root.mainloop(); 
    