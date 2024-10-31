import pandas as pd
import pandas_ta as ta
import numpy as np
from tqdm import tqdm
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from backtesting import Backtest
from backtesting import Strategy

df = pd.read_csv("EURUSD_Candlestick_5_M_ASK_30.09.2019-30.09.2022.csv", index_col="Gmt time", parse_dates=True, dayfirst=True)
df = df[df.High!=df.Low] # Filter out candles with no movement (high = low) usually from days when the market was closed


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


def compute_EMA(df):
    # Compute slow and fast EMA
    df["EMA_slow"] = ta.ema(df.Close, length=50)
    df["EMA_fast"] = ta.ema(df.Close, length=30)
    # Compute RSI, BB, ATR(Average true range)
    df['RSI'] = ta.rsi(df.Close, length=10)
    bollinger_band = ta.bbands(df.Close, length=15, std=1.5)
    df['ATR'] = ta.atr(df.High, df.Low, df.Close, length=7)
    df = df.join(bollinger_band)
    
    df=df[-30000:-1]
    tqdm.pandas() # Enable progress bar
    df.reset_index(inplace=True)

    # Apply EMA signal function
    df['EMASignal'] = df.progress_apply(lambda row: ema_signal(df, row.name, 7) if row.name >= 20 else 0, axis=1)
    df['TotalSignal'] = df.progress_apply(lambda row: total_signal(df, row.name, 7), axis=1)


def backtest_EMA_Strategy(df):
    

    def SIGNAL():
        return df.TotalSignal

    class EMAStrategy(Strategy):
        mysize = 3000
        slcoef = 1.1
        TPSLRatio = 1.5
        rsi_length = 16
        
        def init(self):
            super().init()
            self.signal1 = self.I(SIGNAL)
            #df['RSI']=ta.rsi(df.Close, length=self.rsi_length)

        def next(self):
            super().next()
            slatr = self.slcoef*self.data.ATR[-1]
            TPSLRatio = self.TPSLRatio

            # if len(self.trades)>0:
            #     if self.trades[-1].is_long and self.data.RSI[-1]>=90:
            #         self.trades[-1].close()
            #     elif self.trades[-1].is_short and self.data.RSI[-1]<=10:
            #         self.trades[-1].close()
            
            if self.signal1==2 and len(self.trades)==0:
                sl1 = self.data.Close[-1] - slatr
                tp1 = self.data.Close[-1] + slatr*TPSLRatio
                self.buy(sl=sl1, tp=tp1, size=self.mysize)
            
            elif self.signal1==1 and len(self.trades)==0:         
                sl1 = self.data.Close[-1] + slatr
                tp1 = self.data.Close[-1] - slatr*TPSLRatio
                self.sell(sl=sl1, tp=tp1, size=self.mysize)

    bt = Backtest(df, EMAStrategy, cash=250, margin=1/30)
    print(bt.run())

backtest_EMA_Strategy(df)



# def pointpos(x):
#     if x['TotalSignal']==2:
#         return x['Low']-1e-3
#     elif x['TotalSignal']==1:
#         return x['High']+1e-3
#     else:
#         return np.nan

# df['pointpos'] = df.apply(lambda row: pointpos(row), axis=1)


# st=100
# dfpl = df[st:st+350]
# #dfpl.reset_index(inplace=True)
# fig = go.Figure(data=[go.Candlestick(x=dfpl.index,
#                 open=dfpl['Open'],
#                 high=dfpl['High'],
#                 low=dfpl['Low'],
#                 close=dfpl['Close']),

#                 go.Scatter(x=dfpl.index, y=dfpl['BBL_15_1.5'], 
#                            line=dict(color='green', width=1), 
#                            name="BBL"),
#                 go.Scatter(x=dfpl.index, y=dfpl['BBU_15_1.5'], 
#                            line=dict(color='green', width=1), 
#                            name="BBU"),
#                 go.Scatter(x=dfpl.index, y=dfpl['EMA_fast'], 
#                            line=dict(color='black', width=1), 
#                            name="EMA_fast"),
#                 go.Scatter(x=dfpl.index, y=dfpl['EMA_slow'], 
#                            line=dict(color='blue', width=1), 
#                            name="EMA_slow")])

# fig.add_scatter(x=dfpl.index, y=dfpl['pointpos'], mode="markers",
#                 marker=dict(size=5, color="MediumPurple"),
#                 name="entry")

# fig.show()