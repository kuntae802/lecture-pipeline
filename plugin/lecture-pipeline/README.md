# lecture-pipeline (Claude Code · Codex 플러그인)

강의 영상을 목차·검색 가능한 자료로 바꾸는 파이프라인입니다. 자세한 설치·사용법은
[`skills/lecture-pipeline/README.md`](skills/lecture-pipeline/README.md) 를 보세요.

## Claude Code 설치

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

## Codex 설치

배포된 플러그인은 GitHub 저장소를 마켓플레이스로 등록해 설치합니다.

```bash
codex plugin marketplace add kuntae802/lecture-pipeline
codex plugin add lecture-pipeline@vcu-lecture-plugins
```

Codex 데스크톱 앱만 설치되어 터미널에서 `codex` 명령을 사용할 수 없다면, 앱의
대화창에서 다음처럼 요청합니다.

```text
GitHub 저장소 kuntae802/lecture-pipeline을 Codex 마켓플레이스로 등록하고
lecture-pipeline@vcu-lecture-plugins를 설치해 줘.
```

대화창에서 명령 실행 승인을 요청할 수 있습니다. WindowsApps 폴더의 앱 실행 파일은
직접 실행하지 않습니다.

개발 중인 로컬 버전을 시험할 때만 이 저장소 루트에서 다음을 실행합니다.

```bash
codex plugin marketplace add .
codex plugin add lecture-pipeline@vcu-lecture-plugins
```

Codex 대응 버전이 GitHub 배포 저장소에 올라오기 전에는 원격 설치 명령으로 새 버전을
받을 수 없습니다.

설치 후 새 Codex 대화를 시작하고, 산출물을 둘 빈 폴더에서 다음처럼 요청합니다.

```text
$lecture-pipeline https://youtu.be/영상ID
$lecture-pipeline https://youtu.be/영상ID --include-video
```

Codex와 Claude Code는 같은 `skills/lecture-pipeline/scripts/` 코드를 사용합니다. 작업 산출물은
대화를 시작한 폴더의 `workspace/` 아래에 만들어집니다. 자세한 옵션은
[`skills/lecture-pipeline/README.md`](skills/lecture-pipeline/README.md)를 보세요.
