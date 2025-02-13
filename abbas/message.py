from __future__ import annotations
import time
import json
from uuid import uuid4
from typing import Optional

class Message:
    def __init__(self, id: int, parent: Optional[int], sender: str, text: str = '', tool_calls: Optional[list[ToolCall]] = None):
        self.id = id
        self.parent = parent
        self.sender = sender
        self.text = text
        self.tool_calls = tool_calls or []
    def __repr__(self) -> str:
        return f"Message(id={self.id!r}, parent={self.parent!r}, sender={self.sender!r}, text={self.text!r})"
    def __str__(self) -> str:
        return self.text
    
    def __hash__(self) -> int:
        return self.id
    def __eq__(self, value) -> bool:
        if isinstance(value, int):
            return self.id == value
        if isinstance(value, Message):
            return self.id == value.id
        return NotImplemented
    
    def tuple(self):
        return self.id, self.parent, self.sender, self.text
    @staticmethod
    def generate_id(messages: list) -> int:
        id = int(time.time()*1000) << 6
        while next((x for x in messages if x.id == id), None):
            id += 1
        return id

class ToolCall:
    def __init__(self, id: Optional[str], name: str, arguments: dict | str, result: str):
        self.id = id or str(uuid4())
        self.name = name
        if isinstance(arguments, dict):
            self.arguments = arguments
        elif isinstance(arguments, str):
            self.arguments = json.loads(arguments)
        self.result = result
    
    def __repr__(self) -> str:
        return f"ToolCall(id={self.id!r}, name={self.name!r}, arguments={self.arguments!r}, result={self.result!r})"
    def __str__(self) -> str:
        return self.expression
    
    @property
    def expression(self):
        params = ', '.join(f'{x}="{y}"' for x, y in self.arguments.items())
        return f"{self.name}({params})"