---
name: lecture-pipeline
description: 유튜브 강의 URL → 편집본 mp4 + lecture.json + 챕터 썸네일. 기계 단계는 동봉된 파이썬 스크립트(표준 라이브러리만), 판단 단계(컷 편집·목차 구조화)는 이 문서의 브리프로 Opus 서브에이전트를 병렬로 띄운다. 사용 "/lecture-pipeline <youtube-url>".
---

# lecture-pipeline

강의 영상에서 **실언을 정정한 앞부분과 의미가 중복된 재발화만** 잘라낸 편집본을 만들고, 전체를 목차·요약·검색 가능한 전사로 구조화한다. 결과물을 뷰어 웹에 업로드하면 목차 점프·본문 검색·편집 검토가 되는 페이지가 된다.

**원칙: 소리가 아니라 발화를 편집한다.** 필러("어/음/그")·더듬·멈춤·잡음은 건드리지 않는다. 모든 단계가 파일을 남기므로 실패한 단계부터 다시 돌린다. 판단 단계의 출력은 기계 검증을 통과해야만 다음으로 간다.

## 경로 규칙 (중요)

- `$SKILL` = 이 스킬의 base directory(스킬이 로드될 때 함께 주어진다).
- `$PY` = `python3` (윈도우는 `python`). 0단계 `doctor` 가 어느 쪽인지 알려준다.
- **작업 산출물은 전부 현재 작업 폴더(cwd) 아래**에 만들어진다. 코드는 `$SKILL` 안에만 있고, 사용자는 아무 빈 폴더에서나 실행하면 된다.
- 아래에서 `<ID>` = 유튜브 video id(1단계가 URL 에서 뽑아 폴더 이름으로 쓴다). **사용자에게 강의 번호를 묻지 않는다** — 뷰어에 올라갈 강의 id 는 8단계가 `<ID>-<MMDD-HHMM>` 으로 자동 생성한다.
- **옵션:** 호출에 `--no-glossary` 가 붙으면 6.5단계(용어집)를 건너뛴다. 기본은 켜짐(서브에이전트 1개 추가).
- **진행도:** 환경변수 `VCU_API` 가 있으면 `lp.py` 명령이 자기 단계를 뷰어에 자동으로 알린다(뷰어 강의 목록에 작업 카드가 뜬다). 없으면 아무 일도 일어나지 않는다. 아래 4·6·6.5단계는 `lp.py` 밖에서 도는 판단 단계라 **직접 알려야** 그 구간이 화면에서 멈춘 것처럼 보이지 않는다.

## 0단계 — 환경 점검 (항상 먼저)

```
$PY "$SKILL/scripts/lp.py" doctor
```

- 전부 OK 면 1단계로 간다.
- 빠진 게 있으면 doctor 가 **그 OS 에 맞는 설치 명령**을 출력한다. 그 명령을 사용자에게 보여주고 **승인을 받아 실행**한 뒤 doctor 를 다시 돌린다. 사용자 승인 없이 설치 명령을 실행하지 않는다.
- GPU 유무와 무관하게 렌더는 CPU 로도 충분히 빠르다(3시간 강의 실측 약 13분, 기기에 따라 20~40분). 7단계 전에 예상 시간을 알린다.

## 단계

1. **확보** — `$PY "$SKILL/scripts/lp.py" fetch <url>`
   → `workspace/raw/<ID>/{source.mp4, source.ko.json3, source.info.json}` (이미 있으면 건너뜀 — 같은 영상을 다시 돌리면 재사용된다)
2. **전처리** — `$PY "$SKILL/scripts/lp.py" preprocess --source youtube_json3 --input workspace/raw/<ID>/source.ko.json3 --out workspace/build/<ID>/youtube --title "<ID>"`
   → `words.json`·`sentences.json`·`indexed.md`·`stats.json`
3. **청크** — `$PY "$SKILL/scripts/lp.py" chunk --build workspace/build/<ID>/youtube --out workspace/build/<ID>/chunks`
   → `NN.md` ×N + `manifest.json` (3시간 강의면 19개 안팎)
4. **편집 패스 (판단)** — `manifest.json` 의 청크마다 Opus 서브에이전트 1개를 **8개씩 병렬**로 띄운다(`Agent(model="opus")`). 브리프는 아래 [편집 브리프]에 절대경로만 채워 그대로 전달. 산출 `chunks/NN.cuts.json`·`chunks/NN.corrections.json`. 끝나면 파일 수가 청크 수와 같은지 확인한다.
   - 배치를 하나 마칠 때마다 진행도를 알린다 — `$PY "$SKILL/scripts/lp.py" progress --step edit --detail "8/19"` (완료 청크 수/전체).
5. **병합·검증** — `$PY "$SKILL/scripts/lp.py" merge --build workspace/build/<ID>/youtube --chunks workspace/build/<ID>/chunks`
   → `cuts.json`·`corrections.json`. 에러가 나면 **그 청크만** 4단계를 다시 돌린다(브리프 끝에 에러 메시지 원문을 붙인다). 첫 실행이면 컷 목록을 사용자에게 한 번 보여준다.
6. **구조화 패스 (판단)** — 먼저 `$PY "$SKILL/scripts/lp.py" progress --step outline` 로 시작을 알리고, Opus 서브에이전트 1개. 브리프는 아래 [구조화 브리프]. 산출 `workspace/build/<ID>/outline.json`·`notes.json`. 문장 커버리지가 어긋나면 8단계가 거부하므로, 에러를 붙여 1회 재실행한다. 끝나면 `... progress --step outline --status done`.
6.5. **용어집 패스 (판단, 선택)** — `--no-glossary` 가 아니면 `... progress --step glossary` 로 알린 뒤 Opus 서브에이전트 1개를 더 띄운다. 브리프는 아래 [용어집 브리프]. 산출 `workspace/build/<ID>/glossary.json`. 실패해도 파이프라인은 계속 간다(8단계에서 `--glossary` 를 빼면 그만).
7. **렌더** — `$PY "$SKILL/scripts/lp.py" render --original workspace/raw/<ID>/source.mp4 --cuts workspace/build/<ID>/youtube/cuts.json --out workspace/out/<ID>/edited.mp4`
   - 인코더 기본값 `auto` = 코어 8개 이상이면 libx264(실측상 GPU 보다 빠르고 파일도 작다), 그 미만이면 NVENC(실제 동작 확인 후). `--encoder` 로 강제 지정할 수 있다. 오래 걸리므로 백그라운드로 돌리고 로그를 남긴다.
   - 원격 GPU 호스트가 있으면 `--ssh-host user@host --ssh-port 22` 를 덧붙인다(그 호스트의 컨테이너에서 렌더하고 결과만 받아온다).
8. **조립** — 원본을 산출물 폴더에 `original.mp4` 로 하드링크(또는 복사)한 뒤
   `$PY "$SKILL/scripts/lp.py" assemble --build workspace/build/<ID>/youtube --outline workspace/build/<ID>/outline.json --notes workspace/build/<ID>/notes.json --info workspace/raw/<ID>/source.info.json --original workspace/raw/<ID>/source.mp4 --edited workspace/out/<ID>/edited.mp4 --out workspace/out/<ID>` (용어집을 만들었으면 `--glossary workspace/build/<ID>/glossary.json` 를 덧붙인다)
   → `lecture.json` + `thumbs/chNN.jpg`
9. **업로드** — 환경변수 `VCU_API` (뷰어 API 주소)가 있으면 **자동으로 올린다.**
   `$PY "$SKILL/scripts/lp.py" upload --out workspace/out/<ID>`
   → 썸네일 zip 을 알아서 만들어 함께 올리고, 적재·임베딩이 끝날 때까지 기다린 뒤 강의 id 를 출력한다.
   토큰을 요구하는 뷰어면 `VCU_API_TOKEN` 도 함께 설정한다(없으면 헤더를 생략한다).
   실패하면 아래 수동 절차를 안내한다 — 산출물은 이미 다 만들어져 있으므로 다시 돌릴 필요가 없다.

   `VCU_API` 가 없으면 산출물 폴더 `workspace/out/<ID>/` 를 알리고, 뷰어 웹의 **업로드 화면**에서 아래 3개(+선택 1개)를 올리게 안내한다.
   - `original.mp4` (원본 — 편집 검토 화면의 대조용)
   - `edited.mp4` (편집본 — 플레이어 본체)
   - `lecture.json` (전사·컷·목차·노트)
   - `thumbs.zip` (선택 — 챕터 썸네일. 없으면 목차에 회색 박스)
   썸네일 zip 은 `$PY -c "import shutil;shutil.make_archive('workspace/out/<ID>/thumbs','zip','workspace/out/<ID>','thumbs')"` 로 만든다.

   같은 영상을 다시 올려도 **덮어쓰지 않고 새 강의로 쌓인다**(강의 id 가 조립 때마다 새로 생긴다).

## [편집 브리프] — 청크마다 `<ABS>`(작업 폴더 절대경로)·`<ID>`·`NN` 만 바꿔 그대로 전달

```
You are the editorial pass of a Korean technical-lecture editing pipeline. Your ONLY job: find places where the lecturer (a) misspoke and then corrected themself, or (b) abandoned an attempt and re-delivered the same content, and mark the abandoned/incorrect span for cutting. Nothing else is cut.

INPUT: <ABS>/workspace/build/<ID>/chunks/NN.md — `[N] [start-end] word` lines (N = global word index, seconds). `_(silence Xs)_` = pause. The `## CONTEXT` block is read-only (never cut there); cut only inside `## EDITABLE RANGE`.

OUTPUT (write both files; valid JSON arrays only — empty array [] is fine):
- <ABS>/workspace/build/<ID>/chunks/NN.cuts.json: [{"from_idx": int, "to_idx": int, "category": "misstatement"|"duplicate", "confidence": "high"|"medium", "note": "why this span is the abandoned/incorrect attempt and what re-covers it"}]
- <ABS>/workspace/build/<ID>/chunks/NN.corrections.json: [{"idx": int, "from": "<word as written>", "to": "<corrected word>"}] — ONLY technical terms / product names that are clearly misrecognized (e.g. 오프스→오푸스, 출론→추론, 아크다운→마크다운, 안솔로→앤트로픽). One token → one token. No grammar or particle fixes, no expansions, no fixes of ordinary words.

RULES:
1. misstatement = wrong content followed by a correction (e.g. "…한 500명 미만에 아 다시 한 200명 미만의…" → cut "한 500명 미만에 아 다시"). duplicate = the speaker restarts the same thought and the later version supersedes the earlier → cut the earlier attempt.
2. NEVER cut fillers (어/음/그/자/네/예), stutters, repeated single words, pauses, audio events ([콧방귀] etc.), or deliberate recaps ("다시 한번 말씀드리면", "정리하면").
3. A cut is a meaningful clause/sentence span — never under ~1 second. Cut END = end of the restart/correction signal (or end of the abandoned attempt). Cut START = beginning of the abandoned attempt at a clause boundary, preferably right after a pause. Verify the speech AFTER the cut re-covers the abandoned content; if it does not, do not cut.
4. When in doubt cut LESS (only the clause right before the signal) or not at all. Expect 0–5 cuts per 10-minute chunk; zero is a valid answer.
5. Indices must exist in the input; from_idx ≤ to_idx; spans must not overlap each other.

Finish with a 3-line report: number of cuts (with idx ranges, time ranges, categories), number of corrections, anything you were unsure about. Return only that report.
```

## [구조화 브리프]

```
You are structuring a Korean technical lecture transcript into a two-level outline.

INPUT: <ABS>/workspace/build/<ID>/youtube/sentences.json — [{idx, start, end, text, word_from, word_to}] in order (N sentences; seconds). Sentences whose word range falls inside cut spans listed in <ABS>/workspace/build/<ID>/youtube/cuts.json are removed speech — ignore their content but keep idx continuity. Read the file in parts if it is large.

OUTPUT (valid JSON only):
- <ABS>/workspace/build/<ID>/outline.json = {"chapters": [{"id": "1", "title": "...", "summary": "...", "segments": [first_idx, last_idx], "children": [{"id": "1.1", "title": "...", "summary": "...", "segments": [a, b]}, ...]}, ...]}
- <ABS>/workspace/build/<ID>/notes.json = {"commands": [{"text": "...", "segment_idx": n}], "links": [{"url": "...", "label": "...", "segment_idx": n}]}

RULES: 6–12 level-1 chapters, each with 2–6 children. `segments` ranges are contiguous, non-overlapping, in order, and together cover 1..N exactly; children cover their parent's range exactly. Use sentence idx values (not word indices, not seconds). Titles = concise Korean noun phrases in the lecturer's own vocabulary (no invented jargon, ≤ 30 characters). Level-1 summary 3–5 sentences, level-2 1–2 sentences, faithful to what was said (no additions, no evaluation). commands = terminal/CLI/code one-liners the lecturer actually says or reads out; links = URLs or sites mentioned (label = how the lecturer referred to it). Empty arrays if none. Verify the coverage rules programmatically before finishing, and fix them if they fail.

Finish with a 3-line report (chapters/children counts, commands/links counts, anything you were unsure about). Return only that report.
```

## [용어집 브리프]

```
You are building a glossary for a Korean technical lecture, for learners who are watching it.

INPUT: <ABS>/workspace/build/<ID>/youtube/sentences.json — [{idx, start, end, text, ...}] in order. Also read <ABS>/workspace/build/<ID>/outline.json for the chapter structure (it tells you what the lecture actually teaches). Sentences inside cut spans in <ABS>/workspace/build/<ID>/youtube/cuts.json are removed speech — ignore them.

OUTPUT: <ABS>/workspace/build/<ID>/glossary.json = [{"term": "...", "definition": "...", "analogy": "...", "segment_idx": n}]  (valid JSON array only)

WHAT COUNTS AS A TERM:
- Include a technical term ONLY IF the lecturer actually explains, defines, or works with it in this lecture — something a learner would need to understand to follow along. A term merely name-dropped in passing does not qualify.
- Prefer the standard spelling of the term even when the auto-caption misheard it (e.g. write "REPL", "IDE", "PostgreSQL"), and give both scripts when both are used in Korean tech speech (e.g. "리팩터링(refactoring)").
- Skip: the lecturer's own file/project names, ordinary words, and anything specific to this one demo project.
- 8–25 terms for a 20-minute lecture, 20–60 for a 3-hour one. Order by first appearance.

WHAT TO WRITE:
- "definition": 1–2 sentences of general, correct knowledge — NOT a transcript quote. Write what the term actually means in the field, at a level a non-developer can follow. Do not contradict the lecture; if the lecturer used the term loosely, define it correctly and neutrally.
- "analogy": ONE sentence of everyday comparison that carries the term's core mechanism (not decoration). Omit the key entirely if no honest analogy exists — a missing analogy is better than a misleading one.
- "segment_idx": the sentence index where the term is first explained (must exist in sentences.json).

Finish with a 3-line report: number of terms, which ones you were unsure qualified, any term whose analogy you deliberately omitted. Return only that report.
```

## 참고

- 3시간 강의 기준 실측(1강): 전처리 수 초 · 편집 패스 약 10분(19청크 병렬) · 구조화 약 8분 · 렌더 약 12~14분(libx264 4스레드 기준 13분) · 컷 63건/2분 42초 제거.
- 편집 패스는 Opus 서브에이전트를 많이 쓴다 — 3시간 강의 한 편에 대략 150만 토큰. 사용자에게 미리 알린다.
- 용어집은 서브에이전트 1개(3시간 강의 기준 20만 토큰 안팎)를 더 쓴다. 비용을 아끼려면 `--no-glossary`.
- 사람이 읽을 설치·사용 안내는 `$SKILL/README.md`.
