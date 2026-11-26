import json
import shutil
import subprocess
import sys

import pytest

from backend import shortcut
from backend.settings import APP_DIR

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows shortcuts")


def read_lnk(lnk):
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:PQ_LNK); "
        "@{target=$s.TargetPath; workdir=$s.WorkingDirectory; icon=$s.IconLocation} | ConvertTo-Json"
    )
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env={**__import__("os").environ, "PQ_LNK": str(lnk)},
        capture_output=True,
        check=True,
    )
    return json.loads(out.stdout)


def make_app(folder):
    folder.mkdir(parents=True)
    shutil.copy(APP_DIR / "Start.bat", folder / "Start.bat")
    shutil.copy(APP_DIR / "converter.ico", folder / "converter.ico")
    return folder


def test_desktop_dir_is_resolved():
    desktop = shortcut.desktop_dir()
    assert desktop is not None and desktop.is_dir()


def test_created_once_and_points_at_start_bat(tmp_path):
    app = make_app(tmp_path / "Loh Bao Zhi" / "ParquetConverter")
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    marker = tmp_path / "data" / "desktop-shortcut.json"

    msg = shortcut.ensure_desktop_shortcut(app, marker, desktop)
    lnk = desktop / shortcut.SHORTCUT_NAME
    assert msg and "Created" in msg and lnk.exists()
    info = read_lnk(lnk)
    assert info["target"].lower() == str(app / "Start.bat").lower()
    assert info["workdir"].lower() == str(app).lower()
    assert info["icon"].lower() == f"{app / 'converter.ico'},0".lower()

    # Second launch: nothing to do.
    assert shortcut.ensure_desktop_shortcut(app, marker, desktop) is None

    # User deleted it: not recreated.
    lnk.unlink()
    assert shortcut.ensure_desktop_shortcut(app, marker, desktop) is None
    assert not lnk.exists()


def test_moved_folder_updates_shortcut(tmp_path):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    marker = tmp_path / "data" / "desktop-shortcut.json"
    old = make_app(tmp_path / "old" / "ParquetConverter")
    new = make_app(tmp_path / "new" / "ParquetConverter")

    shortcut.ensure_desktop_shortcut(old, marker, desktop)
    msg = shortcut.ensure_desktop_shortcut(new, marker, desktop)
    assert msg and "Updated" in msg
    assert read_lnk(desktop / shortcut.SHORTCUT_NAME)["target"].lower() == str(new / "Start.bat").lower()


def test_failure_never_raises(tmp_path, monkeypatch):
    app = make_app(tmp_path / "app")
    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    def blocked(*args, **kwargs):
        raise OSError("blocked by policy")

    monkeypatch.setattr(shortcut, "create_shortcut", blocked)
    msg = shortcut.ensure_desktop_shortcut(app, tmp_path / "marker.json", desktop)
    assert msg and "could not create" in msg
    assert not (tmp_path / "marker.json").exists()  # will retry next launch
