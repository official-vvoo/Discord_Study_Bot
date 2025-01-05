import os
import random
import asyncio
from datetime import datetime
from dotenv import load_dotenv

import discord
from discord.ext import commands

CONST_STR_END_COMMAND = "종료"
CONST_STR_UPDATE_COMMAND = "업데이트"

CONST_DICT_SUMMARY = {
    "no": 0,
    "date": "",
    "participant": [],
    "absentee": [],
    "summary": {}
}

def init():
    global TOKEN
    global THREAD_ID
    global SUMMARY_THREAD_ID
    
    load_dotenv()
    
    TOKEN = os.getenv("token")                                  # bot token
    THREAD_ID = int(os.getenv("channel_id"))                    # Thread id to send announcement time message
    SUMMARY_THREAD_ID = int(os.getenv("summary_channel_id"))    # Thread id to send summary message

# 명령어 프리픽스와 intents 설정 // intents란??
intents = discord.Intents.default()
intents.voice_states = True  # 음성 상태를 모니터링할 수 있도록 허용
intents.messages = True      # 메시지 관련 이벤트를 허용
intents.message_content = True  # 메시지 내용을 읽기 위한 인텐트 활성화
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# 2인 이상 사용자 별 타이머와 업데이트 태스크를 관리하기 위한 딕셔너리
timers = {}
update_tasks = {}

@bot.event # 봇 시작 시
async def on_ready():
    print(f'봇 실행 완료. {bot.user}')
    channel = bot.get_channel(THREAD_ID)
    if not channel:
        print("???")

@bot.event
async def on_voice_state_update(member, before, after):
    user_id = member.id

    # 화면 공유와 마이크가 동시에 켜진 경우 타이머 시작
    if after.self_stream and not after.self_mute:
        if user_id not in update_tasks:  # 이전에 중지된 타이머가 없을 때만 새로운 타이머 시작
            if user_id not in timers:
                # 처음 시작할 때 경과 시간 초기값으로 설정
                timers[user_id] = datetime.now()
            else:
                # 누적 시간을 유지하기 위해 현재 시간부터 계속 계산
                timers[user_id] = datetime.now() - timers[user_id]
            update_tasks[user_id] = asyncio.create_task(update_timer(member))

    # 화면 공유가 꺼질 때 타이머 종료
    elif before.self_stream and not after.self_stream and user_id in timers:
        # 실시간 업데이트 태스크 중지 및 현재까지의 경과 시간 누적
        if user_id in update_tasks:
            update_tasks[user_id].cancel()
            del update_tasks[user_id]
        
        # 현재까지의 경과 시간을 누적하여 기록
        timers[user_id] = datetime.now() - timers[user_id]

async def update_timer(member):
    user_id = member.id
    channel = bot.get_channel(THREAD_ID)
    
    # 초기 메시지 보낸 후, 메시지를 수정하며 실시간 업데이트
    if channel:
        message = await channel.send(f"{member.name} 발표 시간: 0분 0초")

    # 타이머 시작 시간
    start_time = timers[user_id]

    while user_id in timers:
        # 현재까지 누적된 경과 시간을 초 단위로 계산
        elapsed_time = datetime.now() - start_time
        elapsed_seconds = int(elapsed_time.total_seconds())
        minutes, seconds = divmod(elapsed_seconds, 60)

        # 메시지 수정으로 실시간 업데이트
        if channel and message:
            await message.edit(content=f"{member.name} 발표 시간: {minutes}분 {seconds}초")

        # 매 1초마다 정확히 업데이트 (이전 작업의 지연을 보정)
        await asyncio.sleep(1 - (datetime.now().timestamp() % 1))

@bot.command(name='삭제')
async def clear_all_messages_command(ctx):
    """스레드 내 모든 메시지를 삭제합니다."""
    await ctx.send("스레드의 전체 메세지를 삭제할게요")
    channel = bot.get_channel(THREAD_ID)
    if channel is None:
        await ctx.send("지정된 스레드를 찾을 수 없습니다. THREAD_ID를 확인하세요.")
        return

    # 모든 메시지 삭제 작업
    deleted = 0
    async for message in channel.history(limit=None):
        try:
            await message.delete()
            deleted += 1
            await asyncio.sleep(0.5)  # 디스코드 API 제한
        except discord.errors.Forbidden:
            await ctx.send("메시지를 삭제할 권한이 없습니다.")
            return
        except discord.errors.HTTPException as e:
            await ctx.send(f"HTTP 예외 발생: {e}")
            return

@bot.command(name='순서')
async def announce_order(ctx):
    """일반 음성 채팅방에 있는 사람들 기준으로 발표 순서를 정합니다."""
    
    # 음성 채널을 찾습니다. 채널 이름을 '일반'으로 가정
    guild = ctx.guild
    voice_channel = discord.utils.get(guild.voice_channels, name="일반")
    
    # 음성 채널이 없으면 에러 메시지를 보냅니다.
    if voice_channel is None:
        await ctx.send("일반 음성 채널을 찾을 수 없습니다.")
        return
    
    # 음성 채널에 접속해 있는 사용자 목록을 가져옵니다.
    members = [member for member in voice_channel.members if not member.bot]  # 봇 제외
    if not members:
        await ctx.send("현재 일반 음성 채널에 사용자가 없습니다.")
        return
    
    # 발표 순서를 섞습니다.
    random.shuffle(members)
    CONST_DICT_SUMMARY["participant"] = members
    
    # 발표 순서를 문자열로 만듭니다.
    order_message = "# 발표 순서\n" + "\n".join(f"{idx + 1}. {member.display_name}" for idx, member in enumerate(members))
    
    # 지정된 THREAD_ID 채널에 발표 순서를 전송합니다.
    channel = bot.get_channel(THREAD_ID)
    if channel:
        await channel.send(order_message)
    else:
        await ctx.send("지정된 스레드를 찾을 수 없습니다. THREAD_ID를 확인하세요.")

    CONST_DICT_SUMMARY["date"] = datetime.now()

def generate_summary_message():
    '''
    format:
    --------------------------------------
    {N}일차
    일시: {start_time}
    참여자: {members}
    불참자: {members}
    미발표자: {members}

    [진행 내용]
    - member1 : 알고리즘 문제풀이
    - member2 : 공부 내역 1
    - member3 : 알고리즘 문제풀이
    '''
    summary_message = f'{CONST_DICT_SUMMARY["no"]}일차\n일시: {CONST_DICT_SUMMARY["date"].strftime("%Y.%m.%d. %H:%M")}'
    summary_message += '\n참여자: ' + " ".join(x.mention for x in CONST_DICT_SUMMARY["participant"] if x in CONST_DICT_SUMMARY["summary"].keys())
    summary_message += '\n불참자: ' + " ".join(x.mention for x in CONST_DICT_SUMMARY["absentee"])
    summary_message += '\n미발표자: ' + " ".join(x.mention for x in CONST_DICT_SUMMARY["participant"] if x not in CONST_DICT_SUMMARY["summary"].keys())
    summary_message += f'\n\n[진행내용]\n'+'\n'.join(f'- {x.mention} : {CONST_DICT_SUMMARY["summary"][x]}' for x in CONST_DICT_SUMMARY["participant"] if x in CONST_DICT_SUMMARY["summary"].keys())
    return summary_message

@bot.command(name=CONST_STR_END_COMMAND)
async def send_summary(ctx):
    """
    스터디 종료와 함께 스터디 내역 기록
    """
    channel = bot.get_channel(SUMMARY_THREAD_ID)
    
    async for message in channel.history(limit=None):
        if "일차" in message.content:
            CONST_DICT_SUMMARY["no"] = int(message.content.split("일차")[0]) + 1
            break
        
        if message.author in CONST_DICT_SUMMARY["participant"]:
            CONST_DICT_SUMMARY["summary"][message.author] = message.content
            await message.delete()
            await asyncio.sleep(0.5)  # 디스코드 API 제한
            continue

        if message.content==f"!{CONST_STR_END_COMMAND}":
            await message.delete()
            await asyncio.sleep(0.5)  # 디스코드 API 제한
    
    if channel:
        await channel.send(generate_summary_message())
    else:
        await ctx.send("지정된 스레드를 찾을 수 없습니다. THREAD_ID를 확인하세요.")

@bot.command(name=CONST_STR_UPDATE_COMMAND)
async def update_member(ctx):
    """
    스터디 진행 중 인원 변동에 따른 명단 수정
    """
    channel = bot.get_channel(THREAD_ID)
    # !{CONST_STR_UPDATE_COMMAND} 명령 제거
    async for message in channel.history(limit=1):
        if message.content==f"!{CONST_STR_UPDATE_COMMAND}":
            await message.delete()
            await asyncio.sleep(0.5)  # 디스코드 API 제한

    # 음성 채널을 찾습니다. 채널 이름을 '일반'으로 가정
    guild = ctx.guild
    voice_channel = discord.utils.get(guild.voice_channels, name="일반")
    
    # 음성 채널이 없으면 에러 메시지를 보냅니다.
    if voice_channel is None:
        await ctx.send("일반 음성 채널을 찾을 수 없습니다.")
        return
    
    # 음성 채널에 접속해 있는 사용자 목록을 가져옵니다.
    members = [member for member in voice_channel.members if not member.bot]  # 봇 제외
    if not members:
        await ctx.send("현재 일반 음성 채널에 사용자가 없습니다.")
        return
    
    new_members = [x for x in members if x not in CONST_DICT_SUMMARY["participant"]]
    CONST_DICT_SUMMARY["participant"] += new_members
    
    # 발표 순서를 문자열로 만듭니다.
    order_message = "추가 발표\n" + "\n".join(f"{idx + 1}. {member.display_name}" for idx, member in enumerate(new_members))
    
    if channel:
        await channel.send(order_message)
    else:
        await ctx.send("지정된 스레드를 찾을 수 없습니다. THREAD_ID를 확인하세요.")

if __name__ == "__main__":
    init()
    # 봇 실행
    bot.run(TOKEN)