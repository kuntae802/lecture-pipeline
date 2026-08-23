# lecture-pipeline (Claude Code 플러그인)

강의 영상을 목차·검색 가능한 자료로 바꾸는 파이프라인입니다. 자세한 설치·사용법은
[`skills/lecture-pipeline/README.md`](skills/lecture-pipeline/README.md) 를 보세요.

## 설치

```
/plugin marketplace add <이 레포 주소 또는 로컬 경로>
/plugin install lecture-pipeline@vcu-lecture-plugins
```

설치 후 아무 빈 폴더에서:

```
/lecture-pipeline https://youtu.be/영상ID
```

첫 단계가 환경 점검이라, 필요한 도구(python3 · ffmpeg · yt-dlp · node/deno)가 없으면
그 OS 에 맞는 설치 명령을 알려주고 승인을 받아 대신 설치해 줍니다.
