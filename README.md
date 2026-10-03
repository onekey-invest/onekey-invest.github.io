# 리서치 사이트

기업·산업 리포트, 가상운용 전략, 마켓노트를 정적 사이트로 만드는 도구. 파이썬으로 `dist/` 폴더에 HTML을 만들고, 그 폴더를 그대로 호스팅에 올린다. 상시 서버는 없다.

## 실행

```bash
python serve.py
```

http://localhost:4321 에서 본다. 파일을 고치고 브라우저를 새로 고치면 다시 만들어진다.

```bash
python build.py
```

`dist/`만 만든다.

```bash
python -m unittest discover tests
```

수익률 계산과 차트 눈금을 검증한다.

필요한 패키지는 `requirements.txt`에 있다(Jinja2, PyYAML, Markdown).

## 폴더

| 위치 | 내용 |
|---|---|
| `data/site.yaml` | 사이트 이름, 작성자, 홈의 큰 문장과 소개, 외부 링크 |
| `data/companies.yaml` | 커버 종목, 투자포인트, 실적 추정, 밸류에이션 상세, 리스크·회고 |
| `data/industries.yaml` | 커버 산업, 산업 의견, 핵심 논점, 밸류체인 |
| `data/indicators/산업id.csv` | 산업 핵심 지표. 첫 열은 date, 나머지 열이 지표(없어도 된다) |
| `data/prices/*.csv` | 일별 종가. 파일 이름은 종목 id 또는 벤치마크 이름 |
| `data/strategies.yaml` | 가상운용 전략. 규칙, 근거, 백테스트 설명, 회고 |
| `data/trades/전략id.csv` | 전략의 거래 기록 |
| `data/backtests/전략id.csv` | 운용 개시 전 백테스트 곡선(없어도 된다) |
| `content/reports/*.md` | 리포트 원고. 투자의견과 목표주가는 여기서 읽는다 |
| `content/notes/날짜.md` | 마켓노트. 하루에 한 파일 |
| `content/pages/*.md` | 방법론, About |
| `lib/metrics.py` | 커버리지 수익률 계산 |
| `lib/portfolio.py` | 가상운용 평가금액·MDD·샤프 계산 |
| `lib/chart.py` | 표 안의 추이선과, 스크립트가 안 될 때 보이는 대체 차트(SVG) |
| `static/charts.js` | 화면의 차트. TradingView Lightweight Charts를 쓴다 |
| `templates/` | 화면 틀 |
| `static/` | 스타일, 표 정렬·검색 스크립트. 리포트 PDF는 `static/reports/`에 둔다 |
| `DESIGN.md` | 디자인 규칙. 화면을 고치기 전에 읽는다 |

## 리포트 추가

`content/reports/`에 마크다운 파일을 만든다. 파일 이름은 `발행일-종목id.md` 형식을 권한다.

```markdown
---
id: ex001-20261105          # 주소에 쓰인다. 겹치면 안 된다
company: ex001              # 산업 리포트면 company 대신 industry: 산업id
date: 2026-11-05
kind: 업데이트               # 최초 / 업데이트 / 산업
title: "제목"
rating: 매수                 # 기업 리포트에만 필요
target: 90000               # 기업 리포트에만 필요
summary: 한 줄 요약
pdf: ""                     # static/reports/ 안의 파일 이름. 없으면 비워 둔다
---

본문
```

- 한 종목의 첫 리포트 발행일이 커버리지 개시일이 된다.
- 가장 최근 리포트의 의견과 목표주가가 현재 값으로 표시된다.
- 발행한 리포트는 고치지 않는다. 판단이 바뀌면 새 리포트를 추가한다.
- 머리말에 `featured: true`를 넣으면 홈과 About의 대표 리포트에 나온다(최근 3건).

## 마켓노트 추가

`content/notes/2026-10-01.md`처럼 날짜를 파일 이름으로 한다.

```markdown
---
date: 2026-10-01
headline: "오늘의 한 줄"
indicators:                 # 시장 지표 4칸. 값은 직접 적는다
  - {name: KOSPI, value: "3,814.80", change: "+0.4%"}
comment: >-                 # 내 코멘트
  커버 종목 관점의 한두 문장
summary: ["알아야 할 것: ...", "가장 큰 리스크: ...", "확인할 것: ..."]
companies: [ex001]          # 이 종목의 기업 화면에 자동으로 걸린다
industries: [semi-equipment]
tags: [반도체]
week: ["10.02(금) 미국 고용보고서"]   # 이번 주 주요 일정
review: "어제 확인하겠다고 한 것 → 결과"  # 어제 확인한 것 (없어도 된다)
draft: true                 # 공개 전. 이 줄이 있으면 사이트에 나가지 않는다
---

## 통합 브리핑

## 기업·산업 Watch

## 오늘·내일 새벽 이벤트
```

본문의 `## 제목` 하나가 접는 구획 하나가 된다. 브리핑 양식의 [1]~[4]를 여기에 넣는다.

### 브리핑에서 바로 만들기

아침 브리핑 글(양식의 [0]~[6]이 다 들어 있는 것)을 파일로 저장한 뒤 실행한다.

```
python tools/import_briefing.py 브리핑.txt
```

- 머리말은 [6. 짧은 노트]에서, 본문은 [1]~[4]에서, 최종 요약은 [5]에서 가져온다.
- 만든 원고는 저장소에 올리면 바로 공개된다. `--draft`를 붙이면 공개 전(`draft: true`)으로 만들고, 이때는 `python serve.py` 미리보기에서만 보인다.
- `comment`는 비워 둔다. 쓰고 싶은 날 직접 적으면 그날만 "내 코멘트" 칸이 나타난다.
- 같은 날짜 원고가 이미 있으면 멈춘다. 덮어쓰려면 `--force`.

## 종목 추가

1. `data/companies.yaml`에 종목을 추가한다.
2. `data/prices/종목id.csv`에 일별 종가를 넣는다(`date,close`, 커버리지 개시일 이전부터).
3. 그 종목의 최초 리포트를 `content/reports/`에 넣는다.

빠진 것이 있으면 빌드가 어느 파일의 무엇이 없는지 알려 주고 멈춘다.

## 전략 추가

1. `data/strategies.yaml`에 전략을 추가한다. 규칙과 근거를 먼저 쓰고 `published`에 공개일을 적는다.
2. `data/trades/전략id.csv`에 거래를 적는다. 열은 `date,asset,side,qty,price,note`이고 side는 매수 또는 매도다.
3. 거래한 자산의 종가 파일이 `data/prices/`에 있어야 한다. 기업 페이지가 있는 종목은 asset에 종목 id를 쓰면 서로 연결된다.
4. 백테스트가 있으면 `data/backtests/전략id.csv`에 `date,value`로 넣는다. 차트에 점선으로 나온다.

현금보다 많이 사거나 보유 수량보다 많이 팔면 빌드가 멈춘다. 전략을 중단하면 `status: 중단`과 `stopped`를 적고 회고를 `log`에 남긴다.

## 실제 종가 받기

```bash
pip install -r requirements-data.txt
python tools/update_prices.py
```

`data/sources.yaml`에 적은 대상의 일별 종가를 받아 `data/prices/`에 저장한다. 국내 종목은 pykrx(수정주가), 지수와 해외 종목은 yfinance로 받는다. 두 도구 모두 공식 제공 경로가 아니어서 값이 비거나 형식이 바뀔 수 있다. 한 대상이 실패하면 그 대상의 기존 파일은 그대로 두고 오류로 끝난다.

- 한국 시간 16시 전에 돌리면 어제까지만 받는다.
- 2026-10-02에 삼성전자·KOSPI·KOSDAQ로 받아 사이트가 만들어지는 것을 임시 복사본에서 확인했다.
- pykrx는 로그인 없이 종목 종가는 받지만 지수는 받지 못한다. 그래서 지수는 yfinance로 받는다.

## 자동 갱신과 배포

`.github/workflows/daily.yml`이 평일 18:30에 종가를 받고, 검증하고, 사이트를 만들어 GitHub Pages에 올린다. `site/` 폴더를 저장소의 맨 위로 삼는다.

1. GitHub에 저장소를 만들고 이 폴더를 올린다.
2. Settings → Pages → Source를 "GitHub Actions"로 바꾼다.
3. 주소가 `아이디.github.io/저장소이름` 형태면 `data/site.yaml`의 `base_url`에 `/저장소이름`을 적는다.

이 설정은 실제 저장소에서 아직 돌려 보지 않았다. GitHub의 서버에서 pykrx가 종가를 받을 수 있는지도 첫 실행에서 확인해야 한다.

## 지금 들어 있는 것은 예시다

회사 세 곳, 산업 두 곳, 리포트 일곱 건, 전략 두 개, 마켓노트 세 건, 시세·거래·지표 파일은 모두 화면 확인용 예시다. `data/site.yaml`의 `demo: true`가 켜져 있는 동안 모든 화면 위에 안내 띠가 나온다. 실제 자료로 바꾸면 다음을 한다.

- 예시 종목·산업·리포트·전략·노트·시세·거래·지표 파일 삭제
- `data/sources.yaml`에 실제 종목과 벤치마크를 적고 `python tools/update_prices.py` 실행
- `tools/make_example_prices.py`, `tools/make_example_portfolio.py` 삭제
- `demo: false`

## 아직 없는 것

- GitHub 저장소 생성과 첫 배포(설정 파일은 준비됨, 미검증)
- 리포트 PDF 첫 장 썸네일
- 해외 주식·멀티에셋 전략(화면 자리는 있고 전략이 없다)
- 마켓노트 주간 정리, 공시 연동, 실시간 시세(추후)
