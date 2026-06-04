import telebot
class MockUser:
    id = 123456
    username = "testuser2"
class MockChat:
    id = 123456
class MockMessage:
    from_user = MockUser()
    chat = MockChat()
    message_id = 1000
    text = "/clean"

import bot
bot.bot = telebot.TeleBot('invalid') # disable real bot
try:
    print("Testing check_user with is_start=False")
    res = bot.check_user(MockMessage(), is_start=False)
    print("Result:", res)
except Exception as e:
    import traceback
    traceback.print_exc()
