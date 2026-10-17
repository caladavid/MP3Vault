import pytest

from core import naming


@pytest.mark.parametrize("title, expected", [
    ("Song (Official Audio)", "Song"),
    ("Song (video)", "Song"),
    ("Song (Video)", "Song"),
    ("Song (Remastered)", "Song"),
    ('a: b? <c> | "d" *', "a b c  d"),
    ("Rock & Roll, Pt. 2", "Rock & Roll, Pt. 2"),
    ("  spaced  ", "spaced"),
])
def test_clean_filename(title, expected):
    assert naming.clean_filename(title) == expected


@pytest.mark.parametrize("uploader, expected", [
    ("Artist - Topic", "Artist"),
    ("Artist - VEVO", "Artist"),
    ("Artist - Official", "Artist"),
    ("Plain Artist", "Plain Artist"),
])
def test_clean_uploader(uploader, expected):
    assert naming.clean_uploader(uploader) == expected


def test_build_filename_basic():
    cleanTitle, filename = naming.build_clean_title_and_filename("Bad Bunny", "DtMF (Official Audio)", "mp3")
    assert cleanTitle == "DtMF"
    assert filename == "Bad Bunny - DtMF.mp3"


def test_build_filename_dedupes_uploader_prefix():
    _, filename = naming.build_clean_title_and_filename("A", "A - A - Song", "m4a")
    assert filename == "A - Song.m4a"


def test_build_filename_slash_in_artist_is_not_a_subfolder():
    # Regression: raw "AC/DC" used to create C:\dl\AC\ and duplicate the artist
    _, filename = naming.build_clean_title_and_filename("AC/DC", "AC/DC - Thunderstruck", "mp3")
    assert filename == "ACDC - Thunderstruck.mp3"


@pytest.mark.parametrize("uploader", [r"..\..\Startup\evil", "../../etc/evil", "Artist: Live", 'a<b>c|d?e*"f'])
def test_build_filename_never_contains_path_or_stream_chars(uploader):
    _, filename = naming.build_clean_title_and_filename(uploader, "x", "mp3")
    for char in '\\/:*?"<>|':
        assert char not in filename


def test_playlist_prediction_matches_rename():
    # The already-downloaded check and the real rename must produce the same name
    rawTitle = "Peso Pluma - BELLAKEO (Video Oficial)"
    predicted = naming.predict_playlist_filename("Peso Pluma", rawTitle, "mp3")
    assert predicted == naming.playlist_filename("Peso Pluma", rawTitle, "mp3")
    assert predicted == "Peso Pluma - BELLAKEO (Video Oficial).mp3"


def test_safe_join_accepts_plain_name(tmp_path):
    assert naming.safe_join(str(tmp_path), "song.mp3") == str((tmp_path / "song.mp3").resolve())


@pytest.mark.parametrize("filename", [r"..\x.mp3", "../x.mp3", "sub/x.mp3", r"sub\x.mp3"])
def test_safe_join_rejects_escapes_and_subfolders(tmp_path, filename):
    with pytest.raises(ValueError):
        naming.safe_join(str(tmp_path), filename)


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=jNQXAC9IVRw",
    "http://youtube.com/watch?v=jNQXAC9IVRw",
    "https://m.youtube.com/watch?v=jNQXAC9IVRw",
    "https://music.youtube.com/watch?v=jNQXAC9IVRw",
    "https://youtu.be/jNQXAC9IVRw",
    "https://www.youtube.com/shorts/jNQXAC9IVRw",
])
def test_video_url_accepted(url):
    assert naming.YOUTUBE_VIDEO_URL_RE.match(url).group("id") == "jNQXAC9IVRw"


@pytest.mark.parametrize("url", [
    "https://evil.com/youtu.be/jNQXAC9IVRw",
    "https://youtube.com.evil.com/watch?v=jNQXAC9IVRw",
    "ftp://youtu.be/jNQXAC9IVRw",
    "youtu.be/jNQXAC9IVRw",
])
def test_video_url_rejected(url):
    assert naming.YOUTUBE_VIDEO_URL_RE.match(url) is None


def test_playlist_url():
    assert naming.YOUTUBE_PLAYLIST_URL_RE.match("https://music.youtube.com/playlist?list=PL123")
    assert not naming.YOUTUBE_PLAYLIST_URL_RE.match("https://youtu.be/jNQXAC9IVRw")
