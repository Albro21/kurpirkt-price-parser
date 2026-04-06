# Price Parser for Kurpirkt.lv

A Python script that monitors product prices on [kurpirkt.lv](https://www.kurpirkt.lv) and sends Telegram notifications when prices change.

## Features

- Monitors multiple products simultaneously
- Tracks price history in JSON files
- Sends Telegram notifications on price changes
- Rotating log files with detailed logging
- Easy-to-use configuration file

## Setup

### 1. Clone or Download

```bash
git clone https://github.com/Albro21/kurpirkt-price-parser.git
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Items

Copy the example config and add your items:

```bash
cp config.json.example config.json
```

Edit `config.json` and add the products you want to monitor:

```json
{
  "items": {
    "Product Name": "https://www.kurpirkt.lv/cena.php?q=product+search+query",
    "Another Product": "https://www.kurpirkt.lv/cena.php?q=another+search"
  }
}
```

### 5. Set Telegram Credentials

Copy the environment variables example:

```bash
cp .env.example .env
```

Edit `.env` and add your Telegram credentials:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

Load the environment variables:

```bash
export $(cat .env | xargs)
```

Or add them directly to your systemd service file.

## Usage

### Run Once

```bash
python3 main.py
```

### Run with Cron (Periodic)

To run the script every hour:

```bash
crontab -e
```

Add this line:

```
0 * * * * cd /home/albert/programming/kurpirkt-price-parser && export $(cat .env | xargs) && /home/albert/programming/kurpirkt-price-parser/venv/bin/python main.py
```

## Logs

Logs are saved to `logs/parser.log` with automatic rotation (10MB max, 5 backups).

View logs:

```bash
tail -f logs/parser.log
```

## License

MIT
