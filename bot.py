import os
import time
import asyncio
import threading
import discord
from discord.ext import voice_recv
import discord.ext.voice_recv
import abbas.voice
from abbas.message import Message
import discord.ext

class VoiceClient(voice_recv.VoiceRecvClient):
    def __init__(self, client: discord.Client, channel: discord.abc.Connectable):
        super().__init__(client, channel)
        self.msg: discord.Message = None

token = os.environ['DISCORD_TOKEN']

intents = discord.Intents.default()
intents.message_content = True

voice: VoiceClient = None
cache: dict[int, Message] = {}

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    await client.change_presence(activity=discord.CustomActivity(name="🎙 Voice test"))
    print(f"Abbas Baszir working as {client.user}")

@client.event
async def on_message(message: discord.Message):
    global voice
    if message.author == client.user:
        return
    if not message.content.startswith(';'):
        return
    args = message.content[1:].split(' ')
    cmd = args[0]

    match cmd:
        case 'join':
            vstate = message.author.voice
            if vstate is None or vstate.channel is None:
                await message.reply("You are not in a voice channel!")
                return
            voice = await vstate.channel.connect(cls=VoiceClient)
        case 'leave':
            if voice and voice.is_connected():
                await voice.disconnect()
        case 'say':
            if not voice or not voice.is_connected():
                await message.reply("I am not in a voice channel")
                return
            text = " ".join(args[1:])
            # with open('audio.pcm', 'rb') as file:
            #     chunk = file.read()
            voice.play(ChunkedPCMAudio(text))
        case 'listen':
            if not voice or not voice.is_connected():
                await message.reply("I am not in a voice channel")
                return
            reply = await message.channel.send(embed=discord.Embed(title="Abbas Baszir voice test",
                                                                   description=f"Current status: Listening to *{message.author.display_name}* in **{voice.channel.name}**")
                                                                   .set_footer(text="wiger3/abbas"))
            voice.msg = reply
            voice.listen(Sink(message.author, asyncio.get_event_loop()))
        case 'stop':
            if not voice or not voice.is_connected():
                await message.reply("I am not in a voice channel")
                return
            voice.stop()

class ChunkedPCMAudio(discord.AudioSource):
    FRAME_SIZE = discord.opus.Decoder.FRAME_SIZE

    def __init__(self, text: str):
        self.end = False
        self.buf = b''
        self.generator = abbas.voice.speak(text)
        self.loop = asyncio.new_event_loop()
    async def aread(self) -> bytes:
        if self.end and len(self.buf) == 0:
            return b''
        try:
            while len(self.buf) < self.FRAME_SIZE:
                self.buf += await anext(self.generator)
        except StopAsyncIteration:
            self.buf = self.buf.ljust(self.FRAME_SIZE)
            self.end = True
        data = self.buf[:self.FRAME_SIZE]
        self.buf = self.buf[self.FRAME_SIZE:]
        return data
    def read(self) -> bytes:
        return self.loop.run_until_complete(self.aread())
    def cleanup(self):
        self.loop.stop()

class Sink(voice_recv.AudioSink):
    def __init__(self, user: discord.User | discord.Member, loop):
        super().__init__()
        self.user = user
        self.last_packet = 0
        self.buf = b''
        self.msg: discord.Message = None
        self.loop: asyncio.AbstractEventLoop = loop
        threading.Thread(target=self.kill_listener).start()
        print(f"Listening to {self.user.display_name}")
    
    def write(self, user: discord.Member | discord.User | None, data: voice_recv.VoiceData):
        if self.msg is None:
            self.msg = self.voice_client.msg
        if user == self.user:
            self.buf += data.pcm
            self.last_packet = time.time()
    
    def kill_listener(self):
        while self.last_packet == 0 or time.time() - self.last_packet < 1:
            time.sleep(0.25)
        print(f"Stopping listening to {self.user.display_name}")
        vc = self.voice_client
        self.msg.embeds[0].description = "Current status: Recognizing speech"
        asyncio.run_coroutine_threadsafe(self.msg.edit(embeds=self.msg.embeds), self.loop)
        vc.stop_listening()
    
    def cleanup(self):
        text = asyncio.run_coroutine_threadsafe(abbas.voice.listen(self.buf), self.loop).result()
        print(text)
        self.msg.embeds[0].description = "Current status: Generating response"
        self.msg.embeds[0].add_field(name="Detected text", value=f"```{text}```")
        asyncio.run_coroutine_threadsafe(self.msg.edit(embeds=self.msg.embeds), self.loop)
    
    def wants_opus(self) -> bool:
        return False



client.run(token)