import telebot
bot = telebot.TeleBot('invalid')
try:
    print(telebot.util.escape("`bin_remove`"))
except Exception as e:
    print(e)
