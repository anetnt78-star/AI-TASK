# Slack 휴가 알림 예약 스케줄러

`#00-디지털서비스유닛` 채널에 휴가 알림 메시지를 Slack **예약 발송**하는 CLI 도구입니다.  
`chat.scheduleMessage` API를 사용하여 지금 당장 전송하지 않고, 지정된 시각에 자동으로 발송합니다.

---

## 빠른 시작

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 SLACK_BOT_TOKEN, SLACK_CHANNEL_ID 를 실제 값으로 교체

# 3. 실행
python schedule_vacation.py 20260821 김지훈 연차
```

---

## 설치 및 Slack 앱 준비

### 1) Slack 앱 생성

1. https://api.slack.com/apps → **Create New App** → **From scratch**
2. 앱 이름 입력 (예: `휴가알림봇`), 워크스페이스 선택 후 생성

### 2) Bot Token Scopes 설정

**OAuth & Permissions → Bot Token Scopes** 에서 아래 스코프 추가:

| 스코프 | 용도 |
|--------|------|
| `chat:write` | 채널에 메시지 예약 발송 |
| `channels:read` | `find_channel_id.py` 로 채널 ID 조회 (선택사항) |

### 3) 앱 설치 및 토큰 복사

**OAuth & Permissions → Install to Workspace** → 설치 후  
**Bot User OAuth Token** (`xoxb-...`) 을 복사

### 4) 채널 ID 확인

채널 이름이 아닌 **채널 ID** (예: `C0XXXXXXXXX`)가 필요합니다.

```bash
# find_channel_id.py 로 조회
python find_channel_id.py 00-디지털서비스유닛
```

또는 Slack 앱에서: 채널 이름 우클릭 → **채널 세부 정보 보기** → 스크롤 최하단에서 채널 ID 확인

### 5) 봇을 채널에 초대

```
/invite @휴가알림봇
```

> 봇이 채널에 없으면 `not_in_channel` 오류가 발생합니다.

---

## 환경 변수 (.env)

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `SLACK_BOT_TOKEN` | 필수 | `xoxb-` 로 시작하는 Bot Token |
| `SLACK_CHANNEL_ID` | 필수 | `C` 로 시작하는 11자리 채널 ID |
| `DEFAULT_BACKUP_PERSON` | 선택 | Backup 담당자 기본값 (기본: `고승열`) |

---

## 사용법

### CLI 모드

```bash
# 연차 (9:30 발송)
python schedule_vacation.py 20260821 김지훈 연차

# 오전 반차 (9:30 발송)
python schedule_vacation.py 20260821 김지훈 오전 반차

# 오후 반차 (14:30 발송)
python schedule_vacation.py 20260821 김지훈 오후 반차

# Backup 담당자 지정
python schedule_vacation.py 20260821 김지훈 연차 --backup 홍길동

# 실제 API 호출 없이 미리보기만 (개발/테스트용)
python schedule_vacation.py 20260821 김지훈 연차 --dry-run
```

### 대화형 모드

```bash
python schedule_vacation.py
```

프롬프트가 표시되면 입력:
```
입력: 20260821 김지훈 연차
Backup 담당자 [고승열]:          ← Enter 시 기본값 사용
```

---

## 예약 시각 규칙

| 휴가 유형 | 발송 시각 (KST) |
|-----------|----------------|
| 연차      | 09:30          |
| 오전 반차  | 09:30          |
| 오후 반차  | 14:30          |

---

## 메시지 형식

```
[휴가 공유] 8/21(금) 연차
급한 건은 연락 부탁드립니다.
Backup 담당자 : 고승열 님
```

---

## 실행 예시 (전체 터미널 출력)

```
$ python schedule_vacation.py 20260821 김지훈 연차

────────────────────────────────────────────
  담당자      : 김지훈
  채널        : #00-디지털서비스유닛  (C0XXXXXXXXX)
  발송 예정   : 2026-08-21 09:30 KST
  Backup      : 고승열 님

[ 메시지 미리보기 ]
────────────────────────────────────────────
[휴가 공유] 8/21(금) 연차
급한 건은 연락 부탁드립니다.
Backup 담당자 : 고승열 님
────────────────────────────────────────────

위 내용으로 예약하시겠습니까? (y/N): y

예약 완료!
  scheduled_message_id : Q1298393284
  채널                 : C0XXXXXXXXX
  발송 예정 시간       : 2026-08-21 09:30 KST

예약된 메시지 목록 확인:
  https://api.slack.com/methods/chat.scheduledMessages.list
```

---

## Slack chat.scheduleMessage API 상세

| 항목 | 내용 |
|------|------|
| API 메서드 | `chat.scheduleMessage` |
| SDK 호출 | `client.chat_scheduleMessage(channel=..., text=..., post_at=...)` |
| `channel` | 채널 ID (문자열, 예: `C0XXXXXXXXX`) |
| `text` | 메시지 본문 (문자열) |
| `post_at` | 발송 예정 시각의 **Unix 타임스탬프 (정수)** |
| 제약: 최소 | 현재 시각 기준 **5분 이후** |
| 제약: 최대 | 현재 시각 기준 **120일 이내** |
| 반환값 | `ok`, `channel`, `scheduled_message_id`, `post_at` |
| 필요 스코프 | `chat:write` |

`post_at` 계산 방법:
```python
import pytz
from datetime import datetime

korea_tz = pytz.timezone("Asia/Seoul")
naive_dt = datetime(2026, 8, 21, 9, 30, 0)           # 09:30 KST
aware_dt = korea_tz.localize(naive_dt)                # timezone 붙이기
post_at  = int(aware_dt.timestamp())                  # Unix timestamp (int)
```

---

## 입력 유효성 검사

| 검사 항목 | 조건 |
|-----------|------|
| 날짜 형식 | `YYYYMMDD` 8자리, 유효한 날짜여야 함 |
| 휴가 유형 | `연차`, `오전 반차`, `오후 반차` 중 하나 |
| 예약 시각 | 현재 시각 + 5분 이후여야 함 (Slack 제약) |
| 예약 시각 | 현재 시각 + 120일 이내여야 함 (Slack 제약) |

---

## 흔한 오류 해결

| Slack 오류 코드 | 원인 | 해결 |
|----------------|------|------|
| `not_in_channel` | 봇이 채널에 없음 | `/invite @봇이름` |
| `channel_not_found` | 채널 ID 오류 | `.env`의 `SLACK_CHANNEL_ID` 재확인 |
| `invalid_auth` | 토큰 오류 | `.env`의 `SLACK_BOT_TOKEN` 재확인 |
| `time_in_past` | 과거 시각 예약 시도 | 5분 이후 시각 필요 |
| `time_too_far` | 120일 초과 | 120일 이내 날짜로 변경 |
| `missing_scope` | `chat:write` 스코프 없음 | Slack App 설정에서 스코프 추가 후 재설치 |

---

## 파일 구조

```
.
├── schedule_vacation.py   # 메인 스크립트
├── find_channel_id.py     # 채널 ID 조회 보조 스크립트
├── requirements.txt       # Python 패키지 목록
├── .env.example           # 환경 변수 템플릿
├── .env                   # 실제 환경 변수 (git 제외)
└── .gitignore
```
