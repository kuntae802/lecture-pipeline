#!/usr/bin/env python3
"""lecture-pipeline 단일 진입점.

이 파일이 있는 폴더를 import 경로에 넣으므로 **어느 위치에서 실행해도** 동작한다.
작업 산출물은 항상 "현재 작업 폴더(cwd)" 기준으로 만들어지고, 코드는 이 스킬 폴더 안에만 있다.

    python3 <이 파일> doctor
    python3 <이 파일> fetch <youtube-url>
    python3 <이 파일> preprocess --source youtube_json3 --input ... --out ...
    python3 <이 파일> chunk --build ... --out ...
    python3 <이 파일> merge --build ... --chunks ...
    python3 <이 파일> render --original ... --cuts ... --out ...
    python3 <이 파일> assemble --build ... --outline ... --notes ... --info ... --original ... --edited ... --out ...

의존성: 파이썬 표준 라이브러리만(서드파티 패키지 0) + 외부 바이너리 yt-dlp·ffmpeg/ffprobe.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

COMMANDS = {
    "doctor": ("lecture_pipeline.doctor", "실행 환경 점검 + OS별 설치 안내"),
    "fetch": ("lecture_pipeline.fetch", "유튜브 원본 mp4·한국어 자동자막·메타 취득"),
    "preprocess": ("lecture_pipeline.preprocess", "자막 → 단어/문장/LLM 입력용 인덱스"),
    "chunk": ("lecture_pipeline.chunk", "11분 창으로 분할(문장 경계 유지)"),
    "merge": ("lecture_pipeline.merge_edits", "청크별 편집 결과 병합·검증"),
    "edl": ("lecture_pipeline.edl", "(고급) 원격 렌더용 셸 스크립트 생성"),
    "render": ("lecture_pipeline.render", "컷 반영 편집본 렌더(로컬 ffmpeg, GPU 있으면 자동 사용)"),
    "assemble": ("lecture_pipeline.assemble", "lecture.json + 챕터 썸네일 조립"),
    "upload": ("lecture_pipeline.upload", "산출물 폴더를 뷰어 웹에 업로드(VCU_API 필요)"),
    "progress": ("lecture_pipeline.jobs", "작업 진행도 보고(판단 단계용 — lp.py 밖에서 도는 단계)"),
}


def usage() -> None:
    print(__doc__)
    print("사용 가능한 명령:")
    for name, (_, desc) in COMMANDS.items():
        print(f"  {name:<11} {desc}")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        usage()
        raise SystemExit(0)
    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"알 수 없는 명령: {cmd}\n", file=sys.stderr)
        usage()
        raise SystemExit(2)

    module_name = COMMANDS[cmd][0]
    from importlib import import_module

    module = import_module(module_name)
    sys.argv = [f"lp {cmd}", *sys.argv[2:]]

    # 진행도 보고로 감싼다. VCU_API 나 workspace/.job 이 없으면 전부 no-op 이고,
    # 보고가 실패해도 명령 자체는 그대로 간다(jobs.report 가 예외를 삼킨다).
    # progress·doctor 는 보고 대상이 아니다(전자는 보고 그 자체, 후자는 작업 폴더 밖 점검).
    from lecture_pipeline import jobs

    tracked = cmd in jobs.STEPS
    if tracked:
        jobs.report(cmd, "running")
    try:
        module.main()
    except SystemExit as exc:
        if tracked and (exc.code or 0) != 0:
            jobs.report(cmd, "failed", error=f"{cmd} exit {exc.code}")
        elif tracked:
            jobs.report(cmd, "done")
        raise
    except BaseException as exc:
        if tracked:
            jobs.report(cmd, "failed", error=f"{type(exc).__name__}: {exc}"[:800])
        raise
    if tracked:
        jobs.report(cmd, "done")


if __name__ == "__main__":
    main()
