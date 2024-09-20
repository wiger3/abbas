import mysql.connector.aio as mysql
from .message import Message

class MySQL:
    def __init__(self, **sql_auth):
        self.sql_auth = sql_auth
        self.db = None
        self.cur = None
        self.connected = False
    
    async def connect(self):
        """
        Connect to the MySQL database. Must be used before any other functions.
        """
        self.db = await mysql.connect(**self.sql_auth)
        print(f"MySQL connected to {self.db.user}@{self.db.server_host}")
        self.cur = await self.db.cursor()
        self.connected = True
    
    async def insert_message(self, id: int, parent: int, sender: str, text: str):
        await self.insert_message(Message(id, parent, sender, text))
    async def insert_message(self, message: Message):
        """
        Insert message into database
        """
        if not self.connected:
            raise RuntimeError("MySQL server not connected!")
        await self.cur.execute("INSERT INTO `messages` VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE text=%s", (*message.tuple(), message.text))
        await self.db.commit()
    async def insert_messages(self, messages: list[Message]):
        """
        Insert multiple messages into database
        """
        if not self.connected:
            raise RuntimeError("MySQL server not connected!")
        for message in messages:
            if not isinstance(message, Message):
                print(f"TypeError: insert_messages() requires abbas.message.Message, not {type(message)}")
                continue
            await self.cur.execute("INSERT INTO `messages` VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE text=%s", (*message.tuple(), message.text))
        await self.db.commit()

    async def fetch_message_list(self, message_id: int) -> list[Message]:
        """
        Recursively build a list of messages in conversation, starting from the youngest child.
        """
        if not self.connected:
            raise RuntimeError("MySQL server not connected!")
        await self.cur.execute("""
                            WITH RECURSIVE cte AS (
                            SELECT id, parent, sender, text FROM `messages` WHERE `id`=%s
                            UNION ALL
                            SELECT m.id, m.parent, m.sender, m.text FROM messages m
                            INNER JOIN cte
                                ON m.id=cte.parent
                            )
                            SELECT * FROM cte;
                        """, (message_id,))
        result = await self.cur.fetchall()
        return [Message(*x) for x in result]
