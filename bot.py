import os, time, json, math, logging, threading
from datetime import datetime

try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
    import binance.enums as enums
except ImportError:
    print("pip install python-binance")
    exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

class Config:
    API_KEY = os.environ.get("BINANCE_API_KEY", "")
    API_SECRET = os.environ.get("BINANCE_API_SECRET", "")
    TESTNET = os.environ.get("TESTNET", "true").lower() == "true"
    SYMBOL = os.environ.get("SYMBOL", "BTCUSDT")
    GRID_LEVELS = int(os.environ.get("GRID_LEVELS", "5"))
    GRID_SPACING = float(os.environ.get("GRID_SPACING", "0.5"))
    TOTAL_USDT = float(os.environ.get("TOTAL_USDT", "100"))
    LEVERAGE = int(os.environ.get("LEVERAGE", "3"))
    STOP_LOSS_PCT = float(os.environ.get("STOP_LOSS_PCT", "10"))
    TAKE_PROFIT_PCT = float(os.environ.get("TAKE_PROFIT_PCT", "20"))
    STATE_FILE = "state.json"

state = {
    "running": False, "symbol": Config.SYMBOL,
    "balance": 0.0, "start_balance": 0.0,
    "pnl": 0.0, "pnl_pct": 0.0,
    "grid_levels": [], "active_orders": [],
    "trades": [], "total_trades": 0,
    "wins": 0, "losses": 0,
    "current_price": 0.0, "leverage": Config.LEVERAGE,
    "strategy": "GRID", "last_update": "",
    "logs": [], "error": None, "testnet": Config.TESTNET,
}

def save_state():
    with open(Config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)

def add_log(level, msg):
    entry = {"time": datetime.now().strftime("%H:%M:%S"), "level": level, "msg": msg}
    state["logs"].append(entry)
    if len(state["logs"]) > 100:
        state["logs"] = state["logs"][-100:]
    log.info(f"[{level}] {msg}")
    save_state()

class GridBot:
    def __init__(self):
        self.client = None
        self.running = False
        self.grid_orders = {}
        self.start_balance = 0.0
        self._thread = None

    def connect(self):
        try:
            self.client = Client(Config.API_KEY, Config.API_SECRET, testnet=Config.TESTNET)
            self.client.ping()
            add_log("ok", "Binance baglantisi basarili")
            return True
        except Exception as e:
            add_log("err", f"Baglanti hatasi: {str(e)}")
            state["error"] = str(e)
            save_state()
            return False

    def setup_futures(self):
        try:
            self.client.futures_change_leverage(symbol=Config.SYMBOL, leverage=Config.LEVERAGE)
            add_log("info", f"Kaldirac {Config.LEVERAGE}x ayarlandi")
        except BinanceAPIException as e:
            if "No need to change" not in str(e):
                add_log("warn", f"Ayar uyarisi: {e.message}")

    def get_balance(self):
        try:
            account = self.client.futures_account_balance()
            for asset in account:
                if asset["asset"] == "USDT":
                    return float(asset["balance"])
        except Exception as e:
            add_log("err", f"Bakiye alinamadi: {e}")
        return 0.0

    def get_price(self):
        try:
            ticker = self.client.futures_symbol_ticker(symbol=Config.SYMBOL)
            return float(ticker["price"])
        except:
            return 0.0

    def get_precision(self):
        try:
            info = self.client.futures_exchange_info()
            for s in info["symbols"]:
                if s["symbol"] == Config.SYMBOL:
                    for f in s["filters"]:
                        if f["filterType"] == "LOT_SIZE":
                            step = float(f["stepSize"])
                            return int(round(-math.log(step, 10), 0))
        except:
            pass
        return 3

    def place_grid(self, price):
        add_log("info", f"Grid kuruluyor | Fiyat: {price}")
        precision = self.get_precision()
        usdt_per = Config.TOTAL_USDT / Config.GRID_LEVELS
        spacing = Config.GRID_SPACING / 100
        placed = 0
        for i in range(1, Config.GRID_LEVELS + 1):
            buy_price = round(price * (1 - spacing * i), 2)
            sell_price = round(price * (1 + spacing * i), 2)
            qty = round((usdt_per * Config.LEVERAGE) / price, precision)
            if qty <= 0:
                continue
            try:
                bo = self.client.futures_create_order(
                    symbol=Config.SYMBOL, side=enums.SIDE_BUY,
                    type=enums.ORDER_TYPE_LIMIT,
                    timeInForce=enums.TIME_IN_FORCE_GTC,
                    quantity=qty, price=buy_price)
                self.grid_orders[buy_price] = bo["orderId"]
                so = self.client.futures_create_order(
                    symbol=Config.SYMBOL, side=enums.SIDE_SELL,
                    type=enums.ORDER_TYPE_LIMIT,
                    timeInForce=enums.TIME_IN_FORCE_GTC,
                    quantity=qty, price=sell_price)
                self.grid_orders[sell_price] = so["orderId"]
                placed += 2
                time.sleep(0.15)
            except BinanceAPIException as e:
                add_log("err", f"Emir hatasi: {e.message}")
        state["grid_levels"] = [{"price": p, "order_id": oid} for p, oid in self.grid_orders.items()]
        add_log("ok", f"Grid tamam: {placed} emir")

    def cancel_all(self):
        try:
            self.client.futures_cancel_all_open_orders(symbol=Config.SYMBOL)
            self.grid_orders.clear()
            state["grid_levels"] = []
            add_log("warn", "Tum emirler iptal edildi")
        except Exception as e:
            add_log("err", f"Iptal hatasi: {e}")

    def check_trades(self):
        try:
            trades = self.client.futures_account_trades(symbol=Config.SYMBOL, limit=10)
            for t in trades:
                tid = t["id"]
                if tid in [x["id"] for x in state["trades"]]:
                    continue
                pnl = float(t.get("realizedPnl", 0))
                entry = {
                    "id": tid,
                    "time": datetime.fromtimestamp(t["time"]/1000).strftime("%H:%M:%S"),
                    "side": t["side"], "price": float(t["price"]),
                    "qty": float(t["qty"]), "pnl": pnl, "symbol": Config.SYMBOL
                }
                state["trades"].insert(0, entry)
                state["trades"] = state["trades"][:50]
                state["total_trades"] += 1
                if pnl > 0:
                    state["wins"] += 1
                    add_log("ok", f"{t['side']} | +${pnl:.4f}")
                else:
                    state["losses"] += 1
                    add_log("err", f"{t['side']} | -${abs(pnl):.4f}")
        except Exception as e:
            add_log("err", f"Trade kontrol hatasi: {e}")

    def check_risk(self, balance):
        if self.start_balance <= 0:
            return True
        pct = ((balance - self.start_balance) / self.start_balance) * 100
        if pct <= -Config.STOP_LOSS_PCT:
            add_log("err", f"STOP LOSS! {pct:.1f}%")
            return False
        if pct >= Config.TAKE_PROFIT_PCT:
            add_log("ok", f"TAKE PROFIT! +{pct:.1f}%")
            return False
        return True

    def run_loop(self):
        if not self.connect():
            self.running = False
            state["running"] = False
            save_state()
            return
        self.setup_futures()
        balance = self.get_balance()
        self.start_balance = balance
        state["start_balance"] = balance
        add_log("info", f"Baslangic bakiyesi: ${balance:.2f}")
        if balance < 10:
            add_log("err", "Bakiye cok dusuk!")
            self.running = False
            state["running"] = False
            save_state()
            return
        price = self.get_price()
        state["current_price"] = price
        self.place_grid(price)
        last_rebalance = time.time()
        while self.running:
            try:
                price = self.get_price()
                balance = self.get_balance()
                state["current_price"] = price
                state["balance"] = balance
                state["pnl"] = balance - self.start_balance
                state["pnl_pct"] = ((balance - self.start_balance) / self.start_balance * 100) if self.start_balance > 0 else 0
                state["last_update"] = datetime.now().strftime("%H:%M:%S")
                self.check_trades()
                if not self.check_risk(balance):
                    self.cancel_all()
                    self.running = False
                    state["running"] = False
                    save_state()
                    break
                if time.time() - last_rebalance > 3600:
                    self.cancel_all()
                    self.place_grid(price)
                    last_rebalance = time.time()
                save_state()
                time.sleep(10)
            except BinanceAPIException as e:
                add_log("err", f"Binance hatasi: {e.message}")
                time.sleep(30)
            except Exception as e:
                add_log("err", f"Hata: {str(e)}")
                time.sleep(30)
        add_log("warn", "Bot durdu")

    def start(self):
        if self.running:
            return False
        self.running = True
        state["running"] = True
        state["error"] = None
        self._thread = threading.Thread(target=self.run_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        add_log("warn", "Bot durduruluyor...")
        self.running = False
        state["running"] = False
        if self.client:
            self.cancel_all()
        save_state()

bot = GridBot()
