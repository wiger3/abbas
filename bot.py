import os
import re
from urllib.parse import urlparse
import discord
import abbas
from abbas.images import interrogate_clip
import abbas.mysql
import replicate.exceptions
from typing import Optional

token = os.environ['DISCORD_TOKEN']

intents = discord.Intents.default()
intents.message_content = True

cache: dict[int, dict] = {}

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    await client.change_presence(activity=discord.CustomActivity(name="Bogaty szejk"))
    print(f"Abbas Baszir working as {client.user}")

@client.event
async def on_message(message: discord.Message):
    if not client.user in message.mentions:
        return
    print(f"@{message.author.display_name}: {message.clean_content}")
                
    async with message.channel.typing():
        reply: Optional[discord.Message] = None
        messages = []
        tree = await create_message_tree(message)
        print(f"Conversation length for {message.author.display_name}: {len(tree)}")
        for msg in tree:
            if msg.id in cache:
                messages.append(cache[msg.id])
                continue
            username = msg.author.display_name
            if msg.author == client.user:
                username = 'assistant'
            elif username.lower() == 'assistant' or username.lower() == 'system':
                username = 'user'
            x = {'sender': username, 'text': msg.clean_content}
            cache[msg.id] = x
            messages.append(x)
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
            if not abbas.mysql.can_user_interrogate(message.author.id):
                reply = await message.reply(embed=discord.Embed(
                    title="Image recognition",
                    description="Wykorzystałeś swój dzisiejszy limit obrazków (3/3)\nWysłane obrazki nie będą rozpoznawane."
                ))
                break
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
            abbas.mysql.decrease_clip_left(message.author.id)
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
        cache[message.id]['text'] = latest
        messages[0]['text'] = latest
        response = await abbas.generate_response(messages)
    context: dict = response[0]
    text: str | replicate.exceptions.ReplicateException = response[1]
    print(context)
    if isinstance(text, replicate.exceptions.ReplicateException):
        print("Responding with exception embed")
        e_type = "Unknown exception"
        if isinstance(text, replicate.exceptions.ReplicateError):
            e_type = text.type
        elif isinstance(text, replicate.exceptions.ModelError):
            e_type = "Prediction failed, please try again"
        await message.reply(embed=discord.Embed(
            title="Wystąpił błąd",
            description="Podczas odpowiadania wystąpił następujący błąd: " + e_type
        ), view=ExceptView(message))
        return
    print("Abbas Baszir: " + text)
    if reply is None:
        await message.reply(text)
    else:
        await reply.edit(content=text)

class ExceptView(discord.ui.View):
    def __init__(self, message: discord.Message):
        super().__init__(timeout=60)
        self.message = message
    
    @discord.ui.button(label="Retry", style=discord.ButtonStyle.red)
    async def retry(self, button: discord.Button, interaction: discord.Interaction):
        await on_message(self.message)
        self.stop()

# compiles a list from a linked list of messages (the name "tree" is inaccurate)
# list is in order of newest to oldest
async def create_message_tree(message: discord.Message, max_length: int = 20) -> list[discord.Message]:
    if max_length == 0:
        return
    max_length -= 1
    
    messages = [message]

    msg = message
    ref = msg.reference
    while max_length != 0 and ref is not None and ref.message_id is not None:
        if ref.cached_message is None:
            print(f"Fetching message {ref.message_id}")
            if ref.channel_id == msg.channel.id:
                channel = msg.channel
            else:
                channel = client.get_channel(ref.channel_id)
                if channel is None:
                    channel = await client.fetch_channel(ref.channel_id)
            try:
                msg = await channel.fetch_message(ref.message_id)
                _cache_message(msg)
            except discord.NotFound:
                print(f"WARNING: Message {ref.message_id} doesn't exist! Message tree will be incomplete")
                break
        else:
            # print(f"Resolved message {ref.message_id} from cache")
            msg = ref.cached_message
        ref = msg.reference
        if not msg.clean_content:
            continue
        messages.append(msg)
        max_length -= 1
    return messages

# adding fetched message to cache
# https://github.com/Rapptz/discord.py/issues/8269#issuecomment-1193431224
def _cache_message(message: discord.Message):
    state = message._state
    if state is not None:
        if state._messages is not None and not message in state._messages:
            state._messages.append(message)

client.run(token)