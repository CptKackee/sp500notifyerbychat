import configparser
import io
import logging
import requests
import yfinance as yf
from jinja2 import Environment, FileSystemLoader
from matplotlib import pyplot as plt


def distance(row, base, value):
    return (row[base] - row[value]) / row[base]


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
        ticker = yf.Ticker(symbol["symbol"])
        symbol["data"] = ticker.history(period=self.config.get("reporting", "history_period"))
        self.stoke_data.append(symbol)

    def calculate_sma_values(self):
        for window in self.__get_sma_windows():
            for symbol in self.stoke_data:
                symbol["data"][f"SMA{window}"] = symbol["data"]["Close"].rolling(window=window).mean()
                symbol["data"][f"Distance SMA{window}"] = symbol["data"].apply(
                    distance, axis=1, args=("Close", f"SMA{window}")
                )

    def generate_graph_for_main_symbol(self):
        dp = self.config.getint("reporting", "datapoints_for_graph")
        df = self.stoke_data[0]["data"].tail(dp)
        cols = ["Close"] + [f"SMA{w}" for w in self.__get_sma_windows()]
        df[cols].plot()
        plt.title(self.stoke_data[0]["name"])
        plt.grid()
        graph_file = io.BytesIO()
        plt.savefig(graph_file, format="png")
        graph_file.seek(0)
        return graph_file

    def send_report(self):
        message = self.jinja_env.get_template("message_body.j2").render(
            symbols=self.stoke_data,
            sma_windows=self.__get_sma_windows(),
        )
        data = {
            "user": self.config.get("pushover", "user"),
            "token": self.config.get("pushover", "token"),
            "message": message,
        }
        files = {'attachment': self.generate_graph_for_main_symbol()}
        requests.post("https://api.pushover.net:443/1/messages.json", data=data, files=files)

    def run(self):
        self.load_historical_stock_data()
        self.calculate_sma_values()
        self.send_report()


if __name__ == "__main__":
    n = Notifyer("config.ini")
    n.run()
