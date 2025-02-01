import os
import re
import json
import random
import asyncio
import replicate
from replicate.exceptions import ReplicateError, ModelError
from llama.tokenizer import Tokenizer
from .tools import ToolsManager
from .message import Message

class ResponseGen:
    def __init__(self, context_length: int, heating: bool, *, tokenizer_path: str = 'llama/tokenizer.model'):
        self.context_length = context_length
        self.heating = heating
        self.tt = Tokenizer(tokenizer_path)
        self.tools = ToolsManager()
        self.tools_prompt = ""
        if len(self.tools.available_tools) > 0:
            self.tools_prompt = ("\n\nTool usage:\n"
            "You have the following tools available:\n"
            "{0}\n"
            "To use a tool call it as follows:\n"
            "<|start_tool|>tool_name(parameter=\"value\")<|end_tool|>\n"
            "Example:\n"
            "<|start_tool|>calculator(query=\"2+2\")<|end_tool|>")
            self.tools_prompt = self.tools_prompt.format(self.tools.describe_tools())
        print(f"Loaded {len(self.tools.available_tools)} tools: {", ".join(self.tools.available_tools)}")

    # messages should be in order of newest to oldest
    async def generate_response(self, messages: list[Message]) -> tuple[dict, str]:
        """
        Uses llama3 to generate a response to the message.
        The list of messages get converted to a conversation and sent to the model, along with a system prompt read from ./system_prompt.txt

        Args:
            messages: list of Message objects
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
                system_prompt = "Jesteś bogaty szejk Abbas Baszir."
        system_prompt += self.tools_prompt
        if os.path.isfile('additional_contexts.json'):
            try:
                with open('additional_contexts.json', 'r', encoding='utf-8') as file:
                    o = json.loads(file.read())
                    if 'additional_contexts' in o:
                        additional_contexts = o['additional_contexts']
            except OSError:
                additional_contexts = []
        prefix = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|>"
        suffix = f"<|start_header_id|>assistant<|end_header_id|>\n\n"
        prompt = ''
        for msg in messages:
            if not msg.text:
                continue
            text = f"<|start_header_id|>{msg.sender}<|end_header_id|>\n\n{msg.text}<|eot_id|>"
            if msg.sender != 'assistant':
                for context in additional_contexts:
                    for trigger in context['trigger_words']:
                        regex = re.compile(trigger, re.I)
                        match = regex.search(msg.text)
                        if match:
                            text = f"<|start_header_id|>system<|end_header_id|>\n\n{context['context']}<|eot_id|>{text}"
                            break
            if len(self.tt.encode(prefix + text + prompt + suffix, bos=False, eos=False, allowed_special="all")) >= self.context_length:
                break
            prompt = text + prompt

        zaposciewanie = False
        temperature = 0.81
        if self.heating:
            zaposciewanie: bool = self.is_zaposciany(messages)
            temperature = 0.81
            for x in messages[1:]:
                if x.sender == 'assistant':
                    temperature = self.heat_up(temperature, 0.01, 0.02)
            if zaposciewanie:
                temperature = self.heat_up(temperature, 0.1, 0.2, cap=9)
        input = {
            "prompt": prompt,
            "prompt_template": f"{prefix}{{prompt}}{suffix}",
            "max_tokens": 150,
            "temperature": temperature
        }
        if zaposciewanie:
            input['presence_penalty'] = 0
            input['frequency_penalty'] = 0
        output = await replicate.async_run(
            "meta/meta-llama-3-70b-instruct",
            input=input
        )

        # sometimes llama generates a wrong token, fix it if it's a minor mistake
        correct_tokens = ['<', '|', 'start', '_tool', '|', '>']
        len_correct = len(correct_tokens)-1
        for i in range(len_correct, len(output)):
            tokens = output[i-len_correct:i+1]
            incorrect = [j+i-len_correct for j, token in enumerate(tokens) if token != correct_tokens[j]]
            if len(incorrect) == 1:
                output[i-len_correct:i+1] = correct_tokens
                break
        
        text = "".join(output)
        tool, tool_response = await asyncio.to_thread(self.tools.parse_tool, text, asyncio.get_running_loop())
        if tool is not None:
            if tool_response is None:
                text = text[:text.find('<|start_tool|>')]
                if not text:
                    return await self.generate_response(messages)
                return (input, text)
            response_log = tool_response
            if "\n" in response_log:
                response_log = response_log.splitlines()
                response_log = response_log[0] + f"... (Truncated {sum(len(x) for x in response_log[1:])} characters)"
            print(tool, "==>", response_log)
            if tool_response:
                messages.insert(0, Message(Message.generate_id(messages), messages[0].id, 'assistant', f'<|start_tool|>{tool}<|end_tool|>'))
                messages.insert(0, Message(Message.generate_id(messages), messages[0].id, 'system', f'Response:\n\n{tool_response!s}'))
                return await self.generate_response(messages)

        return (input, text)

    def is_zaposciany(self, messages: list[Message]) -> bool:
        for x in messages:
            if x.sender == 'assistant':
                roleplay = x.text.split("*")[1::2]
                for me in roleplay:
                    if any(x in me for x in ['zaposciewa', 'zapościewa', 'crack', 'krock']):
                        return True
                break
        return False
    def heat_up(self, temperature: float, min: float, max: float, cap: float = 1.055) -> float:
        lvl = random.uniform(min, min+max)
        if temperature + lvl >= cap:
            temperature -= lvl
        else:
            temperature += lvl
        return temperature

if __name__ == '__main__':
    async def main():
        messages = []
        context = None

        def add_message(sender, text):
            nonlocal messages
            messages.append(Message(len(messages), len(messages)-1 if len(messages) else None, sender, text))
        
        if os.path.isfile('first_message.txt'):
            try:
                with open('first_message.txt', 'r', encoding='utf-8') as file:
                    add_message('assistant', file.read())
                    print("Abbas Baszir: " + messages[0].text)
            except OSError:
                pass
        respgen = ResponseGen(2000)
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
                        print(f"Context length: {len(respgen.tt.encode(context['prompt'], bos=False, eos=False))}/{respgen.context_length}")
                elif cmd == 'bp':
                    breakpoint()
                else:
                    print("Unknown command: " + cmd)
                continue
            print("...", end='\r')
            add_message('user', text)
            response = await respgen.generate_response(messages)
            context = response[0]
            message = response[1]
            add_message({'assistant', message})
            print("Abbas Baszir: " + message)
    asyncio.run(main())