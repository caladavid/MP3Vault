import re
import sys
import os
from tkinter import Tk, Label, Entry, Button, messagebox, Frame, filedialog
from tkinter.font import Font
from pytube import YouTube
from pytube import Playlist
from moviepy.video.io.VideoFileClip import VideoFileClip
from mutagen.easyid3 import EasyID3
from idlelib.tooltip import Hovertip

# Create the main application window
root = Tk()
root.title("MP3Vault")
root.geometry("420x280")
root.resizable(0, 0)
root['bg'] = "#191818"

# Welcome message
print("Welcome to MP3Vault!")
print("Get started by entering a YouTube URL below.\n")

# Print information about the application's creator and GitHub repository
print("MP3Vault - Created by David Cala")
print("Version 1.1")
print("GitHub Repository: https://github.com/caladavid/MP3Vault\n")


# Set the custom font
myFont = Font(size=12, font="bold")

# Get absolute path to resource, works for dev and for PyInstaller
def resource_path(relative_path):
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# Set the application icon
iconPath = resource_path('icon.ico')
root.iconbitmap(iconPath)

# Set the default output path for downloaded files
#OUTPUT_PATH = os.path.join(os.path.expanduser("~"), "Music")

# Define a regular expression pattern to clean filenames
VALID_FILENAME_CHARS = r"[^\w\s\-'.()&,]|Official Audio| - Topic|official|video|Video|audio|Audio|Remaster|Remastered"

# Clean a filename by removing special characters based on a regex pattern
def cleanFilename(filename):
    return re.sub(VALID_FILENAME_CHARS, "", filename)

# Update metadata for an MP3 file
def updateMetadata(title, artist, album, FilenameMP3, OUTPUT_PATH, customFileName=None):
    filePath = os.path.join(OUTPUT_PATH, FilenameMP3)
    audioMetadata = EasyID3(filePath)

    if customFileName:
        audioMetadata['title'] = customFileName
    else:
        audioMetadata['title'] = title
        
    audioMetadata['artist'] = artist
    audioMetadata['albumartist'] = artist
    audioMetadata['album'] = album
    audioMetadata.save()

# Check if a URL is valid and enable corresponding download buttons
def validateURL():
    url = urlInput.get()
    if url.startswith("https://www.youtube.com/watch?v=") or url.startswith("https://youtu.be/"):
        downloadBtn.config(state="normal")
    elif url.startswith("https://www.youtube.com/playlist"):
        downloadPlaylistBtn.config(state="normal")
    else:
        downloadBtn.config(state="disabled")
        downloadPlaylistBtn.config(state="disabled")


# Open a folder dialog to select the download destination folder
def selectDownloadFolder():
    folder_path = filedialog.askdirectory()
    if folder_path:
        global OUTPUT_PATH
        OUTPUT_PATH = folder_path
        messagebox.showinfo("Folder Selected", f"{folder_path}")

# Get video information like title, artist, and album
def getVideoInfo(video):
    title = cleanFilename(video.title)
    artist = cleanFilename(video.author)
    artist = cleanFilename(artist)
    album = albumInput.get()
    title = re.sub(f"{artist}\s*-\s*", "", title, flags=re.IGNORECASE).strip()
    return title, artist, album

# Generate filenames for video and audio files
def generateFilenames(video, customFileName):
    title = cleanFilename(video.title)
    artist = cleanFilename(video.author)
    artist = cleanFilename(artist)

    if customFileName:
        FilenameMP4 = cleanFilename(f"{customFileName}.mp4")
        FilenameMP3 = cleanFilename(f"{customFileName}.mp3")
    else:
        FilenameMP4 = cleanFilename(f"{artist} - {title}.mp4")
        FilenameMP3 = cleanFilename(f"{artist} - {title}.mp3")

    return FilenameMP4, FilenameMP3

# Download and convert a single video to MP3
def downloadAudio():
    try:
        videoUrl = urlInput.get()
        album = albumInput.get()
        customFileName = audioNameInput.get()

        video = YouTube(videoUrl)
        title, artist, album = getVideoInfo(video)

        FilenameMP4, FilenameMP3 = generateFilenames(video, customFileName)

        stream = video.streams.get_highest_resolution()
        videoFiles = stream.download(OUTPUT_PATH, filename=FilenameMP4)

        # Convert the downloaded video to MP3 using moviepy and save to the output folder
        videoStream = VideoFileClip(videoFiles)
        audio = videoStream.audio

        audio.write_audiofile(os.path.join(OUTPUT_PATH, FilenameMP3))

        # Update metadata for the MP3 file
        updateMetadata(title, artist, album, FilenameMP3, OUTPUT_PATH, customFileName)

        # Release resources used by moviepy
        videoStream.close()
        audio.close()

        # Remove the downloaded video file
        os.remove(videoFiles)

         # Clear the URL input field
        urlInput.delete(0, 'end')

        # Show a success message
        messagebox.showinfo("Download Success", f"{title} - Downloaded Successfully")

    except Exception as e:
        if 'StreamingData' in str(e):
            messagebox.showerror("Error", "Se ha producido un error. Actualice la biblioteca pytube e inténtelo de nuevo.")
        else:
            messagebox.showerror("Error", str(e))

# Download and convert all videos in a YouTube playlist to MP3
def downloadPlaylist():
    try:
        playlistUrl = urlInput.get()
        album = albumInput.get()
        customFileName = audioNameInput.get()

        playlist = Playlist(playlistUrl)

        for video in playlist.videos:
            title, artist, album = getVideoInfo(video)
            FilenameMP4, FilenameMP3 = generateFilenames(video, customFileName)

            stream = video.streams.get_highest_resolution()
            videoFiles = stream.download(OUTPUT_PATH, filename=FilenameMP4)

            videoStream = VideoFileClip(videoFiles)
            audio = videoStream.audio

            audio.write_audiofile(os.path.join(OUTPUT_PATH, FilenameMP3))

            # Update metadata for the MP3 file (you may need to customize this part for playlists)
            updateMetadata(title, artist, album, FilenameMP3, OUTPUT_PATH, customFileName)
            videoStream.close()
            audio.close()
            os.remove(videoFiles)

        urlInput.delete(0, 'end')
        messagebox.showinfo("Download Success", f"{playlist.title} Downloaded Successfully")

    except Exception as e:
        if 'StreamingData' in str(e):
            messagebox.showerror("Error", "An error occurred. Please update the pytube library and try again.")
        else:
            messagebox.showerror("Error", str(e))


### Label and entry for the video URL ###
headLabel = Label(root, text="Enter URL:")
headLabel.config(bg="#191818", fg="#FFFFFF", font=myFont)
headLabel.place(x=15, y=15)

urlInput = Entry(root)
urlInput.place(x=15, y=55, width=380, height=30)
urlInput.config(font=myFont)
urlInput.bind("<KeyRelease>", lambda _: validateURL())

# Download and information buttons
downloadFrame = Frame(root, height=50, width=75, highlightthickness=1, highlightbackground="#FF4C58")
downloadPlaylistFrame = Frame(root, height=50, width=75, highlightthickness=1, highlightbackground="#FF4C58")

downloadBtn = Button(downloadFrame, text="Download", command=downloadAudio, state="disabled")
downloadBtn.config(bg="#191818", fg="#FFFFFF", bd=0, padx=8, pady=3, font=myFont)
downloadBtn.pack()

downloadPlaylistBtn = Button(downloadPlaylistFrame, text="Download", command=downloadPlaylist, state="disabled")
downloadPlaylistBtn.config(bg="#191818", fg="#FFFFFF", bd=0, padx=8, pady=3, font=myFont)
downloadPlaylistBtn.pack()

audioTip = Hovertip(downloadBtn,'Download an audio.')
playlistTip = Hovertip(downloadPlaylistBtn,'Download a playlist.')

downloadFrame.place(x=15, y=105)
downloadPlaylistFrame.place(x=300, y=105)

downloadingLabel = Label(root, text="Downloading...", bg="#191818", fg="#FFFFFF", font=myFont)

### Album details section ###

detailLabel = Label(root, text="Details")
detailLabel.config(bg="#191818", fg="#FFFFFF", font=myFont)
detailLabel.place(x=170, y=155, height=25)

# Album name input
albumInput = Entry(root, highlightthickness=1.3)
albumInput.config(highlightcolor= "#FF4C58", font=myFont)
albumInput.place(x=125, y=230, height=25, width=270)
albumLabel = Label(root, text="Album Name:")
albumLabel.config(bg="#191818", fg="#FFFFFF", font=myFont)
albumLabel.place(x=15, y=230)

# Audio title input
audioNameInput = Entry(root, highlightthickness=1.3)
audioNameInput.config(highlightcolor= "#FF4C58", font=myFont)
audioNameInput.place(x=125, y=195, height=25, width=270)
audioNameLabel = Label(root, text="Audio Title:")
audioNameLabel.config(bg="#191818", fg="#FFFFFF", font=myFont)
audioNameLabel.place(x=15, y=195)

# Button to select the download destination folder
folderButton = Button(root, text="Choose Folder", command=selectDownloadFolder)
folderButton.config(bg="#191818", fg="#FFFFFF", padx=8, pady=3, font=myFont)
folderButton.place(x=140, y=105)

# Start the main application loop
root.mainloop() 