from typing import Dict, List
import talib.abstract as ta
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter

class AIStrategy(IStrategy):
    INTERFACE_VERSION = 3
    
    # Minimal ROI designed for the strategy
    minimal_roi = {
        "0": 0.01,
        "10": 0.005,
        "20": 0.002,
        "30": 0
    }

    # Optimal stoploss designed for the strategy
    stoploss = -0.01

    # Optimal timeframe for the strategy
    timeframe = '1m'

    # Parameters
    rsi_buy_threshold = IntParameter(25, 35, default=30, space="buy")
    rsi_sell_threshold = IntParameter(65, 75, default=70, space="sell")
    ema_fast_period = IntParameter(10, 20, default=12, space="buy")
    ema_slow_period = IntParameter(30, 50, default=36, space="buy")
    volume_threshold = DecimalParameter(1.5, 3.0, default=2.0, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # EMAs
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.ema_fast_period.value)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.ema_slow_period.value)
        
        # Volume indicators
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # Bollinger Bands
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_middle'] = bollinger['middleband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        # MACD
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = []
        
        # EMA crossover condition
        conditions.append(
            (dataframe['ema_fast'] > dataframe['ema_slow']) &
            (dataframe['ema_fast'].shift(1) <= dataframe['ema_slow'].shift(1))
        )
        
        # RSI condition
        conditions.append(dataframe['rsi'] < self.rsi_buy_threshold.value)
        
        # Volume condition
        conditions.append(dataframe['volume_ratio'] > self.volume_threshold.value)
        
        # Bollinger Band condition (price near lower band)
        conditions.append(dataframe['close'] <= dataframe['bb_lower'])
        
        # MACD condition
        conditions.append(dataframe['macd'] > dataframe['macdsignal'])
        
        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                'enter_long',
            ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = []
        
        # EMA crossover condition
        conditions.append(
            (dataframe['ema_fast'] < dataframe['ema_slow']) &
            (dataframe['ema_fast'].shift(1) >= dataframe['ema_slow'].shift(1))
        )
        
        # RSI condition
        conditions.append(dataframe['rsi'] > self.rsi_sell_threshold.value)
        
        # Bollinger Band condition (price near upper band)
        conditions.append(dataframe['close'] >= dataframe['bb_upper'])
        
        # MACD condition
        conditions.append(dataframe['macd'] < dataframe['macdsignal'])
        
        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                'exit_long',
            ] = 1

        return dataframe
