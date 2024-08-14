import mysql.connector.aio as mysql
from .message import Message

db, cur = None, None
async def connect():
    """
    Connect to the MySQL database. Must be used before any other functions.
    """
    global db, cur
    sql_auth = {}
    with open('mysql.ini', 'r', encoding='utf-8') as file:
        a = []
        for line in file:
            a.append(line.strip('\n').split('=', 1))
        sql_auth = dict(a)
    db = await mysql.connect(**sql_auth)
    print(f"MySQL connected to {db.user}@{db.server_host}")
    cur = await db.cursor()


async def insert_message(id: int, parent: int, sender: str, text: str):
    await insert_message(Message(id, parent, sender, text))
async def insert_message(message: Message):
    """
    Insert message into database
    """
    if not db or not cur:
        raise RuntimeError("MySQL server not connected!")
    await cur.execute("INSERT INTO `messages` VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE text=%s", (*message.tuple(), message.text))
    await db.commit()
async def insert_messages(messages: list[Message]):
    """
    Insert multiple messages into database
    """
    if not db or not cur:
        raise RuntimeError("MySQL server not connected!")
    for message in messages:
        if not isinstance(message, Message):
            print(f"TypeError: insert_messages() requires abbas.message.Message, not {type(message)}")
            continue
        await cur.execute("INSERT INTO `messages` VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE text=%s", (*message.tuple(), message.text))
    await db.commit()

async def fetch_message_list(message_id: int) -> list[Message]:
    """
    Recursively build a list of messages in conversation, starting from the youngest child.
    """
    if not db or not cur:
        raise RuntimeError("MySQL server not connected!")
    await cur.execute("""
                        WITH RECURSIVE cte AS (
                          SELECT id, parent, sender, text FROM `messages` WHERE `id`=%s
                          UNION ALL
                          SELECT m.id, m.parent, m.sender, m.text FROM messages m
                          INNER JOIN cte
                            ON m.id=cte.parent
                        )
                        SELECT * FROM cte;
                      """, (message_id,))
    result = await cur.fetchall()
    return [Message(*x) for x in result]
