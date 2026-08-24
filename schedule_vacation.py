#!/usr/bin/env python3
"""
Slack 휴가 알림 예약 스케줄러

사용법:
    python schedule_vacation.py 20260821 김지훈 연차
    python schedule_vacation.py 20260821 김지훈 오전 반차
    python schedule_vacation.py 20260821 김지훈 오후 반차
    python schedule_vacation.py 20260821 김지훈 연차 --backup 홍길동
    python schedule_vacation.py              # 대화형 모드 (프롬프트 입력)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, date, timedelta, timezone

import pytz
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

KOREA_TZ = pytz.timezone("Asia/Seoul")

# Monday=0 … Sunday=6
WEEKDAYS_KR = ["월", "화", "수", "목", "금", "토", "일"]

# leave_type → (schedule_hour, schedule_minute)
# 연차 and 오전 반차 both send at 09:30; 오후 반차 sends at 14:30.
LEAVE_SCHEDULE: dict[str, tuple[int, int]] = {
    "연차":      (9, 30),
    "오전 반차": (9, 30),
    "오후 반차": (14, 30),
}

VALID_LEAVE_TYPES: set[str] = set(LEAVE_SCHEDULE.keys())

# Slack requires post_at to be at least 5 minutes in the future.
SLACK_MIN_SCHEDULE_MINUTES = 5

# Slack requires post_at to be at most 120 days in the future.
SLACK_MAX_SCHEDULE_DAYS = 120

MESSAGE_TEMPLATE = (
    "[휴가 공유] {date_str}({weekday}) {leave_type}\n"
    "급한 건은 연락 부탁드립니다.\n"
    "Backup 담당자 : {backup_person} 님"
)


# ─────────────────────────────────────────────────────────────────────────────
# Config loading
# ─────────────────────────────────────────────────────────────────────────────

def load_config() -> tuple[str, str, str]:
    """
    Load required environment variables from .env.
    Returns (slack_bot_token, channel_id, default_backup_person).
    Exits with an error message if required vars are missing.
    """
    load_dotenv()

    token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    channel_id = os.getenv("SLACK_CHANNEL_ID", "").strip()
    default_backup = os.getenv("DEFAULT_BACKUP_PERSON", "고승열").strip()

    errors: list[str] = []
    if not token:
        errors.append("SLACK_BOT_TOKEN 이 설정되지 않았습니다.")
    if not channel_id:
        errors.append("SLACK_CHANNEL_ID 가 설정되지 않았습니다.")

    if errors:
        print("오류: .env 파일 또는 환경 변수를 확인하세요.", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    return token, channel_id, default_backup


# ─────────────────────────────────────────────────────────────────────────────
# Input parsing & validation
# ─────────────────────────────────────────────────────────────────────────────

def parse_date(date_str: str) -> date:
    """
    Parse 'YYYYMMDD' string into a datetime.date.
    Raises ValueError with a Korean error message on bad format.
    """
    try:
        return datetime.strptime(date_str.strip(), "%Y%m%d").date()
    except ValueError:
        raise ValueError(
            f"날짜 형식 오류: '{date_str}'\n"
            "  YYYYMMDD 형식으로 입력하세요 (예: 20260821)."
        )


def parse_leave_type(tokens: list[str]) -> str:
    """
    Join remaining tokens and validate against VALID_LEAVE_TYPES.
    Accepts single-token ('연차') or two-token ('오전 반차', '오후 반차').
    Raises ValueError on unrecognized input.
    """
    joined = " ".join(t.strip() for t in tokens)
    if joined not in VALID_LEAVE_TYPES:
        allowed = ", ".join(f"'{t}'" for t in sorted(VALID_LEAVE_TYPES))
        raise ValueError(
            f"휴가 유형 오류: '{joined}'\n"
            f"  허용된 값: {allowed}"
        )
    return joined


def validate_schedule_time(target_date: date, leave_type: str) -> None:
    """
    Ensure the computed send time satisfies Slack's scheduling constraints:
      - at least 5 minutes in the future
      - at most 120 days in the future
    Raises ValueError with a descriptive message on violation.
    """
    hour, minute = LEAVE_SCHEDULE[leave_type]
    naive_dt = datetime(
        target_date.year, target_date.month, target_date.day, hour, minute
    )
    aware_dt = KOREA_TZ.localize(naive_dt)
    now_kst = datetime.now(KOREA_TZ)

    min_allowed = now_kst + timedelta(minutes=SLACK_MIN_SCHEDULE_MINUTES)
    max_allowed = now_kst + timedelta(days=SLACK_MAX_SCHEDULE_DAYS)

    if aware_dt <= min_allowed:
        raise ValueError(
            f"예약 시간 오류: {aware_dt.strftime('%Y-%m-%d %H:%M KST')} 는 "
            f"현재 시각으로부터 최소 {SLACK_MIN_SCHEDULE_MINUTES}분 이후여야 합니다.\n"
            f"  현재 시각: {now_kst.strftime('%Y-%m-%d %H:%M KST')}"
        )
    if aware_dt > max_allowed:
        raise ValueError(
            f"예약 시간 오류: {aware_dt.strftime('%Y-%m-%d %H:%M KST')} 는 "
            f"현재 시각으로부터 최대 {SLACK_MAX_SCHEDULE_DAYS}일 이내여야 합니다."
        )


def parse_tokens(tokens: list[str]) -> tuple[date, str, str]:
    """
    Parse a flat token list [date_str, name, *leave_type_tokens] into
    (target_date, person_name, leave_type).

    Token layout:
        tokens[0]     → YYYYMMDD
        tokens[1]     → person name (e.g. '김지훈')
        tokens[2:]    → leave type words (e.g. ['연차'] or ['오전', '반차'])

    Raises ValueError on any validation failure.
    """
    if len(tokens) < 3:
        raise ValueError(
            "입력 오류: 날짜, 이름, 휴가 유형을 모두 입력하세요.\n"
            "  예: 20260821 김지훈 연차"
        )

    target_date = parse_date(tokens[0])
    name = tokens[1].strip()
    if not name:
        raise ValueError("이름이 비어 있습니다.")

    leave_type = parse_leave_type(tokens[2:])
    validate_schedule_time(target_date, leave_type)

    return target_date, name, leave_type


# ─────────────────────────────────────────────────────────────────────────────
# Message formatting
# ─────────────────────────────────────────────────────────────────────────────

def format_date_kr(target_date: date) -> tuple[str, str]:
    """
    Returns (date_str, weekday_kr) for the message header.
        date_str    → 'M/D'   e.g. '8/21'
        weekday_kr  → Korean single-char weekday e.g. '금'
    """
    date_str = f"{target_date.month}/{target_date.day}"
    weekday_kr = WEEKDAYS_KR[target_date.weekday()]
    return date_str, weekday_kr


def build_message(target_date: date, leave_type: str, backup_person: str) -> str:
    """
    Render the final Slack message text.

    Example output:
        [휴가 공유] 8/21(금) 연차
        급한 건은 연락 부탁드립니다.
        Backup 담당자 : 고승열 님
    """
    date_str, weekday_kr = format_date_kr(target_date)
    return MESSAGE_TEMPLATE.format(
        date_str=date_str,
        weekday=weekday_kr,
        leave_type=leave_type,
        backup_person=backup_person,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Scheduling logic
# ─────────────────────────────────────────────────────────────────────────────

def compute_post_at(target_date: date, leave_type: str) -> int:
    """
    Compute the Unix timestamp (integer) for the scheduled send time.

    The time is determined by leave type:
        연차 / 오전 반차  → 09:30 KST on target_date
        오후 반차         → 14:30 KST on target_date
    """
    hour, minute = LEAVE_SCHEDULE[leave_type]
    naive_dt = datetime(
        target_date.year, target_date.month, target_date.day, hour, minute, 0
    )
    aware_dt = KOREA_TZ.localize(naive_dt)
    return int(aware_dt.timestamp())


def schedule_slack_message(
    client: WebClient,
    channel_id: str,
    text: str,
    post_at: int,
) -> dict:
    """
    Call Slack chat.scheduleMessage and return the response dict.

    Parameters:
        client      – authenticated WebClient
        channel_id  – Slack channel ID (e.g. 'C0XXXXXXXXX')
        text        – plain-text message body
        post_at     – Unix timestamp (int) for the scheduled send time

    Returns:
        dict with keys: ok, channel, scheduled_message_id, post_at

    Raises:
        SlackApiError – propagated as-is; caller handles user output
    """
    response = client.chat_scheduleMessage(
        channel=channel_id,
        text=text,
        post_at=post_at,
    )
    return dict(response)


# ─────────────────────────────────────────────────────────────────────────────
# Interactive prompts
# ─────────────────────────────────────────────────────────────────────────────

def prompt_for_input() -> list[str]:
    """
    Prompt the user for the main input string and split it into tokens.
    """
    print("Slack 휴가 알림 예약 스케줄러")
    print("─" * 44)
    print("입력 형식: YYYYMMDD 이름 휴가유형")
    print("  예) 20260821 김지훈 연차")
    print("      20260821 김지훈 오전 반차")
    print("      20260821 김지훈 오후 반차")
    print()
    raw = input("입력: ").strip()
    return raw.split()


def prompt_for_backup(default_backup: str) -> str:
    """
    Ask the user for the backup person name, defaulting to default_backup.
    Returns the entered name or the default if the user presses Enter.
    """
    answer = input(f"Backup 담당자 [{default_backup}]: ").strip()
    return answer if answer else default_backup


# ─────────────────────────────────────────────────────────────────────────────
# CLI argument parser
# ─────────────────────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schedule_vacation.py",
        description="Slack 채널에 휴가 알림 메시지를 예약 발송합니다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
예시:
  python schedule_vacation.py 20260821 김지훈 연차
  python schedule_vacation.py 20260821 김지훈 오전 반차
  python schedule_vacation.py 20260821 김지훈 오후 반차 --backup 홍길동
  python schedule_vacation.py          # 대화형 모드
""",
    )
    parser.add_argument(
        "tokens",
        nargs="*",
        metavar="TOKEN",
        help="날짜(YYYYMMDD), 이름, 휴가유형 순서로 입력",
    )
    parser.add_argument(
        "--backup", "-b",
        default=None,
        metavar="이름",
        help="Backup 담당자 이름 (미입력 시 .env의 DEFAULT_BACKUP_PERSON 사용)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Slack API를 실제로 호출하지 않고 메시지 미리보기만 출력",
    )
    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    token, channel_id, default_backup = load_config()

    parser = build_arg_parser()
    args = parser.parse_args()

    # ── 1. Gather tokens and backup person ─────────────────────────────────
    if args.tokens:
        # CLI mode: tokens provided directly
        tokens = args.tokens
        backup_person = args.backup if args.backup else default_backup
    else:
        # Interactive mode: prompt the user
        tokens = prompt_for_input()
        backup_person = (
            args.backup if args.backup else prompt_for_backup(default_backup)
        )

    # ── 2. Parse & validate ────────────────────────────────────────────────
    try:
        target_date, name, leave_type = parse_tokens(tokens)
    except ValueError as exc:
        print(f"\n{exc}", file=sys.stderr)
        sys.exit(1)

    # ── 3. Build message and compute schedule time ─────────────────────────
    message_text = build_message(target_date, leave_type, backup_person)
    post_at = compute_post_at(target_date, leave_type)

    hour, minute = LEAVE_SCHEDULE[leave_type]
    send_time_kst = datetime(
        target_date.year, target_date.month, target_date.day, hour, minute
    )
    send_time_str = send_time_kst.strftime("%Y-%m-%d %H:%M") + " KST"

    # ── 4. Preview ─────────────────────────────────────────────────────────
    date_str, weekday_kr = format_date_kr(target_date)
    print()
    print("─" * 44)
    print(f"  담당자      : {name}")
    print(f"  채널        : #00-디지털서비스유닛  ({channel_id})")
    print(f"  발송 예정   : {send_time_str}")
    print(f"  Backup      : {backup_person} 님")
    if args.dry_run:
        print("  모드        : [DRY RUN] – API 호출 없음")
    print()
    print("[ 메시지 미리보기 ]")
    print("─" * 44)
    print(message_text)
    print("─" * 44)

    # ── 5. Confirm ─────────────────────────────────────────────────────────
    try:
        confirm = input("\n위 내용으로 예약하시겠습니까? (y/N): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n취소되었습니다.")
        sys.exit(0)

    if confirm != "y":
        print("취소되었습니다.")
        sys.exit(0)

    # ── 6. Dry-run exit ────────────────────────────────────────────────────
    if args.dry_run:
        print("\n[DRY RUN] Slack API 호출을 건너뜁니다.")
        print(f"  post_at (Unix) : {post_at}")
        sys.exit(0)

    # ── 7. Schedule via Slack API ──────────────────────────────────────────
    client = WebClient(token=token)
    try:
        response = schedule_slack_message(client, channel_id, message_text, post_at)
    except SlackApiError as exc:
        error_code = exc.response.get("error", "unknown_error")
        print(f"\nSlack API 오류 ({error_code})", file=sys.stderr)
        _print_slack_error_hint(error_code)
        sys.exit(1)

    # ── 8. Success output ──────────────────────────────────────────────────
    scheduled_id = response.get("scheduled_message_id", "N/A")
    print()
    print("예약 완료!")
    print(f"  scheduled_message_id : {scheduled_id}")
    print(f"  채널                 : {channel_id}")
    print(f"  발송 예정 시간       : {send_time_str}")
    print()
    print("예약된 메시지 목록 확인:")
    print("  https://api.slack.com/methods/chat.scheduledMessages.list")


def _print_slack_error_hint(error_code: str) -> None:
    """Print a context-specific hint for common Slack API errors."""
    hints: dict[str, str] = {
        "not_in_channel": (
            "봇이 채널에 초대되지 않았습니다.\n"
            "  → Slack에서 #00-디지털서비스유닛 채널에 봇을 /invite 해주세요."
        ),
        "channel_not_found": (
            "채널 ID를 찾을 수 없습니다.\n"
            "  → .env의 SLACK_CHANNEL_ID 값을 확인하세요 (C 로 시작하는 11자리 ID)."
        ),
        "invalid_auth": (
            "토큰이 유효하지 않습니다.\n"
            "  → .env의 SLACK_BOT_TOKEN (xoxb-...) 값을 확인하세요."
        ),
        "time_in_past": (
            "예약 시간이 과거입니다.\n"
            "  → Slack은 현재 시각으로부터 최소 5분 이후만 예약 가능합니다."
        ),
        "time_too_far": (
            "예약 시간이 너무 멀리 있습니다.\n"
            "  → Slack은 최대 120일 이내만 예약 가능합니다."
        ),
        "missing_scope": (
            "봇에 chat:write 권한이 없습니다.\n"
            "  → Slack App 설정 → OAuth & Permissions → Bot Token Scopes 에서\n"
            "    'chat:write' 스코프를 추가하세요."
        ),
    }
    hint = hints.get(error_code)
    if hint:
        print(f"  힌트: {hint}", file=sys.stderr)


if __name__ == "__main__":
    main()
