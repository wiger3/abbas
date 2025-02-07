# Abbas Baszir
Discord chatbot
## Installation
This project was written for Python 3.12.

Download requirements
```
pip install -r requirements.txt
```
`voice` branch requires FFmpeg. It can be downloaded as follows: \
Windows: https://www.gyan.dev/ffmpeg/builds/ffmpeg-git-essentials.7z \
Linux: Download using your package manager \
(Optional) `voice.py` demo requires mpv.

Download the Llama3 tokenizer from Meta:
1. Go to [Request access to Meta Llama](https://llama.meta.com/llama-downloads) and fill in your details (Select Llama 3 from previous models)
2. Copy the download link you received
3. Run the following commands in your terminal:
```bash
# bash
PRESIGNED_URL="paste_your_copied_url_here"
wget --continue ${PRESIGNED_URL/'*'/"70b_instruction_tuned/tokenizer.model"}
```
```powershell
# powershell
$PRESIGNED_URL="paste_your_copied_url_here"
Invoke-WebRequest $PRESIGNED_URL.replace('*', '70b_instruction_tuned/tokenizer.model') -OutFile "tokenizer.model"
```
4. Copy the tokenizer.model file to the llama folder in the repo directory

Get the following API keys:
1. Replicate: Make an account, set up billing, and go to https://replicate.com/account/api-tokens
2. Discord: Go to https://discord.com/developers/applications, make a new application, go to the Bot tab and click "Reset Token"
3. ElevenLabs: Create an account and in the lower left corner click on your account, then "API Keys".

Save the api keys in environment variables: `REPLICATE_API_TOKEN`, `DISCORD_TOKEN`, `ELEVEN_API_KEY`.

(Optional) If you want to run Whisper (speech recognition) locally on your own GPU instead of Replicate (to avoid their random queue times):
1. Download `faster-whisper` with `pip install faster-whisper`
2. Download [CUDA 12](https://developer.nvidia.com/cuda-download) and cuDNN 8 for CUDA 12 ([Windows](https://developer.download.nvidia.com/compute/cudnn/redist/cudnn/windows-x86_64/cudnn-windows-x86_64-8.9.7.29_cuda12-archive.zip), [Linux](https://developer.download.nvidia.com/compute/cudnn/redist/cudnn/linux-x86_64/cudnn-linux-x86_64-8.9.7.29_cuda12-archive.tar.xz))
3. Set `whisper_source` in config to `cuda`

Fill out config.json:
```yaml
name: Assistant's name, shows up in console (default: Abbas Baszir)
custom_status: Status displayed by the bot on Discord (default: Bogaty szejk)
context_length: max conversation token length to send to the model (default: 2000)
heating: increase generation temperature the longer a conversation is going on. Higher temperature makes the model output more gibberish. This option exists because it's funny (default: false)
whisper_source: what to use for Whisper inference, values other than "replicate" will assume local installation and will be passed as device to PyTorch (default: replicate)
```

(Optional) Create prompting files for the model:
1. system_prompt.txt: System prompt that directs the model
2. first_message.ogg and first_message.txt: A message that gets spoken by the bot when it initially connects to the channel and its transcript. The ogg file **must** be Opus encoded.
3. additional_contexts.json: Additional contexts that get triggered as a message from system when user's message matches the given regex
```json
{
    "additional_contexts": [
        {
            "trigger_words": ["array of", "regexes", "that will trigger the context", "case-insensitive"],
            "context": "Text provided by system as a guide for the model when context gets triggered"
        },
        {
            "trigger_words": ...
            "context": ...
        }
    ]
}
```

Run with `python3 bot.py`

---
Built with [Discord.py](https://github.com/Rapptz/discord.py), [Replicate](https://replicate.com), [Llama3](https://llama.meta.com/llama3/), [Whisper](https://openai.com/index/whisper), [ElevenLabs](https://elevenlabs.io)