from tkinter import Tk, Label, Entry, Button, messagebox, Frame, filedialog
from tkinter.font import Font
from tkinter.filedialog import askopenfilename
from pytube import YouTube
from moviepy.video.io.VideoFileClip import VideoFileClip
from mutagen.easyid3 import EasyID3
from tkinter import ttk
from mutagen.id3 import ID3, APIC
from PIL import Image, ImageTk
import re
import sys
import os

root = Tk()
root.title("MP3Vault")
root.geometry("420x280")
root.resizable(0, 0)
root['bg'] = "#191818"

myFont = Font(size=12, font="bold")

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

#Icon
iconPath = resource_path('icon.ico')
root.iconbitmap(iconPath)

OUTPUT_PATH = os.path.join(os.path.expanduser("~"), "Music")
VALID_FILENAME_CHARS = r"[^\w\s\-'.()&,]|Official Audio| - Topic|official|video|Video|audio|Audio|Remaster|Remastered"

# Elimina caracteres especiales de un filename.
def cleanFilename(filename):
    return re.sub(VALID_FILENAME_CHARS, "", filename)


# Modificar los metadatos
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

# Verifica si hay un URL valido
def validateURL():
    url = urlInput.get()
    if url.startswith("https://www.youtube.com/watch?v=") or url.startswith("https://youtu.be/"):
        downloadBtn.config(state="normal")
    else:
        downloadBtn.config(state="disabled")


# Seleccionar carpeta de destino
def selectDownloadFolder():
    folder_path = filedialog.askdirectory()
    if folder_path:
        global OUTPUT_PATH
        OUTPUT_PATH = folder_path
        messagebox.showinfo("Folder Selected", f"{folder_path}")

def downloadAudio():
    try:
        # Choose the highest resolution video to download
        videoUrl = urlInput.get()
        getAlbum = albumInput.get()
        customFileName = audioNameInput.get()
        
        video = YouTube(videoUrl)

        # Obtiene la información necesaria del video
        title = cleanFilename(video.title)
        artist = cleanFilename(video.author)
        artist = cleanFilename(artist)
        album = getAlbum

        # Eliminar el nombre del artista del título
        title = re.sub(f"{artist}\s*-\s*", "", title, flags=re.IGNORECASE).strip()

        if customFileName:
            FilenameMP4 = cleanFilename(f"{customFileName}.mp4")
        else:
            FilenameMP4 = cleanFilename(f"{artist} - {title}.mp4")
        stream = video.streams.get_highest_resolution()

        videoFiles = stream.download(OUTPUT_PATH, filename=FilenameMP4)

        # Convertir el video descargado a mp3 con moviepy y guardar en la carpeta de salida
        videoStream = VideoFileClip(videoFiles)
        audio = videoStream.audio

        # Especificar el nombre del archivo de salida
        if customFileName:
            FilenameMP3 = cleanFilename(f"{customFileName}.mp3")
        else:
            FilenameMP3 = cleanFilename(f"{artist} - {title}.mp3")

        audio.write_audiofile(os.path.join(OUTPUT_PATH, FilenameMP3))

        # Actualizar los metadatos del archivo MP3
        updateMetadata(title, artist, album, FilenameMP3, OUTPUT_PATH, customFileName)

        # Liberar los recursos usados por moviepy
        videoStream.close()
        audio.close()

        os.remove(videoFiles)
        urlInput.delete(0, 'end')
        messagebox.showinfo("Download Success", f"{title} - Downloaded Successfully!!")

    except Exception as e:
        if 'StreamingData' in str(e):
            messagebox.showerror("Error", "Se ha producido un error. Actualice la biblioteca pytube e inténtelo de nuevo.")
        else:
            messagebox.showerror("Error", str(e))



# Etiqueta y entrada para la URL del video
headLabel = Label(root, text="Enter URL:")
headLabel.config(bg="#191818", fg="#FFFFFF", font=myFont)
headLabel.place(x=15, y=15)

urlInput = Entry(root)
urlInput.place(x=15, y=55, width=380, height=30)
urlInput.config(font=myFont)
urlInput.bind("<KeyRelease>", lambda _: validateURL())

# Botones de descarga e información
downloadFrame = Frame(root, height=50, width=75, highlightthickness=1, highlightbackground="#FF4C58")

downloadBtn = Button(downloadFrame, text="Download", command=downloadAudio, state="disabled")
downloadBtn.config(bg="#191818", fg="#FFFFFF", bd=0, padx=8, pady=3, font=myFont)
downloadBtn.pack()

downloadFrame.place(x=15, y=105)

downloadingLabel = Label(root, text="Downloading...", bg="#191818", fg="#FFFFFF", font=myFont)

### Botones de album ###

detailLabel = Label(root, text="Details")
detailLabel.config(bg="#191818", fg="#FFFFFF", font=myFont)
detailLabel.place(x=170, y=155, height=25)

# Album name
albumInput = Entry(root, highlightthickness=1.3)
albumInput.config(highlightcolor= "#FF4C58", font=myFont)
albumInput.place(x=125, y=230, height=25, width=270)
albumLabel = Label(root, text="Album Name:")
albumLabel.config(bg="#191818", fg="#FFFFFF", font=myFont)
albumLabel.place(x=15, y=230)

# Audio title
audioNameInput = Entry(root, highlightthickness=1.3)
audioNameInput.config(highlightcolor= "#FF4C58", font=myFont)
audioNameInput.place(x=125, y=195, height=25, width=270)
audioNameLabel = Label(root, text="Audio Title:")
audioNameLabel.config(bg="#191818", fg="#FFFFFF", font=myFont)
audioNameLabel.place(x=15, y=195)

# Botones para seleccionar carpeta de destino
folderButton = Button(root, text="Choose Folder", command=selectDownloadFolder)
folderButton.config(bg="#191818", fg="#FFFFFF", padx=8, pady=3, font=myFont)
folderButton.place(x=125, y=105)

root.mainloop() 
