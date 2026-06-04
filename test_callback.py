import telebot
class MockUser:
    id = 123456
    username = "test"
class MockCall:
    from_user = MockUser()
    data = "test"
import bot
try:
    bot.log_callback_activity(MockCall())
    print("Success")
except Exception as e:
    print("Error:", e)
