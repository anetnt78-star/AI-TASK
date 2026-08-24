#!/usr/bin/env python3
"""채널 이름으로 채널 ID를 조회하는 헬퍼 스크립트"""

import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()

def find_channel_id(channel_name: str):
    token = os.environ.get('SLACK_BOT_TOKEN', '')
    if not token:
        print('❌ SLACK_BOT_TOKEN이 설정되지 않았습니다.')
        return

    client = WebClient(token=token)
    name = channel_name.lstrip('#')

    try:
        for page in client.conversations_list(limit=200, types='public_channel,private_channel'):
            for ch in page['channels']:
                if ch['name'] == name:
                    print(f'채널 이름: #{ch["name"]}')
                    print(f'채널 ID  : {ch["id"]}')
                    print(f'.env에 아래를 추가하세요:')
                    print(f'SLACK_CHANNEL_ID={ch["id"]}')
                    return
        print(f'채널 "{channel_name}"을 찾을 수 없습니다.')
        print('Bot이 해당 채널의 멤버인지 확인해 주세요.')
    except SlackApiError as e:
        print(f'❌ Slack API 오류: {e.response["error"]}')

if __name__ == '__main__':
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else '00-디지털서비스유닛'
    find_channel_id(name)
