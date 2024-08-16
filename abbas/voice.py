import base64
import asyncio
import subprocess
import replicate
import elevenlabs
from elevenlabs.client import AsyncElevenLabs
from typing import AsyncGenerator, AsyncIterator

voice_abbas = elevenlabs.Voice(
    voice_id='pNInz6obpgDQGcFmaJgB',
    name='Adam',
    settings=elevenlabs.VoiceSettings(stability=0, similarity_boost=0, style=1, use_speaker_boost=True)
)

async def listen(audio: bytes) -> str:
    duration = len(audio) / 48000 / 8 * 2 + 2 # [size (in bytes)] / [sample_size] / [8bits] * [channels] + [2 seconds leeway]
    if duration < 6:
        duration = 6
    command = "ffmpeg -c:a pcm_s16le -f s16le -ar 48000 -ac 2 -i pipe: -f mp3 pipe:".split(' ')
    ffmpeg = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    mp3, fferror = ffmpeg.communicate(audio)
    if ffmpeg.returncode != 0 or len(mp3) == 0:
        raise RuntimeError(f"FFmpeg failed! ({ffmpeg.returncode})\n{fferror.decode()}")
    
    # send audio to whisper
    print("starting openai whisper")
    model = await replicate.models.async_get('openai/whisper')
    data = base64.b64encode(mp3).decode('utf-8')
    audio = f"data:application/octet-stream;base64,{data}"
    input = {
        "model": "large-v3",
        "language": "pl",
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
    if result.strip() == 'Dziękuję.': # whisper hallucination
        result = ''
    return result


async def speak(text: str) -> AsyncGenerator[bytes, None]:
    """
    Generates audio stream from text using ElevenLabs

    Returns:
        Generator of PCM chunks
    """
    client = AsyncElevenLabs()
    audio_stream = await client.generate(
        text=text,
        model="eleven_multilingual_v2",
        voice=voice_abbas,
        stream=True
    )
    mp3_response = b''
    last = 0
    async for chunk in audio_stream:
        mp3_response += chunk
        wav = mp3_to_pcm(mp3_response)
        yield wav[last:]
        last = len(wav)
def mp3_to_pcm(audio: bytes) -> bytes:
    """
    Converts MP3 to 16bit PCM audio.

    This is so the audio can be sent on a Discord voice channel.
    """
    command = "ffmpeg -i pipe: -c:a pcm_s16le -f s16le -ar 48000 -ac 2 pipe:".split(' ')
    ffmpeg = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    pcm, fferror = ffmpeg.communicate(audio)
    if ffmpeg.returncode != 0 or len(pcm) == 0:
        raise RuntimeError(f"FFmpeg failed! ({ffmpeg.returncode})\n{fferror.decode()}")
    return pcm

async def main():
    while True:
        text = input('> ')

        if text == 'exit':
            return
        
        async def stream_pcm_async(audio_stream: AsyncIterator[bytes]) -> bytes:
            # elevenlabs.play.stream but async and for raw PCM
            def is_installed(lib_name: str) -> bool:
                from shutil import which
                lib = which(lib_name)
                if lib is None:
                    return False
                return True
            if not is_installed("mpv"):
                message = (
                    "mpv not found, necessary to stream audio. "
                    "On mac you can install it with 'brew install mpv'. "
                    "On linux and windows you can install it from https://mpv.io/"
                )
                raise ValueError(message)

            mpv_command = ['mpv', '--demuxer=rawaudio', '--demuxer-rawaudio-channels=2', '--demuxer-rawaudio-rate=48000', '--demuxer-rawaudio-format=s16le', '--no-cache', '--no-terminal', '--', 'fd://0']
            mpv_process = subprocess.Popen(
                mpv_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            audio = b""

            async for chunk in audio_stream:
                if chunk is not None:
                    mpv_process.stdin.write(chunk)  # type: ignore
                    mpv_process.stdin.flush()  # type: ignore
                    audio += chunk
            if mpv_process.stdin:
                mpv_process.stdin.close()
            mpv_process.wait()
            return audio

        audio = await stream_pcm_async(speak(text))
        with open('audio.pcm', 'wb') as file:
            file.write(audio)
        print("Spoken audio was saved as 16-bit Little Endian 48KHz stereo PCM in audio.pcm!")

if __name__ == "__main__":
    asyncio.run(main())