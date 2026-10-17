## MP3Vault
**MP3Vault** is a desktop application that lets you effortlessly download music from YouTube and convert it to MP3 format. With this user-friendly app, you can access your favorite songs and build your personal offline music library with ease.

🚀 **MP3Vault** simplifies the process of downloading and converting music. Whether you want to save your favorite tracks for offline listening or create a personal collection, MP3Vault makes it quick and easy.

Get ready to enhance your music experience with **MP3Vault** – enjoy your favorite tunes anytime, anywhere! 🌟


<p align="center">
  <a href="#"><img src="https://github.com/user-attachments/assets/dc28ca26-e9b6-4765-a64e-af1ec6b53b2d"/></a>
</p>

<p align="center">
   <a href="#"><img src="https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54"/></a>
  <a href="#"><img src="https://img.shields.io/badge/YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white"/></a>
</p>


## Features 

- Easy Music Downloads
- MP3 Format Conversion
- User-Friendly Interface
- Personal Offline Music Library



## Limitations

This app is designed specifically for YouTube. It will not work on other websites or video platforms.

## Requirements

- **FFmpeg** installed with its folder on the `PATH` (e.g. `C:\ffmpeg`). For safety MP3Vault only uses an ffmpeg found in an absolute `PATH` folder (or bundled inside the .exe); it never runs an `ffmpeg.exe` from the current folder or from the folder the app sits in.

## Development setup

Dependencies are locked with exact versions and SHA-256 hashes (generated with [pip-tools](https://pip-tools.readthedocs.io/)):

```
python -m venv .venv
.venv\Scripts\activate
pip install --require-hashes -r requirements-dev.txt
python -m pytest
```

- `requirements.in` / `requirements-dev.in`: the direct dependencies you edit.
- `requirements.txt` / `requirements-dev.txt`: generated locks, don't edit by hand. Regenerate with the command at the top of each `.in` file, e.g. to pick up a new yt-dlp:
  ```
  python -m piptools compile --generate-hashes --allow-unsafe --strip-extras --upgrade-package yt-dlp -o requirements.txt requirements.in
  python -m piptools compile --generate-hashes --allow-unsafe --strip-extras -o requirements-dev.txt requirements-dev.in
  ```
- Check the locks for known vulnerabilities: `pip-audit -r requirements.txt --require-hashes`

The locks were generated on Windows with Python 3.11.

## Building the .exe

Packaged with [auto-py-to-exe](https://github.com/brentvollebregt/auto-py-to-exe) (a GUI for PyInstaller):

1. `pip install auto-py-to-exe`, then run `auto-py-to-exe`
2. Script Location: `app.py`
3. **Additional Files**: add `folder.png`, `editar.png`, and `icon.ico` (pointing to the bundle root, `.`)
4. Icon: `icon.ico` (sets the `.exe` icon in Windows Explorer)
5. **Advanced → Additional command line arguments**: add `--collect-data customtkinter`
   — without this the built `.exe` crashes on launch with `FileNotFoundError: ...customtkinter\assets\themes\blue.json`, since PyInstaller doesn't auto-detect customtkinter's own theme/font data files.
6. Convert — output lands in `output/`

Onefile and onedir both work; `resourcePath()` in `app.py` resolves assets correctly in either mode via `sys._MEIPASS`.

# Experiencing an Issue? ⚠️

Did you stumble upon a bug or encounter an issue while using **MP3Vault**? Your feedback is invaluable to us! Please report any [bugs or technical glitches](https://github.com/caladavid/MP3Vault/issues)  you encounter so we can swiftly address them and enhance your browsing experience. 

## Get in Touch! 📩

We'd love to hear from you! Whether you have a question, feedback, or just want to say hello, don't hesitate to reach out. Feel free to [contact me](https://github.com/caladavid) and let's connect!  

## Support & Contributions 🤲

#### [Star this project](https://github.com/caladavid/MP3Vault) ⭐️
