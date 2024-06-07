import asyncio
from datetime import date
import mysql.connector as mysql

sql_auth = {}
with open('mysql.ini', 'r', encoding='utf-8') as file:
    a = []
    for line in file:
        a.append(line.strip('\n').split('=', 1))
    sql_auth = dict(a)

try:
    mydb = mysql.connect(**sql_auth)
except mysql.errors.DatabaseError as e:
    print(e)
    print("ERROR: Failed to connect to MySQL!")
    mydb = False
if mydb:
    print(f"MySQL connected to {mydb.user}@{mydb.server_host}")
    mycur = mydb.cursor()
    

def can_user_interrogate(id: int) -> bool:
    """
    Can the user use image recognition (their limit has not run out)

    Args:
        id: Discord ID of the user
    Returns:
        True/False
    """
    return True
    if id == 327762629575704576 or id == 804792397602095134:
        return True
    if not mydb:
        return False
    mycur.execute(f"SELECT * FROM `limits` WHERE `userid`='{id}' LIMIT 1")
    result = mycur.fetchone()
    if result is None:
        return True
    last_clip = result[1]
    clip_left = result[2]

    if last_clip != date.today():
        return True
    return clip_left > 0

def decrease_clip_left(id: int, max_uses: int = 3) -> None:
    """
    Subtract from the available CLIP uses for the user

    Args:
        id: Discord ID of the user
        max_uses: The amount of uses a user gets every day (default: 3)
    """
    return
    if not mydb:
        return
    mycur.execute(f"SELECT * FROM `limits` WHERE `userid`='{id}' LIMIT 1")
    result = mycur.fetchone()
    if result is None:
        mycur.execute(f"INSERT INTO `limits` VALUES ('{id}', '{date.today()}', '{max_uses-1}')")
        mydb.commit()
        return
    last_clip = result[1]
    clip_left = result[2]
    if last_clip != date.today() and clip_left <= 0:
        clip_left = max_uses
    clip_left -= 1
    mycur.execute(f"UPDATE `limits` SET `clip_left`='{clip_left}', `last_clip`='{date.today()}' WHERE `userid`='{id}'")
    mydb.commit()