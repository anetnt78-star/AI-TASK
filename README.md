# Slack 휴가 알림 예약 전송 스크립트

`#00-디지털서비스유닛` 채널에 휴가 알림 메시지를 Slack **예약 발송**하는 CLI 도구입니다.

---

## 기능 소개

- `chat.scheduleMessage` API를 사용해 지정 날짜 및 시각에 자동으로 휴가 알림 메시지 발송
- 연차 / 오전 반차 / 오후 반차 세 가지 휴가 유형 지원
- CLI 인수 모드 및 대화형(interactive) 모드 지원
- `--dry-run` 옵션으로 API 호출 없이 메시지 미리보기 가능
- `--backup` 옵션으로 Backup 담당자를 실행 시마다 지정 가능

**메시지 형식 예시:**
```
[휴가 공유] 8/21(금) 연차
급한 건은 연락 부탁드립니다.
Backup 담당자 : 고승열 님
```

**예약 시각 규칙:**

| 휴가 유형 | 발송 시각 (KST) |
|-----------|----------------|
| 연차      | 09:30          |
| 오전 반차  | 09:30          |
| 오후 반차  | 14:30          |

---

## 사전 준비 (Slack Bot 생성)

### 1) Slack 앱 생성

1. https://api.slack.com/apps → **Create New App** → **From scratch**
2. 앱 이름 입력 (예: `휴가알림봇`), 워크스페이스 선택 후 생성

### 2) 필요한 OAuth Scope 추가

**OAuth & Permissions → Bot Token Scopes** 에서 아래 스코프 추가:

| 스코프 | 용도 |
|--------|------|
| `chat:write` | 채널에 메시지 예약 발송 |
| `chat:write.public` | 봇이 채널 멤버가 아니어도 발송 가능 |
| `channels:read` | `find_channel_id.py` 로 공개 채널 ID 조회 |
| `groups:read` | `find_channel_id.py` 로 비공개 채널 ID 조회 |

### 3) 앱 설치 및 토큰 복사

**OAuth & Permissions → Install to Workspace** → 설치 후  
**Bot User OAuth Token** (`xoxb-...`) 을 복사

---

## 설치 방법

```bash
# 1. 패키지 설치
pip install -r requirements.txt

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 실제 값 입력
```

`.env` 파일 설정:

```
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_CHANNEL_ID=C0XXXXXXXXX
DEFAULT_BACKUP_PERSON=고승열
```

---

## 채널 ID 조회 방법

채널 이름이 아닌 **채널 ID** (예: `C0XXXXXXXXX`)가 필요합니다.

```bash
python find_channel_id.py 00-디지털서비스유닛
```

출력 예시:
```
채널 이름: #00-디지털서비스유닛
채널 ID  : C0XXXXXXXXX
.env에 아래를 추가하세요:
SLACK_CHANNEL_ID=C0XXXXXXXXX
```

또는 Slack 앱에서: 채널 이름 우클릭 → **채널 세부 정보 보기** → 스크롤 최하단에서 채널 ID 확인

> 봇이 채널에 없으면 `not_in_channel` 오류가 발생합니다. Slack에서 `/invite @휴가알림봇` 으로 초대하세요.

---

## 사용 방법

### CLI 모드

```bash
# 연차 (9:30 KST 발송)
python schedule_vacation.py 20260821 김지훈 연차

# 오전 반차 (9:30 KST 발송)
python schedule_vacation.py 20260821 김지훈 오전 반차

# 오후 반차 (14:30 KST 발송)
python schedule_vacation.py 20260821 김지훈 오후 반차

# Backup 담당자 지정
python schedule_vacation.py 20260821 김지훈 오전 반차 --backup 홍길동

# API 호출 없이 미리보기만 출력
python schedule_vacation.py 20260821 김지훈 오후 반차 --dry-run
```

### 대화형 모드 (인수 없이 실행)

```bash
python schedule_vacation.py
```

프롬프트 예시:
```
입력 형식: YYYYMMDD 이름 휴가종류
예시: 20260821 김지훈 연차
입력: 20260821 김지훈 연차
Backup 담당자 [고승열]:          ← Enter 시 기본값 사용
```

### 실행 예시 (전체 출력)

```
$ python schedule_vacation.py 20260821 김지훈 연차

────────────────────────────────────────────
  담당자      : 김지훈
  채널        : #00-디지털서비스유닛
  발송 예정   : 2026-08-21 09:30 KST
  Backup      : 고승열 님

[ 메시지 미리보기 ]
────────────────────────────────────────────
[휴가 공유] 8/21(금) 연차
급한 건은 연락 부탁드립니다.
Backup 담당자 : 고승열 님
────────────────────────────────────────────

위 내용으로 예약하시겠습니까? (y/N): y

🎉 예약 완료!
  scheduled_message_id : Q1298393284
  채널                 : C0XXXXXXXXX
  발송 예정 시간       : 2026-08-21 09:30 KST
```

---

## 예약 취소 방법

Slack에서 직접 취소할 수 있습니다:

1. Slack 앱에서 해당 채널로 이동
2. 메시지 입력란 왼쪽의 **번개 아이콘(⚡)** 또는 시계 아이콘 클릭
3. **Scheduled messages** 탭에서 예약된 메시지 확인 후 삭제

또는 Slack API를 사용:
```
POST https://slack.com/api/chat.deleteScheduledMessage
  channel: <채널ID>
  scheduled_message_id: <예약ID>
```

---

## 파일 구조

```
.
├── schedule_vacation.py   # 메인 스크립트
├── find_channel_id.py     # 채널 ID 조회 헬퍼 스크립트
├── requirements.txt       # Python 패키지 목록
├── .env.example           # 환경 변수 템플릿
├── .env                   # 실제 환경 변수 (git 제외)
└── .gitignore
```

---

## 흔한 오류 해결

| Slack 오류 코드 | 원인 | 해결 |
|----------------|------|------|
| `not_in_channel` | 봇이 채널에 없음 | `/invite @봇이름` |
| `channel_not_found` | 채널 ID 오류 | `.env`의 `SLACK_CHANNEL_ID` 재확인 |
| `invalid_auth` | 토큰 오류 | `.env`의 `SLACK_BOT_TOKEN` 재확인 |
| `time_in_past` | 과거 시각 예약 시도 | 5분 이후 시각 필요 |
| `time_too_far` | 120일 초과 | 120일 이내 날짜로 변경 |
