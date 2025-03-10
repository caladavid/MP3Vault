import re
import sys
import os
import customtkinter as ctk
import threading
from customtkinter import * 
from PIL import Image, ImageTk, ImageOps
from tkinter import messagebox, ttk
from moviepy.video.io.VideoFileClip import VideoFileClip
from mutagen.easyid3 import EasyID3
from idlelib.tooltip import Hovertip
import requests
from io import BytesIO
from urllib.request import urlopen

import yt_dlp

# Welcome message
print("Welcome to MP3Vault!")
print("Get started by entering a YouTube URL below.\n")

# Print information about the application's creator and GitHub repository
print("MP3Vault - Created by David Cala")
print("Version 1.2")
print("GitHub Repository: https://github.com/caladavid/MP3Vault\n")

# Define a regular expression pattern to clean filenames


class MP3Vault:
    def __init__(self, root):
        # Create the main application window
        self.root = root
        self.root.title("MP3Vault")
        self.root.geometry("750x280")
        self.root.resizable(0, 0)
        
        # grid layout
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)  # videoInfoFrame
        self.root.rowconfigure(2, weight=1)  # videoConfigFrame
        
        self.padding = 20
        
        self.regularFont = ctk.CTkFont(family="Lato", size=14);
        self.titleFont = ctk.CTkFont(family="Lato", size=16, weight="bold");
        self.folderImg = Image.open("folder.png");
        self.editImg = Image.open("editar.png");
        self.downloadPath = "";
        self.urlValue = StringVar();
        self.editInfoWindow = None
        
        self.titleAudioVar = ctk.StringVar()
        self.artistAudioVar = ctk.StringVar()
        self.albumAudioVar = ctk.StringVar()
        
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

        # Get absolute path to resource, works for dev and for PyInstaller
        def resource_path(relative_path):
            try:
                # PyInstaller creates a temp folder and stores path in _MEIPASS
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.abspath(".")

            return os.path.join(base_path, relative_path)

        # Set the application icon
        self.iconPath = resource_path('icon.ico')
        self.root.iconbitmap(self.iconPath)

        self.setupUI();
        self.noURL()
      
      
    """ Open a folder dialog to select the download destination folder """    
    def selectDownloadFolder(self):
        self.downloadPath = filedialog.askdirectory(initialdir="D:\Downloads")
        self.folderInput.configure(text=self.downloadPath)
        print(self.downloadPath)
        
        
        
    VALID_FILENAME_CHARS = re.compile(
        r'[^\w\s\-\'.()&,]'  # Caracteres no permitidos
        r'[\\/:*?"<>|]' # Caracteres no válidos en nombres de archivo
        r'|\(Official Audio\)'  # Elimina "(Official Audio)"
        r'|\(\s-\sTopic\)'  # Elimina "( - Topic)"
        r'|\(official\)'  # Elimina "(official)" (case-sensitive)
        r'|\((?i:video)\)'  # Elimina "(video)" o "(Video)" (case-insensitive)
        r'|\((?i:audio)\)'  # Elimina "(audio)" o "(Audio)" (case-insensitive)
        r'|\((Remaster|Remastered)\)'  # Elimina "(Remaster)" o "(Remastered)"
        r'|\(\)',  # Elimina paréntesis vacíos "()"
    )


    """ Clean a filename by removing special characters based on a regex pattern """
    def cleanFilename(self, filename: str):
        return re.sub(self.VALID_FILENAME_CHARS, "", filename).strip()
    
    
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
            
        if url.startswith("https://www.youtube.com/watch?v=") or url.startswith("https://youtu.be/"):
            self.isPlaylist = False
            
            # Extract the video ID and validate its length
            video_id = url.split("watch?v=")[-1] if "watch?v=" in url else url.split("youtu.be/")[-1]
            if len(video_id) < 11:
                self.displayMessage("The YouTube video ID is incomplete or truncated.")
                return
            
            self.downloadBtn.configure(state="normal")
            self.threadingButton(url)

        elif url.startswith("https://www.youtube.com/playlist"):
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
        self.ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'socket_timeout': 10
        }

        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info_video = ydl.extract_info(url, download=False)

                
                self.root.after(0, self.getInfoVideo, info_video)
                
        # Handle specific download errors from yt_dlp
        except yt_dlp.utils.DownloadError as e:
            errorMsg = str(e)
            
            if "HTTP Error 400" in errorMsg:
                self.displayMessage("Bad request (Error 400). Please check the URL.")
            elif "HTTP Error 404" in errorMsg:
                self.displayMessage("Video not found (Error 404).")
            elif "HTTP Error 403" in errorMsg:
                self.displayMessage("Access denied (Error 403).")
            elif "HTTP Error 500" in errorMsg:
                self.displayMessage("Internal server error (Error 500).")
            elif "youtube:truncated_id" in errorMsg:
                self.displayMessage("The YouTube video ID is incomplete or truncated.")
            elif "Video unavailable" in errorMsg:
                self.displayMessage("The YouTube video ID is unavailable.")
            else:
                self.displayMessage(f"Error retrieving video information: {errorMsg}")
           
                
        except Exception as e:
            self.displayMessage(f"❌ Error inesperado: {str(e)}")
            
   
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
       
        if self.isPlaylist:
            threading.Thread(target=self.downloadPlaylist, daemon=True).start()
        else:
            
            threading.Thread(target=self.downloadAudio, daemon=True).start()
        
                    
            
    """ Update metadata for an MP3 file using the provided information """
    def updateMetadata(self, title: str, artist: str, album: str, audioWithNoMetadata: str, downloadPath: str, customFileName=None):
        filePath = os.path.join(downloadPath, audioWithNoMetadata)
        #print('Ruta completa:', filePath)  # Para depuración

        if not os.path.exists(filePath):
            self.displayMessage(f"Error: File not found - {filePath}")
            return

        try:
            # Ensure values are not None before assigning metadata 
            audioMetadata = EasyID3(filePath)
            
            audioMetadata['title'] = customFileName or title
            audioMetadata['artist'] = artist
            audioMetadata['albumartist'] = artist
            audioMetadata['album'] = str(album)
            
            audioMetadata.save()
            
        except Exception as e:
            self.displayMessage(f"Error updating metadata: {e}")


    """ Handles video information retrieval and processes accordingly """
    def getInfoVideo(self, info_video: str):
        global videoInPlaylist
        
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
            or (info_video["entries"][0].get("channel") if info_video.get("entries") else "Not available")
        )
        self.playlistArtist = info_video.get('artist', self.playlistChannel)
        self.albumArtistVideo = info_video.get('uploader', 'Not available')
        
         # Extract the first available thumbnail URL, if present
        self.playlist_thumbnail  = (
            info_video['thumbnails'][0]['url']
            if info_video.get('thumbnails') and len(info_video['thumbnails']) > 0
            else None
        )
        
        videos = info_video.get("entries", [])
        self.playlist_videos = []
        
        for video in videos:
            video_title = video.get('title').strip()
            
            # If the video is marked as deleted, skip it
            if not video_title == "[Deleted video]":
                self.playlist_videos.append({
                'title': video_title,
        }) 
        
        self.updatePlaylistInfo(self.playlist_thumbnail)  
    
    
    """ Handles processing of a single video """    
    def handleSingleVideoInfo(self, info_video: str):                                        
        self.title_video = info_video.get('title').strip()
        self.album_video = info_video.get('album', 'Not available')
        self.channel_video = info_video.get('channel', 'Not available')
        self.artist_video = info_video.get('artist', self.channel_video)
        self.album_thumbnail = info_video.get('thumbnail') 
        self.updateVideoInfo(self.album_thumbnail)
        
    
    """ Extracts video information from a playlist """    
    def getVideoFromPlaylist(self, videoInPlaylist: str):   
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            info_video_in_playlist = ydl.extract_info(videoInPlaylist, download=False)
            self.title_video = info_video_in_playlist.get('title').strip()
            self.album_video = info_video_in_playlist.get('album', 'Not available')
            self.channel_video = info_video_in_playlist.get('channel', 'Not available')
            self.artist_video = info_video_in_playlist.get('artist', self.channel_video)
            self.album_thumbnail = info_video_in_playlist.get('thumbnail')
            self.updateVideoInfo(self.album_thumbnail)
        
    
    """ Closes the pop-up window for editing playlist information """    
    def closeEditInfoPopUp(self): 
        newPlaylistTitleAudio = self.titleEditUrlEntry.get()     
        self.playlistTitleAudio = self.titleAudioVar.set(newPlaylistTitleAudio)
        self.editInfoWindow.destroy()
        
        
    """ Opens a pop-up window to edit the playlist information """
    def editInfoPopUp(self):
        if self.editInfoWindow and self.editInfoWindow.winfo_exists():
            self.editInfoWindow.lift()
            return
        
        self.editInfoWindow = ctk.CTkToplevel(self.root)
        self.editInfoWindow.geometry("410x250")
        self.editInfoWindow.title("Edit audio details")
        
        self.titleEditUrlEntry = self.titleAudioVar
        self.artistEditUrlEntry = self.artistAudioVar
        self.albumEditUrlEntry = self.albumAudioVar
        
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

        self.artistEditUrlInput = ctk.CTkEntry(self.editInfoUrlFrame, textvariable=self.artistAudioVar)
        self.artistEditUrlInput.grid(row=2, column=1, pady=10, sticky='nsew')
        self.artistEditUrlInput.configure(font=self.regularFont, text_color="#000000", fg_color="#FFFFFF", width=300, height=30)
        
        
        ### Label and entry for the folder destination ###
        self.albumEditLabel = ctk.CTkLabel(self.editInfoUrlFrame, text="Album");
        self.albumEditLabel.configure(text_color="#FFFFFF", font=self.regularFont, pady=1);
        self.albumEditLabel.grid(row=3, column=0, sticky='nsew', padx=(0, 10))

        self.albumEditUrlInput = ctk.CTkEntry(self.editInfoUrlFrame, textvariable=self.albumAudioVar)
        self.albumEditUrlInput.grid(row=3, column=1, pady=10, sticky='nsew')
        self.albumEditUrlInput.configure(font=self.regularFont, text_color="#000000", fg_color="#FFFFFF", width=300, height=30)
        
        # Button to select the download destination folder
        self.editInfoButton = ctk.CTkButton(self.editInfoUrlFrame, text="Confirm", command=self.closeEditInfoPopUp);
        self.editInfoButton.grid(row=4, column=1, pady=2)
        self.editInfoButton.configure(fg_color="#191818", font=self.regularFont, height=35, width=80, hover_color="#FF4C58");


    """ Handles the progress tracking of a download """
    def _progress_hook(self, d):
        # If downloading from a playlist, get the dynamic title
        if 'playlist_index' in d and d['playlist_index'] is not None:
            currentIndex = d['playlist_index']  # Video number in the playlist
            totalVideos = d.get('playlist_count', 1)  # Total number of videos
            title = f"{self.playlist_videos[currentIndex - 1]['title']} ({currentIndex}/{totalVideos})"
        else:
            title = self.titleAudioVar.get() 
        
        # Remove ANSI escape sequences from speed and ETA
        speed = re.sub(r'\x1b\[[0-9;]*m', '', d['_speed_str']).strip() 
        eta = re.sub(r'\x1b\[[0-9;]*m', '', d.get('_eta_str', 'N/A')).strip()

        if d['status'] == 'downloading':
            percent_str = re.sub(r'\x1b\[[0-9;]*m', '', d['_percent_str'])
            percent = float(percent_str.strip('%'))  # Convert percentage to decimal (0-1)
            self.progressVar.set(percent / 100)  # Update progress bar variable
            self.progressBar.update_idletasks()  # Refresh the UI

            self.progressLabel.configure(text=f"Descargando: {title}")
            self.speedLabel.configure(text=f"Velocidad: {speed} - ETA: {eta}")
        
        elif d['status'] == 'finished':
            self.progressLabel.configure(text=f"Descarga completada: {title}")
            self.speedLabel.configure(text="¡Completado!")
            self.progressVar.set(1)  # Set progress bar to 100%
           
   
    """ Initiates audio download from a given URL """
    def downloadAudio(self):   
        self.videoUrl = self.urlInput.get()
        
        if "list=" in self.videoUrl:
            self.videoUrl = self.videoInPlaylist
            
        self.root.after(0, self.show_progress_frame)
        
        title = self.titleAudioVar.get()
        uploader = self.artistAudioVar.get()
        album = self.albumAudioVar.get()

        self.ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            },
            {
            'key': 'FFmpegMetadata'  # Añade metadatos
            }],
            'noplaylist': True,
            'progress_hooks': [self._progress_hook],
            'extract_flat': 'in-playlist',
            'nocolor': True,
            "outtmpl": f'{self.downloadPath}/%(title)s.%(ext)s',
        }
        
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info_downloaded = ydl.extract_info(self.videoUrl, download=True)

                # Remove invalid characters from title
                invalidChars = r'[<>:"/\\|?*]'
                cleanTitle = re.sub(invalidChars, '', self.cleanFilename(title))
                
                # Use regular expressions to remove duplicate uploader names at the beginning of the filename
                pattern = rf"^(?:{re.escape(uploader)}\s*-\s*)+"
                remainder = re.sub(pattern, "", cleanTitle) 
                
                ext = "mp3"  
                finalFilename = f"{uploader} - {remainder}.{ext}"
                
                # Build file path
                download_path = os.path.normpath(self.downloadPath)  # Ensure a valid path format
                file_path = os.path.join(download_path, finalFilename)  # Complete file path
                
                 # Search for the downloaded file in the directory and rename it if necessary
                for file in os.listdir(download_path):
                    if file.endswith(".mp3") and cleanTitle in file:
                        old_filepath = os.path.join(download_path, file)  # Path of the downloaded file
                        if old_filepath != file_path:  # Check if the name is already correct
                            os.rename(old_filepath, file_path)  # Rename the file properly
                            print(f"✅ File renamed successfully: {file_path}")
                        break  # Stop searching once the file is found
            
                
                if os.path.exists(file_path):
                    self.updateMetadata(
                        cleanTitle, 
                        uploader, 
                        album, 
                        finalFilename, 
                        self.downloadPath
                    )
                else:
                    print("❌ Error: Downloaded file not found.")
                
                print(f"Downloaded: {finalFilename}")
                messagebox.showinfo("Download Success", f"{finalFilename} - Downloaded Successfully")
                
            # 🔹 Ocultar ProgressBar al finalizar
            self.root.after(0, self.hide_progress_frame)

        except Exception as e:
                #messagebox.showerror("Error", str(e))
                #print(f"An error occurred: {e}")
                self.displayMessage(f"An error occurred: {e}")
   
   
    """ Downloads selected videos from a playlist """             
    def downloadPlaylist(self):   
        self.videoUrl = self.urlInput.get()
        uploader = self.artistAudioVar.get().strip()
        album = self.albumAudioVar.get()
        
        # Validates if at least one video is selected before proceeding with download
        if not any(state.get() for state in self.checkboxStates):
            messagebox.showwarning("Warning", "Please select at least one video to download.")
            return
        
        # Schedules the transition to the progress frame in the main event loop
        self.root.after(0, self.show_progress_frame)
        
        #  Retrieve the indices of selected videos
        selected_indices = [
            str(i + 1)   #Convert 0-based indices to 1-based
            for i, state in enumerate(self.checkboxStates)
            if state.get()
        ]
        
        # Ensures that at least one video is selected before proceeding
        if not selected_indices:
            messagebox.showwarning("Warning", "No videos selected for download.")
            return
        
        # Joins selected indices into a comma-separated string for further processing
        playlistItems = ",".join(selected_indices)

        self.ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            },
            {
            'key': 'FFmpegMetadata'  # Añade metadatos
            }],
            
            'add_metadata': True,
            'socket_timeout': 60,
            'progress_hooks': [self._progress_hook],
            "outtmpl": f'{self.downloadPath}/%(title)s.%(ext)s',
            'playlist_items': playlistItems,  # Descargar solo los videos seleccionados
        }
        
        try:
            #print(f'El valor de "outtmpl" es: {self.ydl_opts["outtmpl"]}')
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                playlist_info = ydl.extract_info(self.videoUrl, download=True)
                if "entries" in playlist_info:
                    # If the URL is a playlist, we loop through each video in the playlist
                    for video in playlist_info["entries"]:
                        title = video.get('title', 'Desconocido').strip()

                        # Extracts the base name of the file, removing path info
                        generatedFilename = os.path.basename(ydl.prepare_filename(video)).strip()
                        
                        # Change the file extension to .mp3 if the conversion was successful
                        generatedFilename = generatedFilename.replace(".webm", ".mp3").replace(".m4a", ".mp3")

                        
                        # Use regular expressions to remove duplicate uploader names at the beginning of the filename
                        pattern = rf"^(?:{re.escape(uploader)}\s*-\s*)+"
                        remainder = re.sub(pattern, "", generatedFilename)    
                        
                        # Finalizes the file name by including only one uploader and the remainder of the original filename
                        newFilename = f"{uploader} - {remainder}" # Sets the final filename format
                        newFilename = os.path.basename(newFilename)  # Ensures there is no path info in the filename
                        
                        # Build the full path for the old and new file names
                        download_path = os.path.normpath(self.downloadPath) # Normalizes the download path
                        old_filepath = os.path.join(download_path, generatedFilename) # Old file path before renaming
                        new_filepath = os.path.join(download_path, newFilename) # New file path after renaming
                        
                        # Renames the file if needed, checking if the old and new paths are differen
                        if os.path.exists(old_filepath) and old_filepath != new_filepath:
                            os.rename(old_filepath, new_filepath) # Renames the file if a conflict exists
                            print("✅ File renamed successfully:", new_filepath)
                        else:
                            print("🔹 No renaming needed, using:", new_filepath)
                        
                        # Use the final filename to update the video metadata
                        filename = new_filepath

                        if os.path.exists(filename):
                             # If the file exists, proceed to update its metadata
                            self.updateMetadata(
                                self.cleanFilename(title),  
                                uploader,
                                album,
                                filename,
                                self.downloadPath,
                            )
                        else:
                            print(f"❌ Error: File not found: {filename}")
                messagebox.showinfo("Download Success", f"{filename} - Downloaded Successfully")
                
            if any(state.get() for state in self.checkboxStates):
                # 🔹 Ocultar ProgressBar al finalizar
                self.root.after(0, self.hide_progress_frame)

        except Exception as e:
                #messagebox.showerror("Error", str(e))
                self.displayMessage(f"An error occurred: {e}")
    
    
    """ Adjusts the wrap length of the text inside the video info frame dynamically """            
    def updateWraplength(self):
        containerWidth = self.textInsideVideoInfoFrame.winfo_width()
        
        # Defines a minimum wrap length to ensure readability 
        MIN_WRAPLENGTH = 450
        containerWidth = max(containerWidth, MIN_WRAPLENGTH)

        # Updates the wrap length of the title label inside the video info frame
        self.titleVideoInfo.configure(wraplength=containerWidth)
    
    
    """ Updates the editable audio information fields with new values """    
    def updateEditInfoAudio(self, title_video: str, artist_video: str, album_video: str):
        self.titleAudioVar.set(title_video)
        self.artistAudioVar.set(artist_video)
        self.albumAudioVar.set(album_video)
    
         
    """ Updates the video information display, including thumbnail and text fields """            
    def updateVideoInfo(self, album_thumbnail):
        self.clearVideoInfo()
        self.updateEditInfoAudio(self.title_video, self.artist_video, self.album_video)
        
        self.singleVideosFrame = ctk.CTkFrame(self.videoInfoFrame, fg_color="transparent")
        self.singleVideosFrame.grid(row=0, column=0, columnspan=2, rowspan=3, sticky='nsew', padx=self.padding, pady=self.padding)
        self.singleVideosFrame.grid_rowconfigure((0,3), weight=1)
        self.singleVideosFrame.grid_columnconfigure((1,3), weight=1)

        # Loads and processes the album thumbnail if available
        if album_thumbnail:
            try:
                u = urlopen(album_thumbnail)
                raw_data = u.read()
                self.image = ImageTk.PhotoImage(data=raw_data)
                
                response = requests.get(album_thumbnail)
                image_pil = Image.open(BytesIO(response.content)) 
                
                target_size = (200, 113)

                # Uses ImageOps.fit to crop and resize the image without distortion
                image_pil = ImageOps.fit(image_pil, target_size, Image.ANTIALIAS)
                        
                self.imageInsideVideoInfoFrame = ctk.CTkImage(light_image=image_pil, size=(200, 113))
                self.imageLabelInsideVideoInfoFrame = ctk.CTkLabel(self.singleVideosFrame, image=self.imageInsideVideoInfoFrame, text="")
            except Exception as e:
                self.displayMessage(f"Error loading thumbnail: {e}")
        
        else:
            self.imageLabelInsideVideoInfoFrame = ctk.CTkLabel(
                self.singleVideosFrame,
                text="No image available",
                width=200,
                height=113,
                fg_color="gray",
                text_color="white",
                corner_radius=8,
                font=("Arial", 12)
            )
            
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

        self.titleVideoInfo = ctk.CTkLabel(self.textInsideVideoInfoFrame, wraplength=450, textvariable=self.titleAudioVar, font=self.titleFont )
        self.titleVideoInfo.grid(row=0, column=0, sticky='w')
        self.titleVideoInfo.columnconfigure(0, weight=1)
        # Actualizar el wraplength dinámicamente después de mostrar el widget
        self.textInsideVideoInfoFrame.after(100, self.updateWraplength)
        
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
        
        # Loads and processes the album thumbnail if available
        if album_thumbnail:
            try:
                u = urlopen(album_thumbnail)
                raw_data = u.read()
                self.image = ImageTk.PhotoImage(data=raw_data)
                
                response = requests.get(album_thumbnail)
                image_pil = Image.open(BytesIO(response.content)) 
                target_size = (200, 113)
                
                # Uses ImageOps.fit to crop and resize the image without distortion
                image_pil = ImageOps.fit(image_pil, target_size, Image.ANTIALIAS)
                
                self.imageInsideVideoInfoFrame = ctk.CTkImage(light_image=image_pil, size=(200, 113))
                self.imageLabelInsideVideoInfoFrame = ctk.CTkLabel(self.videosFromPlaylistFrame, image=self.imageInsideVideoInfoFrame, text="")

            except Exception as e:
                self.displayMessage(f"Error al cargar el thumbnail: {e}")
        
        
        else:
            self.imageLabelInsideVideoInfoFrame = ctk.CTkLabel(
                self.videosFromPlaylistFrame,
                text="No image available",
                width=200,
                height=113,
                fg_color="gray",
                text_color="white",
                corner_radius=8,
                font=("Arial", 12)
            )
            
            self.videosFromPlaylistFrame.grid_rowconfigure(0, weight=0) 
            self.videosFromPlaylistFrame.grid_columnconfigure(0, weight=0) 
           
               
        self.root.geometry("750x700")
        self.imageLabelInsideVideoInfoFrame.grid(row=0, column=0, sticky='ew', padx=self.padding, pady=self.padding)
        
        frame_width = self.videosFromPlaylistFrame.winfo_width()

        self.textInsideVideoInfoFrame = ctk.CTkFrame(self.videosFromPlaylistFrame, fg_color="transparent")
        self.textInsideVideoInfoFrame.grid(row=0, column=1, columnspan=3, sticky='w', padx=self.padding, pady=self.padding)
        self.textInsideVideoInfoFrame.grid_columnconfigure(0, weight=1)
        self.textInsideVideoInfoFrame.grid_columnconfigure(1, weight=1)
        
        # Button to select the download destination folder
        self.editInfoButton = ctk.CTkButton(self.videosFromPlaylistFrame, text="Edit", command=self.editInfoPopUp, image=CTkImage(dark_image=self.editImg, light_image=self.editImg));
        self.editInfoButton.configure(fg_color="#191818", font=self.regularFont, height=33, width=40, hover_color="#FF4C58");
        self.editInfoButton.grid(row=0, column=3, sticky='ne')
        
        
        self.titleVideoInfo = ctk.CTkLabel(self.textInsideVideoInfoFrame, wraplength=450, textvariable=self.titleAudioVar, font=self.titleFont)
        self.titleVideoInfo.grid(row=0, column=0, sticky='w')
        self.titleVideoInfo.columnconfigure(0, weight=1)

        # Ancho del frame principal

        # Calcular el wraplength dinámico basado en el espacio disponible
        min_wraplength = 150  # Mínimo ancho permitido
        max_wraplength = 450  # Máximo ancho permitido
        available_width = frame_width - (2 * self.padding)  # Espacio total disponible
        calculated_wraplength = max(min_wraplength, min(available_width, max_wraplength))
        
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
                
                for i, video in enumerate(self.playlist_videos):
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
        
        self.root.geometry("750x280")    
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
    