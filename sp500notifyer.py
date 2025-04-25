import configparser
import io
import logging
import requests
import yfinance as yf
from jinja2 import Environment, FileSystemLoader
from matplotlib import pyplot as plt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sp500notifyer")

def distance(row, base, value):
    return (row[base] - row[value]) / row[base]

def check_price_crossover(df, sma_window):
    close_today = df["Close"].iloc[-1]
    close_yesterday = df["Close"].iloc[-2]
    sma_today = df[f"SMA{sma_window}"].iloc[-1]
    sma_yesterday = df[f"SMA{sma_window}"].iloc[-2]

    if close_yesterday < sma_yesterday and close_today > sma_today:
        return f"⚠️ Kurs hat SMA{sma_window} nach oben durchbrochen"
    elif close_yesterday > sma_yesterday and close_today < sma_today:
        return f"⚠️ Kurs hat SMA{sma_window} nach unten durchbrochen"
    return None

def check_sma_cross(df, short_window=50, long_window=200):
    short_yesterday = df[f"SMA{short_window}"].iloc[-2]
    short_today = df[f"SMA{short_window}"].iloc[-1]
    long_yesterday = df[f"SMA{long_window}"].iloc[-2]
    long_today = df[f"SMA{long_window}"].iloc[-1]

    if short_yesterday < long_yesterday and short_today > long_today:
        return "🌟 Golden Cross (SMA50 kreuzt SMA200 nach oben)"
    elif short_yesterday > long_yesterday and short_today < long_today:
        return "⚠️ Death Cross (SMA50 kreuzt SMA200 nach unten)"
    return None

class Notifyer:
    def __init__(self, config_path):
        self.stoke_data = []
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        self.__setup_template_engine()

    def __setup_template_engine(self):
        self.jinja_env = Environment(loader=FileSystemLoader("."), trim_blocks=True)

    def __get_sma_windows(self):
        windows_raw = self.config.get("reporting", "sma_windows").split(",")
        return sorted([int(w.strip()) for w in windows_raw], reverse=True)

    def load_historical_stock_data(self):
        symbol = {
            "name": self.config.get("main_symbol", "name"),
            "symbol": self.config.get("main_symbol", "symbol")
        }
        logger.info(f"Lade historische Daten für {symbol['symbol']}")
        ticker = yf.Ticker(symbol["symbol"])
        symbol["data"] = ticker.history(period=self.config.get("reporting", "history_period"))
        self.stoke_data.append(symbol)

    def calculate_sma_values(self):
        for window in self.__get_sma_windows():
            for symbol in self.stoke_data:
                logger.info(f"Berechne SMA{window} für {symbol['symbol']}")
                symbol["data"][f"SMA{window}"] = symbol["data"]["Close"].rolling(window=window).mean()
                symbol["data"][f"Distance SMA{window}"] = symbol["data"].apply(
                    distance, axis=1, args=("Close", f"SMA{window}")
                )

    def generate_graph_for_main_symbol(self):
        df = self.stoke_data[0]["data"]
        df = df.tail(10)  # Zeige nur letzte 10 Tage im Plot
        cols = ["Close"] + [f"SMA{w}" for w in self.__get_sma_windows()]
        plt.style.use("ggplot")
        fig, ax = plt.subplots(figsize=(5, 8))  # Hochformat für bessere Anzeige auf iPhone
        df[cols].plot(ax=ax, linewidth=1.5)
        ax.set_title(self.stoke_data[0]["name"], fontsize=14)
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.legend(loc="upper left", fontsize=8, frameon=False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        return buf

    def send_report(self):
        df = self.stoke_data[0]["data"]
        sma_windows = self.__get_sma_windows()
        cross_msgs = []

        for window in sma_windows:
            msg = check_price_crossover(df, window)
            if msg:
                cross_msgs.append(msg)

        if 50 in sma_windows and 200 in sma_windows:
            sma_cross = check_sma_cross(df, 50, 200)
            if sma_cross:
                cross_msgs.append(sma_cross)

        if not cross_msgs:
            cross_msgs.append("ℹ️ Keine Kreuzung oder besondere Bewegung erkannt.")

        logger.info("Sende Pushover-Benachrichtigung...")
        message = self.jinja_env.get_template("message_body.j2").render(
            symbols=self.stoke_data,
            sma_windows=sma_windows,
            cross_msgs=cross_msgs,
        )

        data = {
            "user": self.config.get("pushover", "user"),
            "token": self.config.get("pushover", "token"),
            "message": message,
        }
        files = {"attachment": self.generate_graph_for_main_symbol()}
        response = requests.post("https://api.pushover.net:443/1/messages.json", data=data, files=files)
        response.raise_for_status()
        logger.info("Push erfolgreich gesendet.")

    def run(self):
        self.load_historical_stock_data()
        self.calculate_sma_values()
        self.send_report()


if __name__ == "__main__":
    n = Notifyer("config.ini")
    n.run()
