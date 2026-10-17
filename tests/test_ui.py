import types

import pytest

ctk = pytest.importorskip("customtkinter")

from PIL import Image

from core.models import Progress
from ui.dialogs import EditInfoDialog, QueueDialog
from ui.progress_view import ProgressView
from ui.video_views import PlaylistView, SingleVideoView


@pytest.fixture(scope="module")
def root():
    try:
        window = ctk.CTk()
    except Exception as e:  # no display (e.g. headless CI)
        pytest.skip(f"Tk not available: {e}")
    window.withdraw()
    yield window
    window.destroy()


@pytest.fixture
def parent(root):
    frame = ctk.CTkFrame(root)
    frame.grid()
    yield frame
    frame.destroy()


def _settle(root, ms=700):
    # PlaylistView builds its list 500ms after creation
    for _ in range(ms // 20):
        root.update()
        root.after(20)


def _fonts():
    return types.SimpleNamespace(regular=ctk.CTkFont(size=14), title=ctk.CTkFont(size=16))


def _vars(root):
    return tuple(ctk.StringVar(root, value=v) for v in ("Title", "Artist", "Album"))


EDIT_IMAGE = Image.new("RGBA", (16, 16))


def test_playlist_view_selection_and_toggle(root, parent):
    videos = [{'title': 'A', 'playlistIndex': 1}, {'title': 'C', 'playlistIndex': 3}, {'title': 'x' * 100, 'playlistIndex': 4}]
    view = PlaylistView(parent, _vars(root), _fonts(), EDIT_IMAGE, lambda: None, None, lambda fn, *a: fn(*a), videos)
    assert view.selected_videos() == []          # list not built yet
    _settle(root)

    assert view.selected_videos() == videos      # everything ticked by default
    view.checkbox_states[0].set(False)
    assert view.selected_videos() == videos[1:]

    view.masterVar.set(False)
    view.toggle_all()
    assert view.selected_videos() == []
    assert view.masterCheckbox.cget("text") == "Select All"


def test_playlist_view_without_videos(root, parent):
    view = PlaylistView(parent, _vars(root), _fonts(), EDIT_IMAGE, lambda: None, None, lambda fn, *a: fn(*a), [])
    _settle(root)
    assert view.loadingLabel.cget("text") == "No se encontraron videos"


def test_playlist_view_destroyed_before_list_loads(root, parent):
    view = PlaylistView(parent, _vars(root), _fonts(), EDIT_IMAGE, lambda: None, None, lambda fn, *a: fn(*a), [{'title': 'A', 'playlistIndex': 1}])
    view.frame.destroy()
    _settle(root)   # the delayed list build must not raise on destroyed widgets
    assert view.checkbox_states == []


def test_single_view_shows_placeholder_without_thumbnail(root, parent):
    view = SingleVideoView(parent, _vars(root), _fonts(), EDIT_IMAGE, lambda: None, None, lambda fn, *a: fn(*a))
    assert view.thumbnailLabel.cget("text") == "No image available"


def test_edit_dialog_reports_values_and_closes(root):
    received = []
    dialog = EditInfoDialog(root, ctk.CTkFont(size=14), "T", "A", "B", on_confirm=lambda *v: received.append(v))
    dialog.titleVar.set("New title")
    dialog.confirm()
    assert received == [("New title", "A", "B")]
    assert not dialog.exists()


def test_queue_dialog_text(root):
    submitted = []
    dialog = QueueDialog(root, ctk.CTkFont(size=14), on_submit=submitted.append)
    dialog.textbox.insert("1.0", "url1\nurl2")
    assert dialog.text().split() == ["url1", "url2"]
    dialog.close()
    assert not dialog.exists()


def test_progress_view_updates_and_survives_destroy(root, parent):
    view = ProgressView(parent, ctk.CTkFont(size=14), on_cancel=lambda: None)
    view.update(Progress("downloading", 0.4, "1MiB/s", "0:03", "Song", playlist_index=2, playlist_count=5))
    assert view.label.cget("text") == "Descargando: Song (2/5)"
    assert view.progressVar.get() == pytest.approx(0.4)

    view.set_cancelling()
    assert view.cancelButton.cget("text") == "Cancelling..."

    view.destroy()
    # late updates after destroy must be ignored, not raise TclError
    view.update(Progress("finished", 1.0, "-", "N/A", "Song"))
    view.set_text("x")
    view.set_cancelling()
    view.destroy()
