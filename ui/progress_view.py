import customtkinter as ctk

from core.models import Progress
from ui import theme


""" Progress bar + labels + Cancel button shown while a download runs. Created fresh per download
inside the video-info area and destroyed afterwards, so "Cancel visible only during an active
download" comes for free. Every method is safe to call after the view was destroyed (late
progress updates do arrive then, e.g. after a new URL was loaded; verified TclError before). """
class ProgressView:
    def __init__(self, parent, font, on_cancel):
        self.progressVar = ctk.DoubleVar()

        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.grid(row=0, column=1, columnspan=4, sticky="nsew", padx=10, pady=10)
        for column in (1, 2, 3, 4):
            self.frame.grid_columnconfigure(column, weight=1)

        self.label = ctk.CTkLabel(self.frame, text="Downloading...")
        self.label.grid(row=0, column=0, pady=5, columnspan=5)

        self.bar = ctk.CTkProgressBar(self.frame, variable=self.progressVar)
        self.bar.grid(row=1, column=0, sticky="ew", padx=10, pady=10, columnspan=5)
        self.bar.set(0)

        self.speedLabel = ctk.CTkLabel(self.frame, text="Speed: - ETA: -")
        self.speedLabel.grid(row=2, column=0, pady=5, columnspan=5)

        self.cancelButton = ctk.CTkButton(self.frame, text="Cancel", command=on_cancel)
        self.cancelButton.configure(fg_color=theme.BUTTON_COLOR, font=font, height=30, width=100, hover_color=theme.ACCENT_COLOR)
        self.cancelButton.grid(row=3, column=0, pady=(5, 0), columnspan=5)

    def alive(self):
        return self.frame.winfo_exists()

    def update(self, progress: Progress):
        if not self.alive():
            return

        title = progress.title
        if progress.playlist_index is not None:
            title = f"{title} ({progress.playlist_index}/{progress.playlist_count or '?'})"

        if progress.status == 'downloading':
            self.progressVar.set(progress.fraction)
            self.label.configure(text=f"Descargando: {title}")
            self.speedLabel.configure(text=f"Velocidad: {progress.speed} - ETA: {progress.eta}")
        elif progress.status == 'finished':
            self.progressVar.set(1)
            self.label.configure(text=f"Descarga completada: {title}")
            self.speedLabel.configure(text="¡Completado!")

    def set_text(self, text: str):
        if self.alive():
            self.label.configure(text=text)

    """ Disables Cancel right away so a second click can't fire while the worker unwinds """
    def set_cancelling(self):
        if self.alive():
            self.cancelButton.configure(state="disabled", text="Cancelling...")

    def destroy(self):
        if self.alive():
            self.frame.destroy()
