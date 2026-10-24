# BankTracker Bot

Private Telegram bot for tracking outgoing Bangladesh bank/MFS payments from receipt screenshots.

## macOS setup

```bash
brew install tesseract
cd ~/Downloads/BankTrackerBot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set your BotFather token and numeric Telegram user ID.

Run:

```bash
python bot.py
```

Commands: `/today`, `/month`, `/total`, `/search keyword`, `/export`, `/delete ID`.

OCR is heuristic. Always review detected fields before saving.
