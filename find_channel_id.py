#!/usr/bin/env python3
"""
채널 이름으로 Slack 채널 ID를 조회하는 보조 스크립트.

사용법:
    python find_channel_id.py 00-디지털서비스유닛
    python find_channel_id.py          # 모든 채널 목록 출력
"""

import sys
import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()

token = os.getenv("SLACK_BOT_TOKEN", "").strip()
if not token:
    print("오류: SLACK_BOT_TOKEN 이 설정되지 않았습니다.", file=sys.stderr)
    sys.exit(1)

search_name = sys.argv[1].lstrip("#") if len(sys.argv) > 1 else None

client = WebClient(token=token)

try:
    channels = []
    cursor = None
    while True:
        kwargs = {"limit": 200, "exclude_archived": True}
        if cursor:
            kwargs["cursor"] = cursor
        resp = client.conversations_list(**kwargs)
        channels.extend(resp["channels"])
        cursor = resp.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            break
except SlackApiError as exc:
    print(f"Slack API 오류: {exc.response['error']}", file=sys.stderr)
    sys.exit(1)

if search_name:
    matched = [c for c in channels if search_name.lower() in c["name"].lower()]
    if not matched:
        print(f"'{search_name}' 이름이 포함된 채널을 찾을 수 없습니다.")
        sys.exit(1)
    for c in matched:
        print(f"  채널명: #{c['name']}")
        print(f"  채널ID: {c['id']}")
        print()
else:
    print(f"{'채널명':<40} {'채널ID'}")
    print("─" * 55)
    for c in sorted(channels, key=lambda x: x["name"]):
        print(f"  #{c['name']:<38} {c['id']}")
