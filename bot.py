import os
import re
from urllib.parse import urlparse
import discord
import abbas
from abbas.images import interrogate_clip
import abbas.mysql
from abbas.message import Message
import replicate.exceptions
from typing import Optional

token = os.environ['DISCORD_TOKEN']

intents = discord.Intents.default()
intents.message_content = True

cache: dict[int, Message] = {}

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    await abbas.mysql.connect()
    await client.change_presence(activity=discord.CustomActivity(name="Bogaty szejk"))
    print(f"Abbas Baszir working as {client.user}")

@client.event
async def on_message(message: discord.Message):
    if not client.user in message.mentions:
        return
    print(f"@{message.author.display_name}: {message.clean_content}")
                
    async with message.channel.typing():
        reply: Optional[discord.Message] = None
        if not message.reference and message.clean_content == f"@{message.mentions[0].display_name}":
            if os.path.isfile('first_message.txt'):
                try:
                    with open('first_message.txt', 'r', encoding='utf-8') as file:
                        text = file.read()
                    reply = await message.reply(text)
                    msg = Message(reply.id, None, 'assistant', text)
                    await abbas.mysql.insert_message(msg)
                    cache[reply.id] = msg
                    return
                except OSError:
                    pass
        messages = await create_message_list(message)
        print(f"Conversation length for {message.author.display_name}: {len(messages)}")
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
        messages[0].text = latest
        response = await abbas.generate_response(messages)
    text: str | replicate.exceptions.ReplicateException = response[1]
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
        reply = await message.reply(text)
        msg = Message(reply.id, message.id, 'assistant', text)
        await abbas.mysql.insert_message(msg)
        cache[reply.id] = msg
    else:
        await reply.edit(content=text)

class ExceptView(discord.ui.View):
    def __init__(self, message: discord.Message):
        super().__init__(timeout=60)
        self.message = message
    
    @discord.ui.button(label="Retry", style=discord.ButtonStyle.red)
    async def retry(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.pong()
        await on_message(self.message)


async def create_message_list(message: discord.Message) -> list[Message]:
    """
    Create a list of Message objects parenting a Discord message.

    This function will try to retrieve the message list from MySQL. If they don't exist in the database, it will fetch them from Discord.
    It will automatically update the database and uses caching to prevent unnecessary database calls.
    """
    # Resolve message list from cache
    if message.id in cache:
        msg = cache[message.id]
        parent = msg.parent
        messages = [msg]
        while parent:
            msg = cache[parent]
            parent = msg.parent
            messages.append(msg)
        return messages

    ref = message.reference.message_id if message.reference else None
    username = message.author.display_name
    if message.author == client.user:
        username = 'assistant'
    elif username.lower() == 'assistant' or username.lower() == 'system':
        username = 'user'
    messages = [Message(message.id, ref, username, message.clean_content)]
    await abbas.mysql.insert_message(messages[0])
    cache[message.id] = messages[0]
    if not ref:
        return messages
    # Fetch messages from MySQL
    messages += await abbas.mysql.fetch_message_list(ref)

    if len(messages) == 1:
        # Message list not in database. Must be legacy, fetch them from Discord
        print("Fetching message list from Discord (legacy system)")
        msgs = await legacy_create_message_tree(message)
        for x in msgs[1:]:
            ref = x.reference.message_id if x.reference else None
            username = x.author.display_name
            if x.author == client.user:
                username = 'assistant'
            elif username.lower() == 'assistant' or username.lower() == 'system':
                username = 'user'
            messages.append(Message(x.id, ref, username, x.clean_content))
        await abbas.mysql.insert_messages(messages)
    
    # Add messages to cache
    for x in messages:
        if not x in cache:
            cache[x.id] = x
    
    return messages
# compiles a list from a linked list of messages (the name "tree" is inaccurate)
# list is in order of newest to oldest
async def legacy_create_message_tree(message: discord.Message, max_length: int = 20) -> list[discord.Message]:
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

client.run(token)