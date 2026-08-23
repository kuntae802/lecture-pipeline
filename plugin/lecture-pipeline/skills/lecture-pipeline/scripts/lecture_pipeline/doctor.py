"""실행 환경 점검 — 뭐가 없는지와 OS별 설치 명령을 알려준다.

파이프라인이 요구하는 것은 파이썬 표준 라이브러리 + 외부 바이너리 세 종류뿐이다(서드파티 파이썬 패키지 0).
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PY = (3, 12)


def _version(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr).strip() else ""


def _os_key() -> str:
    s = platform.system()
    if s == "Linux":
        # WSL 은 리눅스로 취급(설치 방법이 같다)
        return "wsl" if "microsoft" in platform.release().lower() else "linux"
    return {"Darwin": "macos", "Windows": "windows"}.get(s, "linux")


INSTALL = {
    "linux": {
        "ffmpeg": "sudo apt install -y ffmpeg          # 데비안/우분투 계열",
        "yt-dlp": "uv tool install yt-dlp   (또는) pipx install yt-dlp   (또는) pip install --user yt-dlp",
        "js": "sudo apt install -y nodejs   (또는) curl -fsSL https://deno.land/install.sh | sh",
        "python": "sudo apt install -y python3",
    },
    "wsl": {
        "ffmpeg": "sudo apt install -y ffmpeg",
        "yt-dlp": "uv tool install yt-dlp   (또는) pipx install yt-dlp",
        "js": "sudo apt install -y nodejs",
        "python": "sudo apt install -y python3",
    },
    "macos": {
        "ffmpeg": "brew install ffmpeg",
        "yt-dlp": "brew install yt-dlp",
        "js": "brew install node",
        "python": "brew install python@3.12",
    },
    "windows": {
        "ffmpeg": "winget install Gyan.FFmpeg   (설치 후 새 터미널에서 PATH 반영 확인)",
        "yt-dlp": "winget install yt-dlp.yt-dlp",
        "js": "winget install OpenJS.NodeJS",
        "python": "winget install Python.3.12",
    },
}

WINDOWS_NOTE = (
    "윈도우는 WSL2 를 권장합니다 — `wsl --install` 로 우분투를 깔면 위 리눅스 절차가 그대로 통하고,\n"
    "  이 파이프라인이 실제로 검증된 환경과 같아집니다. 네이티브 윈도우도 동작하도록 만들었지만 검증되지 않았습니다."
)


def check() -> dict:
    os_key = _os_key()
    py_ok = sys.version_info >= MIN_PY
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    ytdlp = shutil.which("yt-dlp")
    node = shutil.which("node")
    deno = shutil.which("deno")

    nvenc = False
    if ffmpeg:
        # 목록 조회가 아니라 실제 인코딩 프로브 — GPU 없는 PC 에서도 목록에는 h264_nvenc 가 뜬다.
        from .render import nvenc_usable

        nvenc = nvenc_usable()

    return {
        "os": os_key,
        "python": {"ok": py_ok, "version": platform.python_version(), "exe": sys.executable,
                   "command": "python" if os_key == "windows" else "python3"},
        "ffmpeg": {"ok": bool(ffmpeg and ffprobe), "path": ffmpeg, "version": _version(["ffmpeg", "-version"])},
        "yt-dlp": {"ok": bool(ytdlp), "path": ytdlp, "version": _version(["yt-dlp", "--version"])},
        "js_runtime": {"ok": bool(node or deno), "node": node, "deno": deno,
                       "version": _version(["node", "--version"]) if node else _version(["deno", "--version"])},
        "gpu_nvenc": nvenc,
    }


def report(res: dict) -> int:
    os_key = res["os"]
    tips = INSTALL.get(os_key, INSTALL["linux"])
    lines: list[str] = [f"환경: {platform.system()} ({os_key}) · python {res['python']['version']}", ""]
    missing: list[str] = []

    def row(label: str, ok: bool, detail: str) -> None:
        lines.append(f"  {'OK  ' if ok else '없음'}  {label:<12} {detail}")

    row("python", res["python"]["ok"], f"{res['python']['version']} (필요 {MIN_PY[0]}.{MIN_PY[1]}+) · 실행 명령 `{res['python']['command']}`")
    if not res["python"]["ok"]:
        missing.append(("python", tips["python"]))
    row("ffmpeg", res["ffmpeg"]["ok"], res["ffmpeg"]["version"] or "ffmpeg/ffprobe 둘 다 필요")
    if not res["ffmpeg"]["ok"]:
        missing.append(("ffmpeg", tips["ffmpeg"]))
    row("yt-dlp", res["yt-dlp"]["ok"], res["yt-dlp"]["version"] or "유튜브 원본·자막 취득에 필요")
    if not res["yt-dlp"]["ok"]:
        missing.append(("yt-dlp", tips["yt-dlp"]))
    row("JS 런타임", res["js_runtime"]["ok"], res["js_runtime"]["version"] or "node 또는 deno — yt-dlp 가 403 을 피하는 데 필요")
    if not res["js_runtime"]["ok"]:
        missing.append(("JS 런타임(node/deno)", tips["js"]))

    lines.append("")
    if res["gpu_nvenc"]:
        lines.append("  GPU: h264_nvenc 사용 가능(코어가 적은 기기에서 자동 사용).")
    else:
        lines.append("  GPU: NVENC 없음 → libx264(CPU)로 렌더합니다. 3시간 강의 기준 실측 약 13분(4스레드), 기기에 따라 20~40분.")

    from . import config
    lines += ["", f"  뷰어: {config.api()}" + ("  (내장 기본값)" if config.is_default() else "  (VCU_API 로 지정됨)"),
              "        완성된 강의를 여기로 올리고 작업 진행도도 여기서 볼 수 있습니다."]

    if missing:
        lines += ["", "설치가 필요합니다:"]
        for name, cmd in missing:
            lines += [f"  - {name}", f"      {cmd}"]
    else:
        lines += ["", "필요한 것이 모두 준비됐습니다."]

    if os_key == "windows":
        lines += ["", WINDOWS_NOTE]

    print("\n".join(lines))
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="lp doctor", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="점검 결과를 JSON 으로 출력(자동 처리용)")
    a = ap.parse_args(argv)
    res = check()
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        raise SystemExit(0 if all(res[k]["ok"] for k in ("python", "ffmpeg", "yt-dlp", "js_runtime")) else 1)
    raise SystemExit(report(res))


if __name__ == "__main__":
    main()
