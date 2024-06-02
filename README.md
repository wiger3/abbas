# Abbas Baszir
Discord chatbot
## Installation
This project was written for Python 3.12.

Download requirements
```
pip install -r requirements.txt
```

Download the Llama3 tokenizer from Meta:
1. Go to [Request access to Meta Llama](https://llama.meta.com/llama-downloads) and fill in your details
2. Copy the download link you received
3. Run the following commands in your terminal:
```
PRESIGNED_URL="paste_your_copied_url_here"
wget --continue ${PRESIGNED_URL/'*'/"70b_instruction_tuned/tokenizer.model"}
```
4. Copy the tokenizer.model file to the llama folder in the repo directory

Get the following API keys:
1. Replicate: Make an account, set up billing, and go to https://replicate.com/account/api-tokens
2. Discord: Go to https://discord.com/developers/applications, make a new application, go to the Bot tab and click "Reset Token"
3. Tenor: https://developers.google.com/tenor/guides/quickstart#setup

Save the api keys in environment variables: `REPLICATE_API_TOKEN`, `DISCORD_TOKEN`, `TENOR_APIKEY`.

Get a MySQL server and import the abbas.sql file, then fill out the mysql.ini file

(Optional) Create prompting files for the model:
1. system_prompt.txt: System prompt that directs the model
2. first_message.txt: A message that gets appended to the context as an initial message sent by the bot
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
Built with [Discord.py](https://github.com/Rapptz/discord.py), [Replicate](https://replicate.com), [Llama3](https://llama.meta.com/llama3/)