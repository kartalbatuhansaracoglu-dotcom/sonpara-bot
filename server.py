import os
import json
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from bot import bot, state, Config, save_state, add_log

app = Flask(__name__)
CORS(app)

@app.route("/api/state")
def get_state():
    return jsonify(state)

@app.route("/api/start", methods=["POST"])
def start_bot():
    body = request.get_json(silent=True) or {}
    if "symbol" in body:
        Config.SYMBOL = body["symbol"]
        state["symbol"] = body["symbol"]
    if "leverage" in body:
        Config.LEVERAGE = int(body["leverage"])
    if "gridLevels" in body:
        Config.GRID_LEVELS = int(body["gridLevels"])
    if "gridSpacing" in body:
        Config.GRID_SPACING = float(body["gridSpacing"])
    if "totalUsdt" in body:
        Config.TOTAL_USDT = float(body["totalUsdt"])
    if "stopLoss" in body:
        Config.STOP_LOSS_PCT = float(body["stopLoss"])
    if "takeProfit" in body:
        Config.TAKE_PROFIT_PCT = float(body["takeProfit"])
    success = bot.start()
    return jsonify({"ok": success})

@app.route("/api/stop", methods=["POST"])
def stop_bot():
    bot.stop()
    return jsonify({"ok": True})

@app.route("/api/emergency", methods=["POST"])
def emergency_stop():
    add_log("err", "ACİL DURUŞ!")
    bot.stop()
    return jsonify({"ok": True})

@app.route("/api/config", methods=["GET", "POST"])
def config():
    if request.method == "GET":
        return jsonify({
            "symbol": Config.SYMBOL,
            "gridLevels": Config.GRID_LEVELS,
            "gridSpacing": Config.GRID_SPACING,
            "totalUsdt": Config.TOTAL_USDT,
            "leverage": Config.LEVERAGE,
            "stopLoss": Config.STOP_LOSS_PCT,
            "takeProfit": Config.TAKE_PROFIT_PCT,
            "testnet": Config.TESTNET,
        })
    else:
        body = request.get_json(silent=True) or {}
        if "symbol" in body: Config.SYMBOL = body["symbol"]
        if "gridLevels" in body: Config.GRID_LEVELS = int(body["gridLevels"])
        if "gridSpacing" in body: Config.GRID_SPACING = float(body["gridSpacing"])
        if "totalUsdt" in body: Config.TOTAL_USDT = float(body["totalUsdt"])
        if "leverage" in body: Config.LEVERAGE = int(body["leverage"])
        if "stopLoss" in body: Config.STOP_LOSS_PCT = float(body["stopLoss"])
        if "takeProfit" in body: Config.TAKE_PROFIT_PCT = float(body["takeProfit"])
        return jsonify({"ok": True})

@app.route("/")
def index():
    return send_file("index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
