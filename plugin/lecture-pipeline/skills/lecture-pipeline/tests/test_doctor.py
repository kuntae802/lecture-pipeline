from lecture_pipeline import doctor


def _res(*, os_key="linux", python=True, ffmpeg=True, ytdlp=True, js=True, nvenc=False):
    return {
        "os": os_key,
        "python": {"ok": python, "version": "3.12.3", "exe": "/usr/bin/python3",
                   "command": "python" if os_key == "windows" else "python3"},
        "ffmpeg": {"ok": ffmpeg, "path": "/usr/bin/ffmpeg", "version": "ffmpeg version 6.1.1"},
        "yt-dlp": {"ok": ytdlp, "path": "/usr/bin/yt-dlp", "version": "2026.08.19"},
        "js_runtime": {"ok": js, "node": "/usr/bin/node", "deno": None, "version": "v24.15.0"},
        "gpu_nvenc": nvenc,
    }


def test_os_key_detects_wsl_separately_from_plain_linux(monkeypatch):
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doctor.platform, "release", lambda: "5.15.0-generic")
    assert doctor._os_key() == "linux"
    monkeypatch.setattr(doctor.platform, "release", lambda: "5.15.153.1-microsoft-standard-WSL2")
    assert doctor._os_key() == "wsl"


def test_os_key_maps_mac_and_windows(monkeypatch):
    monkeypatch.setattr(doctor.platform, "system", lambda: "Darwin")
    assert doctor._os_key() == "macos"
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")
    assert doctor._os_key() == "windows"


def test_install_hints_cover_every_os_and_every_requirement():
    for os_key, hints in doctor.INSTALL.items():
        assert set(hints) == {"ffmpeg", "yt-dlp", "js", "python"}, os_key
        assert all(v.strip() for v in hints.values()), os_key


def test_report_exit_code_is_zero_only_when_nothing_is_missing(capsys):
    assert doctor.report(_res()) == 0
    assert "필요한 것이 모두 준비됐습니다" in capsys.readouterr().out
    assert doctor.report(_res(ffmpeg=False)) == 1


def test_report_lists_install_command_for_each_missing_item(capsys):
    doctor.report(_res(os_key="macos", ffmpeg=False, ytdlp=False))
    out = capsys.readouterr().out
    assert "brew install ffmpeg" in out and "brew install yt-dlp" in out
    assert "brew install node" not in out           # 있는 것의 설치 명령은 보여주지 않는다


def test_report_warns_about_cpu_render_time_and_windows_wsl(capsys):
    doctor.report(_res(nvenc=False))
    assert "libx264(CPU)" in capsys.readouterr().out
    doctor.report(_res(os_key="windows"))
    assert "WSL2" in capsys.readouterr().out
