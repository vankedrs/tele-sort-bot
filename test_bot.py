import telebot
class MockUser:
    id = 12345
    username = "testuser"
class MockChat:
    id = 12345
class MockMessage:
    from_user = MockUser()
    chat = MockChat()
    message_id = 999
    text = "/start"

import bot
bot.bot = telebot.TeleBot('invalid') # disable real bot
try:
    print("Testing check_user with is_start=True")
    res = bot.check_user(MockMessage(), is_start=True)
    print("Result:", res)
    print("Registered users:", bot.db["registered"])
except Exception as e:
    import traceback
    traceback.print_exc()
