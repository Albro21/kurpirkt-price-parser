from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import requests


class PriceParser:
    """Main parser for kurpirkt.lv price monitoring."""
    
    def __init__(self, log_file="logs/parser.log"):
        self.logger = self._setup_logging(log_file)
        self.session = requests.Session()
    
    def _setup_logging(self, log_file):
        """Setup logging to file and console."""
        logger = logging.getLogger("salidzini_parser")
        logger.setLevel(logging.DEBUG)
        
        log_path = Path(log_file)
        log_path.parent.mkdir(exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
    
    def parse_page(self, url, item_name):
        """Parse prices from kurpirkt.lv page using Playwright to bypass Cloudflare."""
        browser = None
        try:
            self.logger.info(f"Parsing: {item_name}")
            
            # Launch headless browser with stealth mode
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                    ]
                )
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )
                page = context.new_page()
                
                # Add stealth script to avoid detection
                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => false,
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5],
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en'],
                    });
                """)
                
                # Navigate to page and wait for content to load
                self.logger.debug(f"Navigating to {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Wait a bit for dynamic content
                page.wait_for_timeout(5000)
                
                # Wait for price containers to appear
                try:
                    page.wait_for_selector('div.precebloks', timeout=30000)
                except:
                    self.logger.warning(f"Price containers not found for {item_name}, proceeding with available content")
                
                # Get page HTML after JS execution
                html = page.content()
                
                # Debug: Log first 3000 characters of HTML
                self.logger.debug(f"Page HTML for {item_name} (first 3000 chars):\n{html[:3000]}")
                
                page.close()
                context.close()
                browser.close()
            
            soup = BeautifulSoup(html, 'html.parser')
            containers = soup.find_all('div', class_="precebloks")
            
            if not containers:
                self.logger.warning(f"No containers found for {item_name}")
                return {}
            
            items_data = {}
            for container in containers:
                shop_elem = container.find('div', class_="name")
                shop_name = shop_elem.get_text(strip=True) if shop_elem else "Unknown Shop"
                
                price_elem = container.find('div', class_="price")
                price = price_elem.get_text(strip=True) if price_elem else "N/A"
                
                items_data[shop_name] = price
            
            self.logger.info(f"✓ Successfully parsed {item_name}: {len(items_data)} shops found")
            return items_data
            
        except Exception as e:
            self.logger.error(f"Error parsing {item_name}: {e}")
            if browser:
                try:
                    browser.close()
                except:
                    pass
            return {}
    
    def save_to_json(self, data, filename):
        """Save data to JSON file."""
        try:
            output_path = Path(filename)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.logger.debug(f"Saved data to {output_path}")
        except Exception as e:
            self.logger.error(f"Error saving to {filename}: {e}")
    
    def load_previous_prices(self, filename):
        """Load previous cheapest price from JSON file."""
        path = Path(filename)
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Return the entire data dict, not just shop names
                return data
            except (json.JSONDecodeError, IOError):
                return {}
        return {}
    
    @staticmethod
    def get_cheapest_price(items_data):
        """Get cheapest price and shop from items data."""
        if not items_data:
            return None, None
        
        prices = {}
        for shop, price in items_data.items():
            try:
                numeric_price = float(''.join(c for c in price if c.isdigit() or c == '.'))
                prices[shop] = numeric_price
            except (ValueError, AttributeError):
                continue
        
        if not prices:
            return None, None
        
        cheapest_shop = min(prices, key=prices.get)
        return cheapest_shop, prices[cheapest_shop]


class TelegramNotifier:
    """Handle Telegram notifications."""
    
    def __init__(self, bot_token, chat_id, logger):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        self.logger = logger
    
    def send_price_update(self, item_name, cheapest_shop, current_price, previous_price, url):
        """Send price change notification to Telegram."""
        if not self.bot_token or self.bot_token == "YOUR_BOT_TOKEN_HERE":
            self.logger.warning("Telegram not configured (skipping notification)")
            return
        
        try:
            message = f"📊 <b>Price update</b>\n"
            message += f"💰 <b>{item_name}</b>\n"
            message += f"🏪 Cheapest at: <b>{cheapest_shop}</b>\n"
            message += f"💵 Current price: <b>{current_price}€</b>"
            message += f"\n📈 Previous price: {previous_price}€"
            message += f"\n🔗 Available at: <a href=\"{url}\">{url}</a>"
            
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            
            response = requests.post(self.api_url, json=payload, timeout=10)
            if response.status_code == 200:
                self.logger.info(f"Telegram notification sent for {item_name}")
            else:
                self.logger.error(f"Failed to send Telegram notification for {item_name}: {response.status_code}")
        except Exception as e:
            self.logger.error(f"Error sending Telegram notification for {item_name}: {e}")


def load_config(config_file="config.json"):
    """Load items configuration from JSON file."""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config.get("items", {})
    except FileNotFoundError:
        print(f"Error: {config_file} not found")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: {config_file} is not valid JSON")
        sys.exit(1)


def main():
    """Main execution."""
    items = load_config()
    
    if not items:
        print("Error: No items found in config.json")
        sys.exit(1)
    
    parser = PriceParser()
    notifier = TelegramNotifier(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        logger=parser.logger
    )
    
    parser.logger.info("=" * 50)
    parser.logger.info("Starting price parser")
    parser.logger.info("=" * 50)
    
    try:
        updates = []
        
        for item_name, url in items.items():
            parser.logger.info(f"Processing: {item_name}")
            items_data = parser.parse_page(url, item_name)
            
            if items_data:
                filename = f"data/{item_name.replace(' ', '_').lower()}.json"
                
                cheapest_shop, cheapest_price = PriceParser.get_cheapest_price(items_data)
                previous_data = parser.load_previous_prices(filename)
                previous_cheapest_price = None
                is_first_tracking = not previous_data
                
                # Get the previous cheapest price (might be from a different shop)
                if previous_data:
                    try:
                        # Find the cheapest price from previous data
                        previous_prices = {}
                        for shop, price in previous_data.items():
                            try:
                                numeric_price = float(str(price).replace(',', '.'))
                                previous_prices[shop] = numeric_price
                            except (ValueError, TypeError):
                                continue
                        if previous_prices:
                            previous_cheapest_price = min(previous_prices.values())
                    except (ValueError, TypeError):
                        previous_cheapest_price = None
                
                parser.save_to_json(items_data, filename)
                
                if cheapest_shop and cheapest_price:
                    if is_first_tracking:
                        # First time tracking this item
                        updates.append((item_name, cheapest_shop, cheapest_price, "N/A (first tracking)"))
                        notifier.send_price_update(item_name, cheapest_shop, cheapest_price, "N/A (first tracking)", url)
                    elif previous_cheapest_price is not None:
                        if cheapest_price < previous_cheapest_price:
                            # Price decreased (good news!)
                            updates.append((item_name, cheapest_shop, cheapest_price, previous_cheapest_price))
                            notifier.send_price_update(item_name, cheapest_shop, cheapest_price, previous_cheapest_price, url)
                        elif cheapest_price > previous_cheapest_price:
                            # Price increased (warning)
                            message = f"⚠️ <b>Price increased</b>\n"
                            message += f"💰 <b>{item_name}</b>\n"
                            message += f"🏪 Cheapest at: <b>{cheapest_shop}</b>\n"
                            message += f"💵 Current price: <b>{cheapest_price}€</b>"
                            message += f"\n📈 Previous price: {previous_cheapest_price}€"
                            message += f"\n🔗 Available at: <a href=\"{url}\">{url}</a>"
                            
                            try:
                                payload = {
                                    "chat_id": notifier.chat_id,
                                    "text": message,
                                    "parse_mode": "HTML"
                                }
                                response = requests.post(notifier.api_url, json=payload, timeout=10)
                                if response.status_code == 200:
                                    parser.logger.info(f"Price increase notification sent for {item_name}")
                                    updates.append((item_name, cheapest_shop, cheapest_price, previous_cheapest_price))
                            except Exception as e:
                                parser.logger.error(f"Error sending price increase notification for {item_name}: {e}")
        
        if not updates:
            parser.logger.info("No price updates detected for any items")
            try:
                payload = {
                    "chat_id": notifier.chat_id,
                    "text": "✅ No price updates - all items remain unchanged",
                    "parse_mode": "HTML"
                }
                response = requests.post(notifier.api_url, json=payload, timeout=10)
                if response.status_code == 200:
                    parser.logger.info("No-update notification sent to Telegram")
            except Exception as e:
                parser.logger.error(f"Error sending no-update notification: {e}")
        
        parser.logger.info("=" * 50)
        parser.logger.info("Parsing complete!")
        parser.logger.info("=" * 50)
    
    except Exception as e:
        parser.logger.exception(f"Fatal error in main execution: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Script interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
