# lecture-pipeline

유튜브 강의 URL 하나로 **편집본 영상 + 목차·요약·검색용 데이터**를 만드는 Claude Code 플러그인입니다.

3시간짜리 강의를 그대로 올려두면 아무도 다시 찾아보지 않습니다. 이 파이프라인은 잘못 말하고 고쳐 말한 부분을 걷어낸 편집본을 만들고, 전체를 2단 목차·챕터 요약·용어집·검색 가능한 전사로 구조화합니다.

- **자르는 것:** 실언을 정정한 앞부분, 같은 내용을 다시 말해 앞 시도가 흡수된 구간
- **자르지 않는 것:** 필러(어·음·그), 더듬, 반복 단어, 멈춤, 잡음, 의도적 요약("다시 한번 말씀드리면")
- 원본은 그대로 두고 편집본을 따로 만듭니다. **모든 컷은 목록으로 남아** 원본과 대조할 수 있습니다.

## 설치

```
/plugin marketplace add kuntae802/lecture-pipeline
/plugin install lecture-pipeline@vcu-lecture-plugins
```

## 사용

Claude Code 에서 아무 **빈 폴더**를 열고:

```
/lecture-pipeline https://youtu.be/영상ID
```

강의 번호도, 옵션도 묻지 않습니다. 산출물은 그 폴더 아래 `workspace/` 에 쌓이고, 코드는 플러그인 폴더 안에만 있어 작업 폴더를 더럽히지 않습니다.

용어집을 빼려면 `--no-glossary` 를 붙이면 됩니다.

## 준비물

파이썬 서드파티 패키지는 **하나도 필요 없습니다**(표준 라이브러리만 씁니다). 대신 아래 네 가지가 있어야 합니다.

| 필요한 것 | 용도 |
|---|---|
| Python 3.12+ | 파이프라인 스크립트 |
| ffmpeg / ffprobe | 영상 자르기·이어붙이기·썸네일 |
| yt-dlp | 유튜브 원본·자동자막 받기 |
| node 또는 deno | yt-dlp 가 유튜브 차단(403)을 피하는 데 필요 |

**직접 확인할 필요는 없습니다.** 스킬을 실행하면 첫 단계가 환경 점검이고, 빠진 게 있으면 그 OS 에 맞는 설치 명령을 알려준 뒤 승인을 받아 대신 실행해 줍니다. 윈도우는 WSL2 를 권합니다.

## 걸리는 시간 (3시간 강의 한 편, 실측)

| 단계 | 소요 |
|---|---|
| 원본·자막 받기 | 1~3분 |
| 컷 편집 판단(LLM 병렬) | 약 10분 |
| 목차·요약 구조화(LLM) | 약 8분 |
| 렌더 | 13~40분 (GPU 없어도 됩니다) |

컷 편집 판단에 **Opus 서브에이전트를 많이 씁니다 — 3시간 강의 한 편에 대략 150만 토큰.** Claude 구독 사용량을 꽤 소모합니다.

## 뷰어 웹 (선택)

산출물(`lecture.json` + 영상 2개 + 썸네일)을 그대로 두고 봐도 되지만, 짝이 되는 뷰어 웹에 올리면 **목차 점프·본문 검색·편집 검토**가 되는 페이지가 됩니다. 뷰어 주소를 환경변수로 알려 두면 마지막 업로드 단계까지 자동입니다.

```bash
export VCU_API=https://예시.도메인/경로/api
export VCU_API_TOKEN=...        # 토큰을 요구하는 뷰어라면
```

이러면 작업이 도는 동안 **뷰어 화면에서 진행 상황도 볼 수 있습니다**(지금 어느 단계인지, 얼마나 지났는지). 환경변수가 없으면 아무것도 보내지 않고, 마지막에 산출물 폴더만 알려 줍니다.

## 더 읽을 것

- [`plugin/lecture-pipeline/skills/lecture-pipeline/README.md`](plugin/lecture-pipeline/skills/lecture-pipeline/README.md) — 설치 상세, 폴더 구조, 자주 막히는 곳
- [`plugin/lecture-pipeline/skills/lecture-pipeline/SKILL.md`](plugin/lecture-pipeline/skills/lecture-pipeline/SKILL.md) — 단계별 실행 절차와 LLM 브리프 원문
