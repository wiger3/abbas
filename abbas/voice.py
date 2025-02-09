import os
import base64
import asyncio
import subprocess
import elevenlabs
from elevenlabs.client import AsyncElevenLabs
from typing import AsyncGenerator, AsyncIterator, Optional

voice_abbas = elevenlabs.Voice(
    voice_id='pNInz6obpgDQGcFmaJgB',
    name='Adam',
    settings=elevenlabs.VoiceSettings(stability=0, similarity_boost=0)
)


class VoiceManager:
    def __init__(self, whisper_source: str, language: Optional[str] = None):
        self.language = language or None
        self.local_whisper = whisper_source != "replicate"
        if self.local_whisper:
            from faster_whisper import WhisperModel
            self.whisper = WhisperModel("large-v3", device=whisper_source, compute_type="float16")
            print("Initialized local Whisper model")

    async def listen(self, audio: bytes, *, sample_size: int = 48000, channels: int = 2) -> str:
        # send audio to whisper
        print("starting openai whisper")
        duration = len(audio) / sample_size / 8 * channels + 2 # [size (in bytes)] / [sample_size] / [8bits] * [channels] + [2 seconds leeway]
        if self.local_whisper:
            import io
            import wave
            from time import time
            def run():
                audioio = io.BytesIO()
                wav: wave.Wave_write = wave.open(audioio, 'wb')
                wav.setnchannels(channels)
                wav.setsampwidth(2)
                wav.setframerate(sample_size)
                wav.writeframes(audio)
                wav.close()
                audioio.seek(0)
                segments, info = self.whisper.transcribe(audioio, language=self.language)
                return "".join(x.text for x in segments)
            whisper_start = time()
            result = await asyncio.to_thread(run)
            whisper_end = time()
            print(f"Whisper took {whisper_end-whisper_start:.2f}s to transcribe {duration:.2f}s of audio")
        else:
            import replicate
            if duration < 6:
                duration = 6
            
            # compress audio to mp3 for upload
            mp3 = ffmpeg(f"-c:a pcm_s16le -f s16le -ar {sample_size} -ac {channels}".split(' '), audio, "-f mp3".split(' '))
            
            # send mp3 to replicate
            model = await replicate.models.async_get('openai/whisper')
            data = base64.b64encode(mp3).decode('utf-8')
            audio = f"data:application/octet-stream;base64,{data}"
            input = {
                "model": "large-v3",
                "language": self.language,
                "translate": False,
                "audio": audio
            }
            prediction = await replicate.predictions.async_create(
                model.latest_version,
                input=input
            )
            try:
                async with asyncio.timeout(duration):
                    await prediction.async_wait()
            except TimeoutError:
                print(f"ERROR: Whisper timed out ({duration} seconds)")
                prediction.cancel()
            if prediction.status != "succeeded":
                return None
            result = prediction.output['transcription']
        if result.strip()[:-1] in ('Dziękuję', 'Dziękuje', 'Dziękuję za oglądanie', 'Dziękuje za oglądanie', 'Dzięki', 'Dzięki za oglądanie'): # whisper hallucination
            print(f"Discarding hallucination: {result!r}")
            result = ''
        return result


    async def speak(self, text: str, *, sample_size: int = 48000, channels: int = 2) -> AsyncGenerator[bytes, None]:
        """
        Generates audio stream from text using ElevenLabs

        Returns:
            Generator of PCM chunks
        """
        client = AsyncElevenLabs()
        audio_stream = await client.generate(
            text=text,
            model="eleven_turbo_v2_5",
            voice=voice_abbas,
            stream=True
        )
        mp3_response = b''
        last = 0
        async for chunk in audio_stream:
            mp3_response += chunk
            wav = mp3_to_pcm(mp3_response, sample_size=sample_size, channels=channels)
            yield wav[last:]
            last = len(wav)


def mp3_to_pcm(audio: bytes, *, sample_size: int = 48000, channels: int = 2) -> bytes:
    """
    Converts MP3 to 16bit PCM audio.

    This is so the audio can be sent on a Discord voice channel.
    """
    return ffmpeg([], audio, f"-c:a pcm_s16le -f s16le -ar {sample_size} -ac {channels}".split(' '))

def ffmpeg(input_args: list, input: bytes, output_args: list) -> bytes:
    command = ["ffmpeg"] + input_args + ["-i", "pipe:"] + output_args + ["pipe:"]
    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    out, fferror = proc.communicate(input)
    if proc.returncode != 0 or len(out) == 0:
        raise RuntimeError(f"FFmpeg failed! ({proc.returncode})\n{fferror.decode()}")
    return out

async def main():
    import wave
    from time import time
    try:
        import pyaudio
    except ImportError:
        print("pyaudio is needed to run the demo")
        print("install it using pip install pyaudio")
        return
    
    p = pyaudio.PyAudio()
    whisper_source = input("Choose Whisper source (replicate/cuda/cpu): ")
    manager = VoiceManager(whisper_source)
    
    CHUNK = 1024
    CHANNELS = 2
    RATE = 48000
    SECONDS = 5
    
    audiostream = p.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        output=True
    )

    while True:
        input("\nPress enter to start speaking...")
        print(f"Listening to your microphone for {SECONDS} seconds")

        audio = b""
        for i in range(0, RATE // CHUNK * SECONDS):
            audio += audiostream.read(CHUNK)
        
        microphone_wav = f'microphone_{int(time())}.wav'
        with wave.open(microphone_wav, 'w') as wav:
            wav.setnchannels(CHANNELS)
            wav.setframerate(RATE)
            wav.setsampwidth(2)
            wav.writeframes(audio)
        
        text = await manager.listen(audio, sample_size=RATE, channels=CHANNELS)
        print("You said: " + text)
        audio = b""
        async for chunk in manager.speak(text, sample_size=RATE, channels=CHANNELS):
            audiostream.write(chunk)
            audio += chunk

        elevenlabs_wav = f'elevenlabs_{int(time())}.wav'
        with wave.open(elevenlabs_wav, 'w') as wav:
            wav.setnchannels(CHANNELS)
            wav.setframerate(RATE)
            wav.setsampwidth(2)
            wav.writeframes(audio)

        print(f"Your microphone audio was saved to {microphone_wav}")
        print(f"Elevenlabs generated audio was saved to {elevenlabs_wav}")

if __name__ == "__main__":
    asyncio.run(main())