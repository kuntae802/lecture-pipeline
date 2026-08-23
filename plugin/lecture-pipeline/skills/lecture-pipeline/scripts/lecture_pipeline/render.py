"""컷을 반영해 편집본 mp4 를 만든다 — ffmpeg 를 파이썬에서 직접 호출한다(셸 스크립트 없음).

기본은 **로컬 렌더**다. GPU 가 있으면 자동으로 NVENC 를 쓰고, 없으면 libx264 로 떨어진다.
원격 GPU 호스트가 있으면(`--ssh-host`) 원본과 세그먼트 작업을 그쪽 컨테이너에서 돌리고 결과만 받아온다 —
우리 환경(111 GB10)용 선택지이며, 없어도 파이프라인은 완결된다.

세그먼트별 재인코딩 + 경계 80ms 오디오 페이드 → concat demuxer `-c copy` 로 이어 붙인다.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .edl import FADE, keep_segments

CONCAT_NAME = "concat_list.txt"


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)]
    )
    return float(out.decode().strip())


def has_encoder(name: str) -> bool:
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return False
    return name in out.stdout


_NVENC_CACHE: bool | None = None


def nvenc_usable() -> bool:
    """`ffmpeg -encoders` 목록은 빌드 포함 여부만 알려준다(GPU 없는 PC 에서도 h264_nvenc 가 보인다).
    그래서 아주 짧은 실제 인코딩을 한 번 시켜 보고 판단한다(1초 내외)."""
    global _NVENC_CACHE
    if _NVENC_CACHE is not None:
        return _NVENC_CACHE
    if not has_encoder("h264_nvenc"):
        _NVENC_CACHE = False
        return False
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", "nullsrc=s=320x240:d=0.2", "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True, timeout=60, check=False,
        )
        _NVENC_CACHE = r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _NVENC_CACHE = False
    return _NVENC_CACHE


# 실측(1080p 화면녹화 3분 구간): libx264 veryfast 10.2초(32스레드)·11.6초(4스레드) vs NVENC 12.3초,
# 결과 크기는 x264 8.7MB vs NVENC 13.5MB. 강의는 움직임이 적은 화면 녹화라 x264 가 잘 먹는다.
# 그래서 코어가 넉넉하면 CPU 가 오히려 빠르고 작다 — GPU 는 코어가 적은 기기에서만 이득이다.
NVENC_CPU_THRESHOLD = 8


def pick_encoder(requested: str = "auto") -> str:
    """auto = 코어가 적은 기기에서만 NVENC, 그 외에는 libx264(위 실측 근거)."""
    if requested != "auto":
        return requested
    if (os.cpu_count() or 1) >= NVENC_CPU_THRESHOLD:
        return "libx264"
    return "h264_nvenc" if nvenc_usable() else "libx264"


def _video_args(encoder: str) -> list[str]:
    if encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]


def _segment_cmd(src: Path, start: float, end: float, dst: Path, encoder: str) -> list[str]:
    dur = end - start
    af = f"afade=t=in:st=0:d={FADE},afade=t=out:st={max(0.0, dur - FADE):.3f}:d={FADE}"
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(src),
        *_video_args(encoder),
        "-c:a", "aac", "-b:a", "160k", "-af", af,
        "-movflags", "+faststart", str(dst),
    ]


def concat_list_text(segments: list[Path]) -> str:
    """concat demuxer 목록 — 파일명만 쓴다(디렉터리는 실행 cwd 로 준다). 경로 안 따옴표 문제를 원천 차단."""
    return "".join(f"file '{p.name}'\n" for p in segments)


def render_local(src: Path, dst: Path, keeps: list[tuple[float, float]], workdir: Path, encoder: str = "auto") -> Path:
    enc = pick_encoder(encoder)
    workdir.mkdir(parents=True, exist_ok=True)
    for old in workdir.glob("seg_*.mp4"):
        old.unlink()
    print(f"[render] {len(keeps)} segments · encoder={enc} · workdir={workdir}", flush=True)

    t0 = time.time()
    segments: list[Path] = []
    for i, (start, end) in enumerate(keeps):
        seg = workdir / f"seg_{i:04d}.mp4"
        subprocess.run(_segment_cmd(src, start, end, seg, enc), check=True)
        segments.append(seg)
        done = i + 1
        rate = (time.time() - t0) / done
        print(f"[render] seg {done}/{len(keeps)} ok · 남은 예상 {rate * (len(keeps) - done) / 60:.1f}분", flush=True)

    listfile = workdir / CONCAT_NAME
    listfile.write_text(concat_list_text(segments), encoding="utf-8")
    dst.parent.mkdir(parents=True, exist_ok=True)
    # 목록에는 파일명만 적고 concat 을 workdir 에서 실행한다 — 경로에 작은따옴표(예: O'Brien)가 있어도 안전하다.
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", CONCAT_NAME, "-c", "copy", "-movflags", "+faststart", str(Path(dst).resolve())],
        check=True, cwd=workdir,
    )
    print(f"[render] done → {dst} ({time.time() - t0:.0f}초, {ffprobe_duration(dst):.1f}s)", flush=True)
    return dst


def render_remote(src: Path, dst: Path, keeps, workdir: Path, encoder: str, ssh_host: str, ssh_port: int,
                  image: str, remote_dir: str) -> Path:
    """원격 GPU 호스트의 컨테이너에서 렌더하고 결과만 회수한다(호스트는 클린 유지 — 컨테이너 안에서만 ffmpeg).

    ssh/scp 만 쓴다(rsync 불요). 원격에 이미 같은 크기의 원본이 있으면 전송을 건너뛴다.
    전제: 원격은 GNU coreutils 를 가진 리눅스 호스트이고 docker 를 쓸 수 있어야 한다(크기 비교에 `stat -c %s` 사용).
    """
    from .edl import write_render_script

    enc = encoder if encoder != "auto" else "h264_nvenc"   # 원격은 GPU 호스트 전제라 auto 는 NVENC
    ssh = ["ssh", "-p", str(ssh_port), ssh_host]
    subprocess.run([*ssh, f"mkdir -p {remote_dir}/in {remote_dir}/out {remote_dir}/work"], check=True)

    size = src.stat().st_size
    probe = subprocess.run([*ssh, f"stat -c %s {remote_dir}/in/source.mp4 2>/dev/null || echo 0"],
                           capture_output=True, text=True, check=False)
    if probe.stdout.strip() != str(size):
        print(f"[render] 원본 전송 → {ssh_host} ({size / 1e6:.0f}MB)", flush=True)
        subprocess.run(["scp", "-P", str(ssh_port), str(src), f"{ssh_host}:{remote_dir}/in/source.mp4"], check=True)
    else:
        print("[render] 원격에 동일 크기 원본 존재 — 전송 생략", flush=True)

    script = write_render_script(keeps, "/in/source.mp4", "/out/edited.mp4", "/work", enc)
    local_script = workdir / "render_remote.sh"
    workdir.mkdir(parents=True, exist_ok=True)
    local_script.write_text(script, encoding="utf-8")
    subprocess.run(["scp", "-P", str(ssh_port), str(local_script), f"{ssh_host}:{remote_dir}/render.sh"], check=True)

    guard = (
        f'if grep -q h264_nvenc /render.sh && ! ffmpeg -hide_banner -encoders 2>/dev/null | grep -q h264_nvenc; '
        f'then echo "ERROR: h264_nvenc not available" >&2; exit 2; fi'
    )
    inner = (
        "apt-get update -qq >/dev/null && apt-get install -y -qq ffmpeg >/dev/null && "
        f"{guard} && bash /render.sh"
    )
    docker = (
        f"docker run --rm --gpus all -v {remote_dir}/in:/in -v {remote_dir}/out:/out "
        f"-v {remote_dir}/work:/work -v {remote_dir}/render.sh:/render.sh:ro {image} bash -lc '{inner}'"
    )
    print(f"[render] 원격 컨테이너 렌더 시작 ({image})", flush=True)
    subprocess.run([*ssh, docker], check=True)

    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["scp", "-P", str(ssh_port), f"{ssh_host}:{remote_dir}/out/edited.mp4", str(dst)], check=True)
    print(f"[render] done → {dst} ({ffprobe_duration(dst):.1f}s)", flush=True)
    return dst


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="lp render", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--original", required=True, help="원본 mp4")
    ap.add_argument("--cuts", required=True, help="cuts.json (merge 산출물)")
    ap.add_argument("--out", required=True, help="편집본 mp4 경로")
    ap.add_argument("--workdir", help="세그먼트 임시 폴더(기본: <out>.work)")
    ap.add_argument("--encoder", default="auto", choices=["auto", "h264_nvenc", "libx264"])
    ap.add_argument("--ssh-host", help="원격 GPU 호스트(user@host) — 주면 원격 컨테이너에서 렌더")
    ap.add_argument("--ssh-port", type=int, default=22)
    ap.add_argument("--docker-image", default="nvcr.io/nvidia/pytorch:25.06-py3")
    ap.add_argument("--remote-dir", default="~/lecture_render")
    a = ap.parse_args(argv)

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        sys.exit("ffmpeg/ffprobe 를 찾을 수 없습니다. `lp.py doctor` 로 설치 방법을 확인하세요.")

    src = Path(a.original)
    dst = Path(a.out)
    workdir = Path(a.workdir) if a.workdir else dst.with_suffix(".work")
    cuts = [tuple(c["orig"]) for c in json.loads(Path(a.cuts).read_text(encoding="utf-8"))]
    keeps = keep_segments(ffprobe_duration(src), cuts)

    if a.ssh_host:
        render_remote(src, dst, keeps, workdir, a.encoder, a.ssh_host, a.ssh_port, a.docker_image, a.remote_dir)
    else:
        render_local(src, dst, keeps, workdir, a.encoder)


if __name__ == "__main__":
    main()
