import bot
from bot import check_user, db, save_db
class MockUser:
    id = 999999
    username = "someotheruser"
class MockChat:
    id = 999999
class MockMessage:
    from_user = MockUser()
    chat = MockChat()
    message_id = 111
    text = "/start"

try:
    print("Initial db:", db)
    check_user(MockMessage(), is_start=True)
    print("After check_user:", db)
except Exception as e:
    print("Error:", e)
