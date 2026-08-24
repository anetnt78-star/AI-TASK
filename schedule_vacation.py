#!/usr/bin/env python3
"""Slack 휴가 알림 예약 전송 스크립트"""

import argparse
import os
import sys
from datetime import datetime, date, timedelta

import pytz
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()

# ── 상수 ──────────────────────────────────────────────────────────────
WEEKDAYS_KR = ['월', '화', '수', '목', '금', '토', '일']
VALID_LEAVE_TYPES = ['연차', '오전 반차', '오후 반차']
CHANNEL_DISPLAY = '#00-디지털서비스유닛'
KST = pytz.timezone('Asia/Seoul')

SCHEDULE_TIMES = {
    '연차': (9, 30),
    '오전 반차': (9, 30),
    '오후 반차': (14, 30),
}

SLACK_ERROR_HINTS = {
    'time_in_past': '예약 시간이 현재 시각보다 과거입니다. 최소 5분 이후로 설정해 주세요.',
    'time_too_far': '예약 시간이 120일을 초과합니다.',
    'channel_not_found': '채널을 찾을 수 없습니다. SLACK_CHANNEL_ID를 확인해 주세요.',
    'not_in_channel': 'Bot이 채널에 초대되지 않았습니다. /invite @Bot 명령으로 초대해 주세요.',
    'invalid_auth': 'Slack 토큰이 올바르지 않습니다. SLACK_BOT_TOKEN을 확인해 주세요.',
}

# ── 설정 로드 ──────────────────────────────────────────────────────────
def load_config():
    token = os.environ.get('SLACK_BOT_TOKEN', '')
    channel_id = os.environ.get('SLACK_CHANNEL_ID', '')
    default_backup = os.environ.get('DEFAULT_BACKUP_PERSON', '고승열')
    return token, channel_id, default_backup

# ── 파싱 및 검증 ────────────────────────────────────────────────────────
def parse_date(date_str: str) -> date:
    try:
        return datetime.strptime(date_str, '%Y%m%d').date()
    except ValueError:
        print(f'❌ 날짜 형식이 올바르지 않습니다: {date_str!r}')
        print('   올바른 형식: YYYYMMDD (예: 20260821)')
        sys.exit(1)

def parse_leave_type(tokens: list) -> str:
    leave = ' '.join(tokens)
    if leave not in VALID_LEAVE_TYPES:
        print(f'❌ 올바르지 않은 휴가 종류: {leave!r}')
        print(f'   사용 가능: {", ".join(VALID_LEAVE_TYPES)}')
        sys.exit(1)
    return leave

def validate_schedule_time(post_at: int):
    now_ts = int(datetime.now().timestamp())
    min_ts = now_ts + 5 * 60         # +5분
    max_ts = now_ts + 120 * 24 * 3600  # +120일
    if post_at < min_ts:
        print('❌ 예약 시간이 너무 가깝습니다. 현재 시각보다 최소 5분 이후여야 합니다.')
        sys.exit(1)
    if post_at > max_ts:
        print('❌ 예약 시간이 너무 멉니다. 현재로부터 최대 120일 이내여야 합니다.')
        sys.exit(1)

# ── 포매팅 ──────────────────────────────────────────────────────────────
def format_date_kr(target_date: date) -> str:
    weekday = WEEKDAYS_KR[target_date.weekday()]
    return f'{target_date.month}/{target_date.day}({weekday})'

def build_message(target_date: date, leave_type: str, backup_person: str) -> str:
    date_str = format_date_kr(target_date)
    return (
        f'[휴가 공유] {date_str} {leave_type}\n'
        f'급한 건은 연락 부탁드립니다.\n'
        f'Backup 담당자 : {backup_person} 님'
    )

# ── 스케줄링 ────────────────────────────────────────────────────────────
def compute_post_at(target_date: date, leave_type: str) -> int:
    hour, minute = SCHEDULE_TIMES[leave_type]
    naive_dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute)
    kst_dt = KST.localize(naive_dt)
    return int(kst_dt.timestamp())

def schedule_slack_message(client: WebClient, channel_id: str, text: str, post_at: int) -> dict:
    return client.chat_scheduleMessage(
        channel=channel_id,
        text=text,
        post_at=post_at,
    )

# ── 대화형 입력 ────────────────────────────────────────────────────────
def prompt_for_input() -> list:
    print('입력 형식: YYYYMMDD 이름 휴가종류')
    print('예시: 20260821 김지훈 연차')
    raw = input('입력: ').strip()
    return raw.split()

def prompt_for_backup(default_backup: str) -> str:
    answer = input(f'Backup 담당자 [{default_backup}]: ').strip()
    return answer if answer else default_backup

# ── 메인 ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='Slack 휴가 알림 예약 전송')
    parser.add_argument('tokens', nargs='*', help='YYYYMMDD 이름 휴가종류')
    parser.add_argument('--backup', '-b', default=None, help='Backup 담당자 이름')
    parser.add_argument('--dry-run', action='store_true', help='API 호출 없이 미리보기만 출력')
    args = parser.parse_args()

    token, channel_id, default_backup = load_config()

    # 입력 처리
    tokens = args.tokens if args.tokens else prompt_for_input()
    if len(tokens) < 3:
        print('❌ 입력이 부족합니다. YYYYMMDD 이름 휴가종류 형식으로 입력해 주세요.')
        sys.exit(1)

    date_str = tokens[0]
    name = tokens[1]
    leave_tokens = tokens[2:]

    target_date = parse_date(date_str)
    leave_type = parse_leave_type(leave_tokens)
    post_at = compute_post_at(target_date, leave_type)
    validate_schedule_time(post_at)

    # Backup 담당자
    if args.backup:
        backup_person = args.backup
    elif not args.tokens:  # 대화형 모드일 때만 프롬프트
        backup_person = prompt_for_backup(default_backup)
    else:
        backup_person = default_backup

    message = build_message(target_date, leave_type, backup_person)
    scheduled_dt = datetime.fromtimestamp(post_at, tz=KST)
    hour, _ = SCHEDULE_TIMES[leave_type]

    # 미리보기 출력
    print()
    print('─' * 44)
    print(f'  담당자      : {name}')
    print(f'  채널        : {CHANNEL_DISPLAY}')
    print(f'  발송 예정   : {scheduled_dt.strftime("%Y-%m-%d %H:%M")} KST')
    print(f'  Backup      : {backup_person} 님')
    print()
    print('[ 메시지 미리보기 ]')
    print('─' * 44)
    print(message)
    print('─' * 44)

    if args.dry_run:
        print()
        print('✅ [드라이런] API 호출을 건너뜁니다.')
        return

    # 확인 프롬프트
    confirm = input('\n위 내용으로 예약하시겠습니까? (y/N): ').strip().lower()
    if confirm != 'y':
        print('취소되었습니다.')
        return

    # API 호출
    if not token or not channel_id:
        print('❌ SLACK_BOT_TOKEN 또는 SLACK_CHANNEL_ID가 설정되지 않았습니다.')
        print('   .env 파일을 확인해 주세요.')
        sys.exit(1)

    try:
        client = WebClient(token=token)
        response = schedule_slack_message(client, channel_id, message, post_at)
        msg_id = response.get('scheduled_message_id', 'N/A')
        print()
        print('🎉 예약 완료!')
        print(f'  scheduled_message_id : {msg_id}')
        print(f'  채널                 : {channel_id}')
        print(f'  발송 예정 시간       : {scheduled_dt.strftime("%Y-%m-%d %H:%M")} KST')
    except SlackApiError as e:
        error_code = e.response.get('error', 'unknown')
        hint = SLACK_ERROR_HINTS.get(error_code, f'Slack API 오류: {error_code}')
        print(f'❌ {hint}')
        sys.exit(1)

if __name__ == '__main__':
    main()
