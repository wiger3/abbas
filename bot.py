import os
import time
import asyncio
import threading
import time
import discord
from discord.ext import voice_recv
import replicate.exceptions
import abbas
import abbas.voice
from abbas.message import Message

class VoiceClient(voice_recv.VoiceRecvClient):
    def __init__(self, client: discord.Client, channel: discord.abc.Connectable):
        super().__init__(client, channel)
        self.msg: discord.Message = None
        self.messages: list[Message] = []
    
    def stop_listening(self, user: discord.User | discord.Member = None, buf: bytes = None) -> None:
        super().stop_listening()
        if user is None or buf is None:
            return
        started_at = time.time()
        loop = self.client.loop
        text = asyncio.run_coroutine_threadsafe(abbas.voice.listen(buf), loop).result()
        if text is None:
            print("Responding with timeout embed")
            e_type = "Whisper timeout"
            self.msg.embeds[0].description = "Current status: Error \u26a0\ufe0f"
            self.msg.embeds[0].colour = 0xED4245
            self.msg.embeds[0].add_field(name="Wystąpił błąd", value="Podczas odpowiadania wystąpił następujący błąd: " + e_type, inline=False)
            asyncio.run_coroutine_threadsafe(self.msg.edit(embeds=self.msg.embeds), loop)
            return
        print(f"{user.display_name}: {text}")
        self.msg.embeds[0].description = "Current status: Generating response"
        self.msg.embeds[0].add_field(name="Detected text", value=f"```{text}```", inline=False)
        asyncio.run_coroutine_threadsafe(self.msg.edit(embeds=self.msg.embeds), loop)
        self.create_message(user.display_name, text)
        input, text = asyncio.run_coroutine_threadsafe(abbas.generate_response(self.messages[::-1]), loop).result()
        print(input)
        if isinstance(text, replicate.exceptions.ReplicateException):
            print("Responding with exception embed")
            e_type = "Unknown exception"
            if isinstance(text, replicate.exceptions.ReplicateError):
                e_type = text.type
            elif isinstance(text, replicate.exceptions.ModelError):
                e_type = "Prediction failed, please try again"
            self.msg.embeds[0].description = "Current status: Error \u26a0\ufe0f"
            self.msg.embeds[0].colour = 0xED4245
            self.msg.embeds[0].add_field(name="Wystąpił błąd", value="Podczas odpowiadania wystąpił następujący błąd: " + e_type, inline=False)
            asyncio.run_coroutine_threadsafe(self.msg.edit(embeds=self.msg.embeds), loop)
            self.messages = self.messages[:-1]
            return
        self.msg.embeds[0].description = f"Current status: Done in {(time.time() - started_at):.2f}s 👍\nCurrent conversation length: {len(self.messages)+1}"
        self.msg.embeds[0].colour = 0x57F287
        self.msg.embeds[0].add_field(name="Response", value=f"```{text}```", inline=False)
        asyncio.run_coroutine_threadsafe(self.msg.edit(embeds=self.msg.embeds), loop)
        print("Abbas Baszir: " + text)
        self.create_message('assistant', text)
        self.play(ChunkedPCMAudio(text))

    
    def create_message(self, sender: str, text: str):
        msg = Message(int(time.time()*1000), self.messages[-1].id if self.messages else None, sender, text)
        self.messages.append(msg)

token = os.environ['DISCORD_TOKEN']

intents = discord.Intents.default()
intents.message_content = True

voice: VoiceClient = None

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    await client.change_presence(activity=discord.CustomActivity(name="\ud83c\udf99\ufe0f Voice test"))
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
            voice.create_message('assistant', text)
            voice.play(ChunkedPCMAudio(text))
        case 'listen':
            if not voice or not voice.is_connected():
                await message.reply("I am not in a voice channel")
                return
            user = message.author
            if len(args) > 1:
                user = int(args[1])
                user = next((x for x in voice.channel.members if x.id == user), None)
                if user is None:
                    await message.reply("User not found in voice channel")
                    return
            reply = await message.channel.send(embed=discord.Embed(title="Abbas Baszir voice test",
                                                                   colour=0x5865F2,
                                                                   description=f"Current status: Listening to *{user.display_name}* in **{voice.channel.name}**")
                                                                   .set_footer(text="wiger3/abbas"))
            voice.msg = reply
            voice.listen(Sink(user))
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
    def __init__(self, user: discord.User | discord.Member):
        super().__init__()
        self.user = user
        self.last_packet = 0
        self.buf = b''
        self.msg: discord.Message = None
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
            if not self.voice_client:
                return
            if not self.voice_client.is_connected():
                return
            if not self.voice_client.is_listening():
                return
        print(f"Stopping listening to {self.user.display_name}")
        vc = self.voice_client
        self.msg.embeds[0].description = "Current status: Recognizing speech"
        asyncio.run_coroutine_threadsafe(self.msg.edit(embeds=self.msg.embeds), self.client.loop)
        vc.stop_listening(self.user, self.buf)
    
    def cleanup(self):
        pass
    
    def wants_opus(self) -> bool:
        return False



client.run(token)