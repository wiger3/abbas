class Message:
    def __init__(self, id: int, parent: int, sender: str, text: str):
        self.id = id
        self.parent = parent
        self.sender = sender
        self.text = text
    def __repr__(self) -> str:
        return f"<Message id={self.id}, parent={self.parent}, sender={repr(self.sender)}, text={repr(self.text)}>"
    def __str__(self) -> str:
        return self.text
    def tuple(self):
        return self.id, self.parent, self.sender, self.text