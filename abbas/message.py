import time

class Message:
    def __init__(self, id: int, parent: int, sender: str, text: str):
        self.id = id
        self.parent = parent
        self.sender = sender.strip()
        self.text = text.strip()
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