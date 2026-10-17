import logging
import threading

import customtkinter as ctk

from core import thumbnail
from ui import theme


log = logging.getLogger(__name__)

# Window width is fixed at 750 and never resizes (root.resizable(0, 0)), so the space actually
# left for the title after the 200px thumbnail, fixed paddings, and the Edit button is a
# constant too — measured directly from the real widget tree.
# CTkLabel needs wraplength AND width set to the same value: wraplength alone still leaves the
# widget's own canvas at its small default size, and grid can silently shrink a too-large width
# to fit its column — either mismatch clips the wrapped text instead of showing it in full.
TITLE_WRAPLENGTH_SINGLE = 340    # single-video view: Edit button shares the same inner frame
TITLE_WRAPLENGTH_PLAYLIST = 385  # playlist view: Edit button lives in a separate outer column
PLAYLIST_TITLE_MAX_CHARS = 80


""" Gray box shown until the thumbnail arrives (or permanently, if there is none) """
def thumbnail_placeholder(parent, thumbnail_url):
    return ctk.CTkLabel(
        parent,
        text="Loading image..." if thumbnail_url else "No image available",
        width=thumbnail.THUMBNAIL_SIZE[0],
        height=thumbnail.THUMBNAIL_SIZE[1],
        fg_color="gray",
        text_color="white",
        corner_radius=8,
        font=("Arial", 12)
    )


""" Fetches the thumbnail off the Tk main thread so a slow host can't freeze the window, then
hands the result back through `post` (the main window's UI queue). The label may already be gone
by then (user pasted a new URL meanwhile), so it is checked before being touched. """
def load_thumbnail_async(url: str, label, post):
    def worker():
        try:
            image_pil = thumbnail.fetch_thumbnail(url)
        except Exception as e:
            log.warning("Thumbnail failed for %s: %s", url, e)
            image_pil = None
        post(apply_result, image_pil)

    def apply_result(image_pil):
        if not label.winfo_exists():
            return
        if image_pil is None:
            label.configure(text="No image available")
            return
        # Kept on the label so Tk doesn't garbage-collect the image while it's displayed
        label.ctkImage = ctk.CTkImage(light_image=image_pil, size=thumbnail.THUMBNAIL_SIZE)
        label.configure(image=label.ctkImage, text="", fg_color="transparent")

    threading.Thread(target=worker, daemon=True).start()


""" Title/artist/album labels bound to the main window's StringVars (so edits show up live) """
def _info_labels(parent, variables, fonts, wraplength):
    titleVar, artistVar, albumVar = variables
    titleLabel = ctk.CTkLabel(parent, width=wraplength, wraplength=wraplength, anchor='w', justify='left', textvariable=titleVar, font=fonts.title)
    titleLabel.grid(row=0, column=0, sticky='w')
    titleLabel.columnconfigure(0, weight=1)

    ctk.CTkLabel(parent, textvariable=artistVar, font=fonts.regular).grid(row=1, column=0, sticky='w')
    ctk.CTkLabel(parent, textvariable=albumVar, font=fonts.regular).grid(row=2, column=0, sticky='w')


def _edit_button(parent, fonts, edit_image, on_edit):
    button = ctk.CTkButton(parent, text="Edit", command=on_edit, image=ctk.CTkImage(dark_image=edit_image, light_image=edit_image))
    button.configure(fg_color=theme.BUTTON_COLOR, font=fonts.regular, height=33, width=40, hover_color=theme.ACCENT_COLOR)
    return button


""" Thumbnail + title/artist/album + Edit button for one video """
class SingleVideoView:
    def __init__(self, parent, variables, fonts, edit_image, on_edit, thumbnail_url, post):
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.grid(row=0, column=0, columnspan=2, rowspan=3, sticky='nsew', padx=theme.PADDING, pady=theme.PADDING)
        self.frame.grid_rowconfigure((0, 3), weight=1)
        self.frame.grid_columnconfigure((1, 3), weight=1)

        self.thumbnailLabel = thumbnail_placeholder(self.frame, thumbnail_url)
        if thumbnail_url:
            load_thumbnail_async(thumbnail_url, self.thumbnailLabel, post)
        self.thumbnailLabel.grid(row=0, column=0, sticky='w', padx=(theme.PADDING, 0), pady=theme.PADDING)

        textFrame = ctk.CTkFrame(self.frame, fg_color="transparent")
        textFrame.grid(row=0, column=1, columnspan=3, padx=theme.PADDING, pady=theme.PADDING, sticky='ew')
        textFrame.grid_columnconfigure(0, weight=1)
        textFrame.grid_columnconfigure(1, weight=1)
        textFrame.grid_rowconfigure((0, 2), weight=1)

        _edit_button(textFrame, fonts, edit_image, on_edit).grid(row=2, column=3, sticky='se')
        _info_labels(textFrame, variables, fonts, TITLE_WRAPLENGTH_SINGLE)


""" Playlist header (thumbnail, title/artist/album, Edit) plus one checkbox per video and a
Select/Deselect-all toggle. `videos` come from ytdl.extract_playlist_videos. """
class PlaylistView:
    def __init__(self, parent, variables, fonts, edit_image, on_edit, thumbnail_url, post, videos):
        self.videos = videos
        self.checkbox_states = []
        self.fonts = fonts

        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.grid(row=0, column=0, columnspan=2, rowspan=3, sticky='nsew', padx=theme.PADDING, pady=theme.PADDING)
        self.frame.grid_rowconfigure((0, 3), weight=1)
        self.frame.grid_columnconfigure((1, 3), weight=1)

        self.thumbnailLabel = thumbnail_placeholder(self.frame, thumbnail_url)
        if thumbnail_url:
            load_thumbnail_async(thumbnail_url, self.thumbnailLabel, post)
        else:
            self.frame.grid_rowconfigure(0, weight=0)
            self.frame.grid_columnconfigure(0, weight=0)
        self.thumbnailLabel.grid(row=0, column=0, sticky='ew', padx=theme.PADDING, pady=theme.PADDING)

        textFrame = ctk.CTkFrame(self.frame, fg_color="transparent")
        textFrame.grid(row=0, column=1, columnspan=3, sticky='w', padx=theme.PADDING, pady=theme.PADDING)
        textFrame.grid_columnconfigure(0, weight=1)
        textFrame.grid_columnconfigure(1, weight=1)

        _edit_button(self.frame, fonts, edit_image, on_edit).grid(row=0, column=3, sticky='ne')
        _info_labels(textFrame, variables, fonts, TITLE_WRAPLENGTH_PLAYLIST)

        self.listFrame = ctk.CTkScrollableFrame(self.frame)
        self.listFrame.grid(row=4, column=0, rowspan=2, columnspan=4, sticky='nsew', padx=theme.PADDING, pady=theme.PADDING)
        for column in (1, 2, 3):
            self.listFrame.columnconfigure(column, weight=1)
        self.listFrame.rowconfigure(0, weight=1)

        separator = ctk.CTkFrame(self.frame, height=2, fg_color="gray")
        separator.grid(row=3, column=0, columnspan=4, sticky="new", pady=5)

        self.loadingLabel = ctk.CTkLabel(self.listFrame, text="Loading...", font=fonts.regular)
        self.loadingLabel.grid(row=0, column=0, sticky="w", padx=theme.PADDING, pady=theme.PADDING)

        self.masterVar = ctk.BooleanVar(value=True)
        self.masterCheckbox = ctk.CTkCheckBox(self.frame, text="Deselect All", command=self.toggle_all, variable=self.masterVar)
        self.masterCheckbox.grid(row=3, column=0, sticky="s")

        # Build the (possibly long) list after 500ms so the header shows up first
        self.listFrame.after(500, self._load_videos)

    def _load_videos(self):
        if not self.listFrame.winfo_exists():
            return
        if not self.videos:
            self.loadingLabel.configure(text="No se encontraron videos")
            return

        self.loadingLabel.destroy()
        for i, video in enumerate(self.videos, start=1):
            title = video['title']
            if len(title) > PLAYLIST_TITLE_MAX_CHARS:
                title = title[:PLAYLIST_TITLE_MAX_CHARS] + "..."

            state = ctk.BooleanVar(value=True)
            self.checkbox_states.append(state)
            ctk.CTkLabel(self.listFrame, text=f"{i}.", font=self.fonts.regular).grid(row=i, column=0, sticky="w", padx=10, pady=5)
            ctk.CTkCheckBox(self.listFrame, text=title, variable=state).grid(row=i, column=1, sticky="w")

        self.masterVar.set(True)

    """ Toggles all checkboxes based on the state of the master checkbox """
    def toggle_all(self):
        newState = self.masterVar.get()
        for state in self.checkbox_states:
            state.set(newState)
        self.masterCheckbox.configure(text="Deselect All" if newState else "Select All")

    """ The videos whose checkbox is ticked (empty until the list finished loading) """
    def selected_videos(self):
        return [video for video, state in zip(self.videos, self.checkbox_states) if state.get()]
