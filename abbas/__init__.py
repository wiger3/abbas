import os
import re
import json
import random
import asyncio
import replicate
from replicate.exceptions import ReplicateError, ModelError
from llama.tokenizer import Tokenizer

tt = Tokenizer('llama/tokenizer.model')

context_length = 2000
system_prompt = "Jesteś bogaty szejk Abbas Baszir."
additional_contexts = []

# messages should be in order of newest to oldest
async def generate_response(messages: list[dict]) -> tuple[dict, str]:
    """
    Uses llama3 to generate a response to the message.
    The list of messages get converted to a conversation and sent to the model, along with a system prompt read from ./system_prompt.txt

    Args:
        messages: list of dicts with the keys: sender, text. Messages should be in order of newest to oldest
    Returns:
        tuple containing:
        [0]: input sent to the model containing the prompt and generation data
        [1]: text generated by the model OR any exceptions raised by the Replicate API (prediction errors)
    """
    if os.path.isfile('system_prompt.txt'):
        try:
            with open('system_prompt.txt', 'r', encoding='utf-8') as file:
                system_prompt = file.read()
        except OSError:
            pass
    if os.path.isfile('additional_contexts.json'):
        try:
            with open('additional_contexts.json', 'r', encoding='utf-8') as file:
                o = json.loads(file.read())
                if 'additional_contexts' in o:
                    additional_contexts = o['additional_contexts']
        except OSError:
            pass
    prefix = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|>"
    suffix = f"<|start_header_id|>assistant<|end_header_id|>\n\n"
    prompt = ''
    for msg in messages:
        text = f"<|start_header_id|>{msg['sender']}<|end_header_id|>\n\n{msg['text']}<|eot_id|>"
        if msg['sender'] != 'assistant':
            for context in additional_contexts:
                for trigger in context['trigger_words']:
                    regex = re.compile(trigger, re.I)
                    match = regex.search(msg['text'])
                    if match:
                        text += f"<|start_header_id|>system<|end_header_id|>\n\n{context['context']}<|eot_id|>"
                        break
        if len(tt.encode(prefix + text + prompt + suffix, bos=False, eos=False)) >= context_length:
            break
        prompt = text + prompt
    prompt = f"{prefix}{prompt}{suffix}"

    zaposciewanie: bool = is_zaposciany(messages)
    # i am aware that this rerolls temperature every prompt, this is intended
    # TODO: make prettier when this shitty mouse gets replaced
    temperature = 0.81
    for x in messages[1:]:
        if x['sender'] == 'assistant':
            temperature = heat_up(temperature, 0.01, 0.02)
    if zaposciewanie:
        temperature = heat_up(temperature, 0.1, 0.2, cap=9)
        print("[generowanie najbardziej zapościanej odpowiedzi]", end='\r')
    input = {
        "prompt": prompt,
        "prompt_template": "{prompt}",
        "max_tokens": 150,
        "temperature": temperature
    }
    if zaposciewanie:
        input['presence_penalty'] = 0
        input['frequency_penalty'] = 0
    try:
        output = await replicate.async_run(
            "meta/meta-llama-3-70b-instruct",
            input=input
        )
        return (input, "".join(output))
    except (ReplicateError, ModelError) as e:
        print(e)
        return (input, e)

def is_zaposciany(messages: list[str]) -> bool:
    for x in messages:
        if x['sender'] == 'assistant':
            roleplay = x['text'].split("*")[1::2]
            for me in roleplay:
                if any(x in me for x in ['zaposciewa', 'zapościewa', 'crack', 'krock']):
                    return True
            break
    return False
def heat_up(temperature: float, min: float, max: float, cap: float = 1.155) -> float:
    lvl = random.uniform(min, min+max)
    if temperature + lvl >= cap:
        temperature -= lvl
    else:
        temperature += lvl
    return temperature

async def main():
    import os
    messages = []
    context = None
    if os.path.isfile('first_message.txt'):
        try:
            with open('first_message.txt', 'r', encoding='utf-8') as file:
                messages.append({'sender': 'assistant', 'text': file.read()})
                print("Abbas Baszir: " + messages[0]['text'])
        except OSError:
            pass
    while True:
        text = input('> ')
        if text[0] == ':':
            args = text[1:].split(' ')
            cmd = args[0].lower()
            if cmd == 'exit':
                break
            elif cmd == 'msgs':
                print(messages)
            elif cmd == 'context':
                print(context)
                if context:
                    print(f"Context length: {len(tt.encode(context['prompt'], bos=False, eos=False))}/{context_length}")
            elif cmd == 'bp':
                breakpoint()
            else:
                print("Unknown command: " + cmd)
            continue
        print("...", end='\r')
        messages.append({'sender': 'user', 'text': text})
        response = await generate_response(messages)
        context = response[0]
        message = response[1]
        messages.append({'sender': 'assistant', 'text': message})
        print("Abbas Baszir: " + message)

if __name__ == '__main__':
    asyncio.run(main())