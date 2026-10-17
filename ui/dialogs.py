import customtkinter as ctk

from ui import theme


""" Popup to edit the title/artist/album that will be used for the file name and tags.
`on_confirm(title, artist, album)` is called when the user presses Confirm. """
class EditInfoDialog:
    def __init__(self, parent, font, title: str, artist: str, album: str, on_confirm):
        self.on_confirm = on_confirm
        self.window = ctk.CTkToplevel(parent)
        self.window.geometry("410x250")
        self.window.title("Edit audio details")

        # StringVars scoped to this popup, seeded from the current values — NOT the long-lived
        # vars the main window's labels use. CTkEntry never removes its internal trace on its
        # textvariable when destroyed, so binding these entries directly to the long-lived vars
        # left a dangling trace on every popup open/close that later crashed with
        # `_tkinter.TclError: invalid command name` the next time a new video loaded.
        self.titleVar = ctk.StringVar(value=title)
        self.artistVar = ctk.StringVar(value=artist)
        self.albumVar = ctk.StringVar(value=album)

        frame = ctk.CTkFrame(self.window, fg_color="transparent")
        frame.grid(row=0, column=0, sticky='nsew', padx=theme.PADDING, pady=theme.PADDING)
        frame.columnconfigure((0, 3), weight=1)

        headLabel = ctk.CTkLabel(frame, text="Edit details")
        headLabel.grid(row=0, column=1)
        headLabel.configure(text_color=theme.TEXT_COLOR, font=font, padx=1, pady=1)

        for row, (label, variable) in enumerate([("Title", self.titleVar), ("Artist", self.artistVar), ("Album", self.albumVar)], start=1):
            fieldLabel = ctk.CTkLabel(frame, text=label)
            fieldLabel.configure(text_color=theme.TEXT_COLOR, font=font, pady=1)
            fieldLabel.grid(row=row, column=0, sticky='nsew', padx=(0, 10))

            entry = ctk.CTkEntry(frame, textvariable=variable)
            entry.grid(row=row, column=1, pady=10, sticky='nsew')
            entry.configure(font=font, text_color=theme.ENTRY_TEXT_COLOR, fg_color=theme.ENTRY_COLOR, width=300, height=30)

        confirmButton = ctk.CTkButton(frame, text="Confirm", command=self.confirm)
        confirmButton.grid(row=4, column=1, pady=2)
        confirmButton.configure(fg_color=theme.BUTTON_COLOR, font=font, height=35, width=80, hover_color=theme.ACCENT_COLOR)

    def exists(self):
        return self.window.winfo_exists()

    def lift(self):
        self.window.lift()

    def confirm(self):
        self.on_confirm(self.titleVar.get(), self.artistVar.get(), self.albumVar.get())
        self.window.destroy()


""" Popup for pasting several video URLs (one per line). `on_submit(text)` receives the raw text;
the caller validates it and calls close() once the queue is accepted. """
class QueueDialog:
    def __init__(self, parent, font, on_submit):
        self.window = ctk.CTkToplevel(parent)
        self.window.title("Add multiple URLs")
        self.window.geometry("420x300")

        label = ctk.CTkLabel(self.window, text="Paste one YouTube video URL per line:")
        label.configure(text_color=theme.TEXT_COLOR, font=font)
        label.grid(row=0, column=0, padx=20, pady=(20, 5), sticky='w')

        self.textbox = ctk.CTkTextbox(self.window, width=380, height=180)
        self.textbox.grid(row=1, column=0, padx=20, pady=5)

        downloadButton = ctk.CTkButton(self.window, text="Download All", command=lambda: on_submit(self.text()))
        downloadButton.configure(fg_color=theme.BUTTON_COLOR, font=font, height=35, hover_color=theme.ACCENT_COLOR)
        downloadButton.grid(row=2, column=0, pady=(10, 20))

    def text(self):
        return self.textbox.get("1.0", "end")

    def exists(self):
        return self.window.winfo_exists()

    def lift(self):
        self.window.lift()

    def close(self):
        self.window.destroy()
