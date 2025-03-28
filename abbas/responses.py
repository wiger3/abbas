import os
import re
import json
import random
import asyncio
from abc import ABC, abstractmethod
from .message import Message

class Responder(ABC):
    @abstractmethod
    def __init__(self, context_length: int, heating: bool):
        raise NotImplementedError
    
    @abstractmethod
    async def generate_response(self, messages: list[Message]) -> tuple[dict, str]:
        """Generates the next response in a conversation.
        The list of messages get encoded to a conversation, system prompt is read from ./system_prompt.txt,
        additional contexts from ./additional_contexts.json get applied, then conversation gets sent to model

        Args:
            messages: list of Message objects, in the order of newest to oldest
        Returns:
            tuple containing:
            [0]: input sent to the model containing the prompt and generation data
            [1]: text generated by the model
        """
        raise NotImplementedError

    @abstractmethod
    def token_len(self, text: str) -> str:
        """Returns the length of provided text in tokens, using the default tokenizer for model"""
        raise NotImplementedError

    def load_prompting_files(self):
        if os.path.isfile('system_prompt.txt'):
            try:
                with open('system_prompt.txt', 'r', encoding='utf-8') as file:
                    system_prompt = file.read()
            except OSError:
                system_prompt = "Jesteś bogaty szejk Abbas Baszir."
        if os.path.isfile('additional_contexts.json'):
            try:
                with open('additional_contexts.json', 'r', encoding='utf-8') as file:
                    o = json.loads(file.read())
                    if 'additional_contexts' in o:
                        additional_contexts = o['additional_contexts']
            except OSError:
                additional_contexts = []
        return system_prompt, additional_contexts
    
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

class ReplicateLlamaResponder(Responder):
    def __init__(self, context_length: int, heating: bool, *, tokenizer_path: str = 'llama/tokenizer.model'):
        import replicate
        from .tools import LlamaToolsManager
        from llama.tokenizer import Tokenizer
        self.context_length = context_length
        self.heating = heating
        self.tt = Tokenizer(tokenizer_path)
        self.tools = LlamaToolsManager()
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
    async def generate_response(self, messages: list[Message], recursion_depth=0) -> tuple[dict, str]:
        import replicate
        if recursion_depth > 2:
            raise RecursionError("Recursion depth reached while calling tool")
        system_prompt, additional_contexts = self.load_prompting_files()
        system_prompt += self.tools_prompt
        prefix = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|>"
        suffix = f"<|start_header_id|>assistant<|end_header_id|>\n\n"
        prompt = ''
        for msg in messages:
            if msg.tool_calls:
                tc = msg.tool_calls[0]
                text = (f"<|start_header_id|>{msg.sender}<|end_header_id|>\n\n<|start_tool|>{tc.expression}<|end_tool|><|eot_id|>"
                        f"<|start_header_id|>system<|end_header_id|>\n\nResponse:\n\n{tc.result}<|eot_id|>")
            else:
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
            if self.token_len(prefix + text + prompt + suffix) >= self.context_length:
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
        tool = await asyncio.to_thread(self.tools.parse_tool, text, asyncio.get_running_loop())
        if tool is not None:
            response_log = tool.result
            if "\n" in response_log:
                response_log = response_log.splitlines()
                response_log = response_log[0] + f"... (Truncated {sum(len(x) for x in response_log[1:])} characters)"
            print(tool.expression, "==>", response_log)
            if tool.result:
                messages.insert(0, Message(Message.generate_id(messages), messages[0].id, 'assistant', tool_calls=[tool]))
                return await self.generate_response(messages, recursion_depth+1)

        return (input, text)

    def token_len(self, text: str) -> str:
        return len(self.tt.encode(text, bos=False, eos=False, allowed_special="all"))
    
if __name__ == '__main__':
    async def main():
        messages: list[Message] = []
        context = None

        def add_message(sender, text):
            nonlocal messages
            messages.append(Message(
                Message.generate_id(messages),
                messages[-1].id if len(messages) else None,
                sender, text))
        
        responder = ReplicateLlamaResponder(2000, True)

        if os.path.isfile('first_message.txt'):
            try:
                with open('first_message.txt', 'r', encoding='utf-8') as file:
                    add_message('assistant', file.read())
                    print("Abbas Baszir: " + messages[0].text)
            except OSError:
                pass
        
        while True:
            text = input('> ')
            if text[0] == ':':
                args = text[1:].split(' ')
                cmd = args[0].lower()
                if cmd == 'exit' or cmd == 'quit' or cmd == 'q':
                    break
                elif cmd == 'msgs' or cmd == 'messages':
                    print(messages)
                elif cmd == 'context':
                    print(context)
                    if context:
                        print(f"Context length: {responder.token_len(context['prompt'])}/{responder.context_length}")
                elif cmd == 'bp':
                    breakpoint()
                else:
                    print("Unknown command: " + cmd)
                continue
            print("...", end='\r')
            add_message('user', text)
            context, message = await responder.generate_response(messages[::-1])
            add_message('assistant', message)
            print("Abbas Baszir: " + message)
    asyncio.run(main())