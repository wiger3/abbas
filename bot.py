import os
import asyncio
import discord
import abbas.voice

token = os.environ['DISCORD_TOKEN']

intents = discord.Intents.default()
intents.message_content = True

voice: discord.VoiceClient = None

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    await client.change_presence(activity=discord.CustomActivity(name="Bogaty szejk / voice test"))
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
            voice = await vstate.channel.connect()
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

class ChunkedPCMAudio(discord.AudioSource):
    SAMPLING_RATE = 48000
    CHANNELS = 2
    FRAME_LENGTH = 20  # in milliseconds
    SAMPLE_SIZE = 2 * CHANNELS # 16-bit PCM = 2 bytes
    SAMPLES_PER_FRAME = int(SAMPLING_RATE / 1000 * FRAME_LENGTH)

    FRAME_SIZE = SAMPLES_PER_FRAME * SAMPLE_SIZE

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


client.run(token)