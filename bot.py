import os
import re
import random
import asyncio
from time import time
from urllib.parse import urlparse
import discord
import abbas
from abbas.images import interrogate_clip
import replicate.exceptions
from typing import Optional

token = os.environ['DISCORD_TOKEN']

intents = discord.Intents.default()
intents.message_content = True
tracked_channels: list[int] = []
waiting_task: asyncio.Task = None
future: asyncio.Future = None

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    # await client.change_presence(activity=discord.CustomActivity(name="Bogaty szejk"))
    print(f"Abbas Baszir working as {client.user}")

@client.event
async def on_message(message: discord.Message):
    global waiting_task, future
    if future and not future.done():
        await future
    if os.path.isfile('tracked_channels.txt'):
        try:
            with open('tracked_channels.txt', 'r', encoding='utf-8') as file:
                tracked_channels.clear()
                for line in file:
                    tracked_channels.append(int(line))
        except OSError:
            pass
    if message.author == client.user:
        return
    if not message.channel.id in tracked_channels:
        return
    print(f"@{message.author.display_name}: {message.clean_content}")
    if waiting_task is not None:
        waiting_task.cancel()
    waiting_task = asyncio.create_task(asyncio.sleep(random.uniform(0.5, 4)))
    await waiting_task
    waiting_task = None
    future = asyncio.get_running_loop().create_future()
    messages = []
    tree = await create_message_tree(message)
    print(f"Conversation length for {message.author.display_name}: {len(tree)}")
    for msg in tree:
        username = msg.author.display_name
        if msg.author == client.user:
            username = 'assistant'
        elif username.lower() == 'assistant' or username.lower() == 'system':
            username = 'user'
        messages.append({'sender': username, 'text': msg.clean_content})
    if os.path.isfile('first_message.txt'):
        try:
            with open('first_message.txt', 'r', encoding='utf-8') as file:
                messages.append({'sender': 'assistant', 'text': file.read()})
        except OSError:
            pass
    latest = message.clean_content
    urls: list[str] = re.findall(r'(https?://\S+)', latest)
    for x in message.attachments:
        if x.content_type.startswith("image"):
            urls.append(x.url)
    for url in urls:
        discord_authenticated_url = False
        uridata = urlparse(url)
        if 'discord' in uridata.hostname and uridata.query == '':
            for x in message.embeds:
                if x.type == 'image':
                    url = x.thumbnail.url
                    discord_authenticated_url = True
                    break
                else:
                    print(x.to_dict())
            if not discord_authenticated_url:
                print("ERROR: Failed to fetch authenticated image from Discord. Skipping")
                continue
        caption = await interrogate_clip(url)
        if caption is None:
            continue
        caption = caption.split(',', 1)[0]
        name = uridata.path.split('/')[-1]
        img_text = f"![{caption}]({name})"
        print(img_text)
        if discord_authenticated_url:
            url = url.split('?', 1)[0]
        if url in latest:
            latest = latest.replace(url, img_text)
        else:
            latest += "\n" + img_text
    # message.content = latest
    messages[0]['text'] = latest
    async with message.channel.typing():
        start = time()
        response = await abbas.generate_response(messages)
        context: dict = response[0]
        text: str | replicate.exceptions.ReplicateException = response[1]
        if isinstance(text, replicate.exceptions.ReplicateException):
            if isinstance(text, replicate.exceptions.ModelError):
                print("Retrying because of exception")
                await on_message(message)
            else:
                print("Aborting, ReplicateError is critical")
            return
        print(context)
        print("Abbas Baszir: " + text)
        wpm = 100
        words = len(text.split(' '))
        wait = words/wpm*60
        wait -= time() - start
        print(f"Typing {words} words for {wait} seconds")
        await asyncio.sleep(wait)
    await message.channel.send(text)
    future.set_result(True)

# compiles a list from a linked list of messages (the name "tree" is inaccurate)
# list is in order of newest to oldest
async def create_message_tree(message: discord.Message, max_length: int = 20) -> list[discord.Message]:
    if max_length == 0:
        return
    return [x async for x in message.channel.history(limit=max_length)]

# adding fetched message to cache
# https://github.com/Rapptz/discord.py/issues/8269#issuecomment-1193431224
def _cache_message(message: discord.Message):
    state = message._state
    if state is not None:
        if state._messages is not None and not message in state._messages:
            state._messages.append(message)

client.run(token)