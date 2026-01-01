#6-12 signal new (fixed)
import pandas as pd
import requests
import os
import time
from datetime import datetime, time as dt_time

# =============================
# Telegram（GitHub Actions / 環境變數）
# =============================
BOT_TOKEN = os.getenv("7794879562:AAE4WNHF5JrFqpDg7ITDDj0Q3s9EiG10i_8")
CHAT_ID = os.getenv("5414345321")

def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram BOT_TOKEN or CHAT_ID not set. Skipping send.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }
    try:
        resp = requests.post(url, data=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"Failed to send telegram message: {e}")

# =============================
# 參數
# =============================
SYMBOLS = [
    "BTC","ETH","SOL","BNB","XRP","ADA","DOGE","AVAX","DOT","TRX",
    "MATIC","ARB","OP","ATOM","NEAR","FTM","ICP","SUI","LTC","LINK",
    "ALGO","XLM","VET","FIL","EGLD","AAVE","KSM","EOS","XTZ","THETA",
    "MANA","CHZ","BTT","ENJ","ZIL","OMG","DASH","BAT","ZRX","COMP",
    "1INCH","CELR","SAND","GRT","KAVA","ANKR","FLOW","CRV","RSR","QTUM",
    "NANO","SC","IOST","KNC","REN","BAL","SRM","CVC","REP","DGB",
    "STX","HNT","CELO","LRC","NEO","RVN","WAVES","KMD","NKN","OCEAN",
    "CTSI","REEF","SKL","FET","AKRO","GLM","IOTX","STMX","ROSE","COTI",
    "HIVE","NMR","NU","LPT","DENT","QNT","BTG","HBAR","AR","RNDR",
    "ORN","MOVR","ALPHA","RLC","API3","SXP","TRIBE","BAKE"
]

LIMIT = 500
THRESHOLD_LOWER = 2
THRESHOLD_UPPER = 2.5
BASE_URL = "https://min-api.cryptocompare.com/data/v2/histominute"

# =============================
# 取得 K 線
# =============================
def get_klines(symbol):
    params = {
        "fsym": symbol,
        "tsym": "USDT",
        "limit": LIMIT,
        "aggregate": 5,
        "e": "Binance"
    }
    try:
        r = requests.get(BASE_URL, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Request failed for {symbol}: {e}")
        return None

    if data.get("Response") != "Success":
        print(f"API returned non-success for {symbol}: {data.get('Message')}")
        return None

    df = pd.DataFrame(data["Data"]["Data"])
    df["time"] = (
        pd.to_datetime(df["time"], unit="s")
        .dt.tz_localize("UTC")
        .dt.tz_convert("Asia/Taipei")
    )
    df.rename(columns={"volumefrom": "volume"}, inplace=True)
    df[["open","high","low","close","volume"]] = df[
        ["open","high","low","close","volume"]
    ].astype(float)
    return df[["time","open","high","low","close","volume"]]

# =============================
# 計算漲幅
# =============================
def calc_pct_change(df, entry_i):
    # 計算從 entry 到最後一筆的百分比漲幅 (百分比)
    entry = df.close.iloc[entry_i]
    last = df.close.iloc[-1]
    return round((last - entry) / entry * 100, 2)

# =============================
# 主策略 - 即時掃描（回傳符合的字串）
# =============================
def scan(symbol):
    df = get_klines(symbol)
    if df is None or len(df) < 30:
        return None

    today = datetime.now().date()

    for i in range(21, len(df)):
        if df.time.iloc[i].date() != today:
            continue

        v0 = df.volume.iloc[i]
        avg20 = df.volume.iloc[i-21:i].mean()

        if not (avg20 * THRESHOLD_LOWER <= v0 <= avg20 * THRESHOLD_UPPER):
            continue

        open_p = df.open.iloc[i]
        close_p = df.close.iloc[i]

        if abs((close_p - open_p) / open_p) <= 0.003:
            continue

        return f"*{symbol}*  價格：{round(close_p,4)}"

    return None

# =============================
# 回測單一幣種（歷史彙總用）
# =============================
def backtest_symbol(symbol):
    df = get_klines(symbol)
    if df is None or len(df) < 30:
        return []

    today = datetime.now().date()
    start_t = dt_time(1, 0)
    end_t = dt_time(12, 0)
    trades = []

    for i in range(21, len(df)):
        d = df.time.iloc[i].date()
        t = df.time.iloc[i].time()
        if d != today or not (start_t <= t <= end_t):
            continue

        v0 = df.volume.iloc[i]
        past20_avg = df.volume.iloc[i-21:i].mean()
        if not (past20_avg * THRESHOLD_LOWER <= v0 <= past20_avg * THRESHOLD_UPPER):
            continue

        close_p = df.close.iloc[i]
        open_p = df.open.iloc[i]
        past20_closes = df.close.iloc[i-21:i]
        past20_volumes = df.volume.iloc[i-21:i]

        # 跌幅 <= 0.3% 排除
        drop_pct = abs((close_p - open_p) / open_p)
        if drop_pct <= 0.003:
            continue

        # 前一根承接量（prev_v 大於等於過去 20 根 volume 的次數需 >= 2）
        prev_v = df.volume.iloc[i-1]
        if (prev_v >= past20_volumes).sum() < 2:
            continue

        # 當前 close 不低於過去 20 根最低價
        if close_p < past20_closes.min():
            continue

        trades.append({
            "symbol": symbol,
            "calc_date": today,
            "date": d,
            "time": t,
            "price": close_p,
            "pct": calc_pct_change(df, i)
        })

    return trades[-1:] if trades else []

# =============================
# main: 執行掃描並發送 telegram
# =============================
def main():
    # 即時掃描（可視需要改成小清單）
    small_symbols = ["BTC","ETH","SOL","BNB","XRP","ADA"]
    signals = []
    for s in small_symbols:
        r = scan(s)
        if r:
            signals.append(r)
        time.sleep(0.2)

    if signals:
        send_telegram("🚨 *買訊警報*\n\n" + "\n".join(signals))
    else:
        send_telegram("ℹ️ 今日無符合條件買訊")

    # 歷史回測彙總（全部 SYMBOLS）
    all_trades = []
    for sym in SYMBOLS:
        result = backtest_symbol(sym)
        if result:
            all_trades.extend(result)
        time.sleep(0.2)

    # 按漲幅排序
    all_trades.sort(key=lambda x: x["pct"], reverse=True)

    # 每 20 筆發送一次
    for i in range(0, len(all_trades), 20):
        msg = "*📌 歷史買訊彙總（含計算日期）*\n\n"
        for t in all_trades[i:i+20]:
            # 格式化時間與日期為字串
            date_str = t["date"].isoformat() if hasattr(t["date"], "isoformat") else str(t["date"])
            time_str = t["time"].strftime("%H:%M:%S") if hasattr(t["time"], "strftime") else str(t["time"])
            msg += (
                f"*{t['symbol']}* | 計算日: {t['calc_date']} | "
                f"{date_str} {time_str} | "
                f"*{t['pct']}%* | 價格: {round(t['price'],4)}\n"
            )
        send_telegram(msg)
        time.sleep(5)

if __name__ == "__main__":
    main()# =============================
# 回測參數
# =============================
SYMBOLS = [
    "BTC","ETH","SOL","BNB","XRP","ADA","DOGE","AVAX","DOT","TRX",
    "MATIC","ARB","OP","ATOM","NEAR","FTM","ICP","SUI","LTC","LINK",
    "ALGO","XLM","VET","FIL","EGLD","AAVE","KSM","EOS","XTZ","THETA",
    "MANA","CHZ","BTT","ENJ","ZIL","OMG","DASH","BAT","ZRX","COMP",
    "1INCH","CELR","SAND","GRT","KAVA","ANKR","FLOW","CRV","RSR","QTUM",
    "NANO","SC","IOST","KNC","REN","BAL","SRM","CVC","REP","DGB",
    "STX","HNT","CELO","LRC","NEO","RVN","WAVES","KMD","NKN","OCEAN",
    "CTSI","REEF","SKL","FET","AKRO","GLM","IOTX","STMX","ROSE","COTI",
    "HIVE","NMR","NU","LPT","DENT","QNT","BTG","HBAR","AR","RNDR",
    "ORN","MOVR","ALPHA","RLC","API3","SXP","TRIBE","BAKE"
]

LIMIT = 500
THRESHOLD_LOWER = 2
THRESHOLD_UPPER = 2.5
BASE_URL = "https://min-api.cryptocompare.com/data/v2/histominute"

# =============================
# 取得 K 線
# =============================
def get_klines(symbol):
    params = {
        "fsym": symbol,
        "tsym": "USDT",
        "limit": LIMIT,
        "aggregate": 5,
        "e": "Binance"
    }
    r = requests.get(BASE_URL, params=params).json()
    if r.get("Response") != "Success":
        return None

    df = pd.DataFrame(r["Data"]["Data"])
    df["time"] = (
        pd.to_datetime(df["time"], unit="s")
        .dt.tz_localize("UTC")
        .dt.tz_convert("Asia/Taipei")
    )
    df.rename(columns={"volumefrom": "volume"}, inplace=True)
    df[["open","high","low","close","volume"]] = df[
        ["open","high","low","close","volume"]
    ].astype(float)
    return df[["time","open","high","low","close","volume"]]

# =============================
# 計算漲幅
# =============================
def calc_pct_change(df, entry_i):
    entry = df.close.iloc[entry_i]
    last = df.close.iloc[-1]
    return round((last - entry) / entry * 100, 2)

# =============================
# 回測單一幣種
# =============================
def backtest_symbol(symbol):
    df = get_klines(symbol)
    if df is None or len(df) < 30:
        return []

    today = datetime.now().date()
    start_t = dt_time(1, 0)
    end_t = dt_time(12, 0)
    trades = []

    for i in range(21, len(df)):
        d = df.time.iloc[i].date()
        t = df.time.iloc[i].time()
        if d != today or not (start_t <= t <= end_t):
            continue

        v0 = df.volume.iloc[i]
        past20_avg = df.volume.iloc[i-21:i].mean()
        if not (past20_avg * THRESHOLD_LOWER <= v0 <= past20_avg * THRESHOLD_UPPER):
            continue

        close_p = df.close.iloc[i]
        open_p = df.open.iloc[i]
        past20_closes = df.close.iloc[i-21:i]
        past20_volumes = df.volume.iloc[i-21:i]

        # 跌幅 <= 0.3% 排除
        drop_pct = abs((close_p - open_p) / open_p)
        if drop_pct <= 0.003:
            continue

        # 前一根承接量
        prev_v = df.volume.iloc[i-1]
        if sum(prev_v >= past20_volumes) < 2:
            continue

        if close_p < past20_closes.min():
            continue

        trades.append({
            "symbol": symbol,
            "calc_date": today,
            "date": d,
            "time": t,
            "price": close_p,
            "pct": calc_pct_change(df, i)
        })

    return trades[-1:] if trades else []

# =============================
# Telegram 匯總
# =============================
all_trades = []

for sym in SYMBOLS:
    result = backtest_symbol(sym)
    if result:
        all_trades.extend(result)
    time.sleep(0.2)

# 按漲幅排序
all_trades.sort(key=lambda x: x["pct"], reverse=True)

# 每 20 幣種發送
for i in range(0, len(all_trades), 20):
    msg = "*📌 歷史買訊彙總（含計算日期）*\n\n"
    for t in all_trades[i:i+20]:
        msg += (
            f"*{t['symbol']}* | 計算日: {t['calc_date']} | "
            f"{t['date']} {t['time']} | "
            f"*{t['pct']}%* | 價格: {round(t['price'],4)}\n"
        ）
    time.sleep(5)
