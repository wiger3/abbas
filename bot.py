import os
import re
import time
import asyncio
import threading
import time
import discord
from discord.ext import voice_recv
from discord.ext.voice_recv.silence import SILENCE_PCM
import replicate.exceptions
import abbas
import abbas.voice
from abbas.message import Message

class VoiceClient(voice_recv.VoiceRecvClient):
    def __init__(self, client: discord.Client, channel: discord.abc.Connectable):
        super().__init__(client, channel)
        self.ready = False
        self.msg: discord.Message = None
        self.messages: list[Message] = []
    
    def stop_listening(self, bufs: dict[bytes] = None):
        print(f"Stopping listening")
        super().stop_listening()
        if bufs is None:
            return
        def user(id: int):
            return next((x for x in self.channel.members if x.id == id), None)
        started_at = time.time()
        loop = self.client.loop
        async def tasks():
            t: list[asyncio.Task] = []
            async with asyncio.TaskGroup() as tg:
                for buf in bufs.values():
                    t.append(tg.create_task(abbas.voice.listen(buf)))
            return dict(zip(bufs.keys(), [x.result() for x in t]))
        text: dict = asyncio.run_coroutine_threadsafe(tasks(), loop).result()
        if list(text.values()).count(None) == len(text):
            print("Responding with timeout embed")
            e_type = "Whisper timeout for all speakers"
            self.update_embed("Error \u26a0\ufe0f",
                              colour=0xED4245,
                              field=("Wystąpił błąd", "Podczas odpowiadania wystąpił następujący błąd: " + e_type))
            return
        elif None in text.values():
            self.update_embed(field=("Wystąpił błąd", f"Some speech recognitions failed: {", ".join([user(x).display_name for x in text if text[x] is None])}"))
                
        detected = []
        for k, v in text.items():
            if v is None or v == '':
                continue
            self.create_message(user(k).display_name, v)
            detected.append(f"{user(k).display_name}: {v}")
        if not detected:
            self.update_embed("Error \u26a0\ufe0f",
                              colour=0xED4245,
                              field=("Wystąpił błąd", "Podczas odpowiadania wystąpił następujący błąd: Nie wykryto żadnej mowy"))
            return
        detected = "\n".join(detected)
        print(detected)
        self.update_embed("Generating response",
                          field=("Detected text", f"```{detected}```"))
        input, text = asyncio.run_coroutine_threadsafe(abbas.generate_response(self.messages[::-1]), loop).result()
        if isinstance(text, replicate.exceptions.ReplicateException):
            print("Responding with exception embed")
            e_type = "Unknown exception"
            if isinstance(text, replicate.exceptions.ReplicateError):
                e_type = text.type
            elif isinstance(text, replicate.exceptions.ModelError):
                e_type = "Prediction failed, please try again"
            self.update_embed("Error \u26a0\ufe0f",
                              colour=0xED4245,
                              field=("Wystąpił błąd", "Podczas odpowiadania wystąpił następujący błąd: " + e_type))
            self.messages = self.messages[:-1]
            return
        self.update_embed(f"Done in {(time.time() - started_at):.2f}s 👍\nCurrent conversation length: {len(self.messages)+1}",
                          colour=0x57F287,
                          field=("Response", f"```{text}```"))
        print("Abbas Baszir: " + text)
        self.create_message('assistant', text)
        self.play(ChunkedPCMAudio(text))
        asyncio.run_coroutine_threadsafe(self.start_listening(self.msg.channel), loop)
    
    async def start_listening(self, channel: discord.abc.Messageable):
        while self.is_playing():
            await asyncio.sleep(0.25)
        reply = await channel.send(embed=discord.Embed(title="Abbas Baszir voice test",
                                                       colour=0x5865F2,
                                                       description=f"Current status: Listening in **{voice.channel.name}**")
                                                       .set_footer(text="wiger3/abbas"))
        self.msg = reply
        self.listen(voice_recv.sinks.SilenceGeneratorSink(Sink()))

    
    def create_message(self, sender: str, text: str):
        if not text or not sender:
            return
        id = int(time.time()*1000) << 6
        while next((x for x in self.messages if x.id == id), None):
            id += 1
        msg = Message(id, self.messages[-1].id if self.messages else None, sender, text)
        self.messages.append(msg)
    
    def update_embed(self, status: str = None, colour: int = None, field: tuple = None):
        if status is not None:
            self.msg.embeds[0].description = f"Current status: {status}"
        if colour is not None:
            self.msg.embeds[0].colour = colour
        if field is not None:
            self.msg.embeds[0].add_field(name=field[0], value=field[1], inline=False)
        return asyncio.run_coroutine_threadsafe(self.msg.edit(embeds=self.msg.embeds), self.client.loop).result()

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
            if voice and voice.is_connected():
                await voice.disconnect()
            voice = await vstate.channel.connect(cls=VoiceClient)
            try:
                if os.path.isfile('first_message.txt') and os.path.isfile('first_message.ogg'):
                    await asyncio.sleep(1)
                    with open('first_message.txt', 'r', encoding='utf-8') as file:
                        text = file.read()
                    source = discord.player.FFmpegOpusAudio('first_message.ogg', codec="copy")
                    voice.play(source)
                    while voice.is_playing():
                        await asyncio.sleep(0.25)
                    voice.create_message('assistant', text)
            except OSError:
                pass
            voice.ready = True
            # await message.channel.send("ready")
            await voice.start_listening(message.channel)
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
            if not voice.ready:
                await message.reply("I'm not ready to start listening")
                return
            if voice.is_playing():
                await message.reply("I'm talking, wait until I shut up")
                return
            if voice.is_listening():
                await message.reply("I'm already listening")
                return
            await voice.start_listening(message.channel)
        case 'stop':
            if not voice or not voice.is_connected():
                await message.reply("I am not in a voice channel")
                return
            voice.stop()
            await message.add_reaction('👍')
        case 'convo':
            if not voice or not voice.is_connected():
                await message.reply("I am not in a voice channel")
                return
            convo = "\n".join(f"```{x.sender}: {x.text}```" for x in voice.messages)
            if len(convo) > 4090:
                embeds = []
                title = "Current conversation"
                for chunk in [x[0] for x in re.findall(r'(.{1,4000})(\n|$)', convo, re.S)]:
                    embeds.append(discord.Embed(title=title, description=chunk))
                    title = None
                await message.channel.send(embeds=embeds)
                return
            await message.channel.send(embed=discord.Embed(title="Current conversation", description=convo))

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
    def __init__(self):
        super().__init__()
        self.started_at = time.time()
        self.last_packet = 0
        self.buf: dict[bytes] = {}
        self.msg: discord.Message = None
        threading.Thread(target=self.kill_listener).start()
        print(f"Listening")
    
    def write(self, user: discord.Member | discord.User | None, data: voice_recv.VoiceData):
        if self.msg is None:
            self.msg = self.voice_client.msg
        if user:
            if not user.id in self.buf:
                self.buf[user.id] = b''
            self.buf[user.id] += data.pcm
            if data.pcm != SILENCE_PCM:
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
            if time.time() - self.started_at > 15:
                break
        vc = self.voice_client
        vc.update_embed("Recognizing speech")
        vc.stop_listening(self.buf)
    
    def cleanup(self):
        pass
    
    def wants_opus(self) -> bool:
        return False



client.run(token)