from dotenv import load_dotenv
import os
import pandas as pd
import pandas_ta as ta
from apscheduler.schedulers.blocking import BlockingScheduler
from oandapyV20 import API
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.trades as trades
from oandapyV20.contrib.requests import MarketOrderRequest
from oanda_candles import Pair, Gran, CandleClient
from oandapyV20.contrib.requests import TakeProfitDetails, StopLossDetails



"""
    Determine if there is an upwards trend or a downwards trend given the EMA curves of the last n(backcandles) candles

    backcandles: The number of candles to determine the EMA trend for
"""
def ema_signal(df, current_candle, backcandles):
    df_slice = df.reset_index().copy()
    # Get the range of candles
    start = max(0, current_candle - backcandles)
    end = current_candle
    df_range = df_slice.iloc[start:end]

    if all(df_range["EMA_fast"] < df_range["EMA_slow"]):
        return 1 # Downtrend
    elif all(df_range["EMA_fast"] > df_range["EMA_slow"]):
        return 2 # Uptrend
    else:
        return 0


def total_signal(df, current_candle, backcandles):
    if (ema_signal(df, current_candle, backcandles) == 2 and df.Close[current_candle] <= df['BBL_15_1.5'][current_candle]):
        return 2 # Long signal
    
    if (ema_signal(df, current_candle, backcandles) == 1 and df.Close[current_candle] >= df['BBU_15_1.5'][current_candle]):
        return 1 # Short signal
    
    return 0

load_dotenv()

"""
    Get the last n candles.
"""
def get_candles(n):
    client = CandleClient(os.getenv('OANDA_API_KEY'), real=False)
    collector = client.get_collector(Pair.EUR_USD, Gran.M5)
    candles = collector.grab(n)
    return candles

candles = get_candles(3)
for candle in candles:
    print(float(str(candle.bid.o))>1)
    print(candle)

def count_opened_trades():
    client = API(access_token=os.getenv('OANDA_API_KEY'))
    req = trades.OpenTrades(accountID=os.getenv('OANDA_ACCOUNT_ID'))
    client.request(req)
    return len(req.response['trades'])

"""
    Create a pandas DataFrame from n candles and compute the ATR, EMA, RSI and BB for each candle.
"""
def get_candles_frame(n):
    candles = get_candles(n)
    dfstream = pd.DataFrame(columns=['Open','Close','High','Low'])
    
    i = 0
    for candle in candles:
        dfstream.loc[i, ['Open']] = float(str(candle.bid.o))
        dfstream.loc[i, ['Close']] = float(str(candle.bid.c))
        dfstream.loc[i, ['High']] = float(str(candle.bid.h))
        dfstream.loc[i, ['Low']] = float(str(candle.bid.l))
        i = i + 1

    dfstream['Open'] = dfstream['Open'].astype(float)
    dfstream['Close'] = dfstream['Close'].astype(float)
    dfstream['High'] = dfstream['High'].astype(float)
    dfstream['Low'] = dfstream['Low'].astype(float)

    dfstream["ATR"] = ta.atr(dfstream.High, dfstream.Low, dfstream.Close, length=7)
    dfstream["EMA_fast"] = ta.ema(dfstream.Close, length=30)
    dfstream["EMA_slow"] = ta.ema(dfstream.Close, length=50)
    dfstream['RSI'] = ta.rsi(dfstream.Close, length=10)
    my_bbands = ta.bbands(dfstream.Close, length=15, std=1.5)
    dfstream = dfstream.join(my_bbands)

    return dfstream


def trading_bot():

    dfstream = get_candles_frame(70)

    signal = total_signal(dfstream, len(dfstream)-1, 7)
        
    slatr = 1.1*dfstream.ATR.iloc[-1] # Stop loss from ATR
    TPSLRatio = 1.5 # Take profit/ Stop loss ratio
    max_spread = 16e-5 # Maximum spread. Bot doesn't trade when spread is too large/
    
    candle = get_candles(1)[-1]
    candle_open_bid = float(str(candle.bid.o))
    candle_open_ask = float(str(candle.ask.o))
    spread = candle_open_ask-candle_open_bid # Spread = The difference between current ask price and current bid price

    # Define stop loss and take profit
    SLBuy = candle_open_bid-slatr-spread
    SLSell = candle_open_ask+slatr+spread

    TPBuy = candle_open_ask+slatr*TPSLRatio+spread
    TPSell = candle_open_bid-slatr*TPSLRatio-spread
    
    client = API(access_token=os.getenv('OANDA_API_KEY'))
    #Sell (Take a short position)
    if signal == 1 and count_opened_trades() == 0 and spread<max_spread:
        mo = MarketOrderRequest(instrument="EUR_USD", units=-3000, takeProfitOnFill=TakeProfitDetails(price=TPSell).data, stopLossOnFill=StopLossDetails(price=SLSell).data)
        r = orders.OrderCreate(os.getenv('OANDA_ACCOUNT_ID'), data=mo.data)
        rv = client.request(r)
        print(rv)
    #Buy (Take a long position)
    elif signal == 2 and count_opened_trades() == 0 and spread<max_spread:
        mo = MarketOrderRequest(instrument="EUR_USD", units=3000, takeProfitOnFill=TakeProfitDetails(price=TPBuy).data, stopLossOnFill=StopLossDetails(price=SLBuy).data)
        r = orders.OrderCreate(os.getenv('OANDA_ACCOUNT_ID'), data=mo.data)
        rv = client.request(r)
        print(rv)

# Schedule trading bot to run every 5 minutes.
scheduler = BlockingScheduler()
scheduler.add_job(trading_bot, 'cron', day_of_week='mon-fri', hour='00-23', minute='1, 6, 11, 16, 21, 26, 31, 36, 41, 46, 51, 56',
                  start_date='2024-05-04 13:00:00', timezone='America/Chicago')
scheduler.start()