# Premium Telegram CC Utility Bot

An advanced, high-performance Telegram Bot built with Python (Telebot & Flask) for manipulating, filtering, and organizing massive Credit Card (CC) datasets. Features a beautiful, interactive Glassmorphism-style Web App for dynamic cross-filtering, and a Max-Heap optimized randomizer for lightning-fast operations.

## ✨ Features

- **🌟 Interactive Web App Filter**
  A premium Telegram Web App built with native CSS variables for dynamic Light/Dark mode. Allows real-time, zero-latency cross-filtering of massive datasets by Country, Bank, Brand, Type, and Level.
- **🧹 Clean Formatting**
  Automatically fix messy formats, pad missing digits, check Luhn algorithms, remove expired cards, and delete duplicates.
- **✂️ Split File**
  Divide a massive `.txt` file into smaller, manageable chunks of any size you want.
- **🎲 Randomize (Anti-Clash)**
  Smartly shuffle your list to ensure cards with the same BIN are spread apart. Uses a highly optimized Max-Heap (Priority Queue) algorithm capable of sorting hundreds of thousands of lines in milliseconds.
- **🛠️ BIN Tools**
  - **Extract BINs**: Extract and identify unique BINs from a list (includes Bank and Country Flags).
  - **Extract Specific BINs**: Pull out cards that match a specific list of 6-11 digit BINs.
  - **Sort by BIN**: Group and sort your entire file cleanly by BIN prefixes.

## 🚀 Tech Stack

- **Backend**: Python 3, PyTelegramBotAPI (Telebot), Flask
- **Frontend**: HTML5, CSS3 (Glassmorphism), Vanilla JavaScript, Telegram Web Apps API
- **Tunneling**: Cloudflare Tunnels (for securely exposing the Web App)
- **Database**: In-memory JSON and CSV parsing for extreme performance.

## 🛠️ Installation

1. Clone this repository.
2. Install the required Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the root directory and add the following variables:
   ```env
   BOT_TOKEN=your_telegram_bot_token
   ALLOWED_ID=your_telegram_user_id
   TUNNEL_URL=your_cloudflare_tunnel_url
   ```
4. Start the Cloudflare Tunnel to expose your local Flask server on port `5001`.
5. Run the bot:
   ```bash
   python3 bot.py
   ```

## 📱 How to Use

1. Start the bot on Telegram with `/start`.
2. Send a `.txt` file containing your data.
3. Reply to that specific file with one of the available commands (e.g., `/filter`, `/clean`, `/random 6`, `/bin`).
4. Follow the interactive inline buttons or the Web App interface to process your file.

## 📝 License
This project is for educational and utility purposes. Use responsibly.
