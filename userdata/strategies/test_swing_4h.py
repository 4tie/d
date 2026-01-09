# Swing Trading Strategy - 4 hour timeframe
from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib

class test_swing_4h(IStrategy):
    """
    Swing trading strategy for 4h timeframe
    Focus: Multi-day trends with medium-term holds
    """
    
    INTERFACE_VERSION = 3
    timeframe = '4h'
    can_short: bool = False
    
    # Swing trading ROI - longer holds
    minimal_roi = {
        "0": 0.20,      # 20% target
        "240": 0.15,    # 15% after 40 hours (10 candles)
        "480": 0.10,    # 10% after 80 hours (20 candles)
        "960": 0.05     # 5% after 160 hours (40 candles)
    }
    
    # Wider stop loss for swing trading
    stoploss = -0.08  # 8% stop loss
    
    # Trailing stop for long-term gains
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.04
    
    startup_candle_count: int = 50
    use_exit_signal = True
    exit_profit_only = False
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Moving averages for trend identification
        dataframe['sma20'] = ta.SMA(dataframe, timeperiod=20)
        dataframe['sma50'] = ta.SMA(dataframe, timeperiod=50)
        dataframe['ema21'] = ta.EMA(dataframe, timeperiod=21)
        
        # RSI for momentum
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # MACD for trend confirmation
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # Bollinger Bands for volatility
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_middleband'] = bollinger['mid']
        
        # ADX for trend strength
        dataframe['adx'] = ta.ADX(dataframe)
        
        # Stochastic for overbought/oversold
        stoch = ta.STOCH(dataframe)
        dataframe['stoch_k'] = stoch['slowk']
        dataframe['stoch_d'] = stoch['slowd']
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                # Strong uptrend confirmation
                (dataframe['close'] > dataframe['sma20']) &
                (dataframe['sma20'] > dataframe['sma50']) &
                (dataframe['close'] > dataframe['ema21']) &
                
                # MACD bullish
                (dataframe['macd'] > dataframe['macdsignal']) &
                (dataframe['macdhist'] > 0) &
                
                # RSI shows momentum but room to grow
                (dataframe['rsi'] > 50) &
                (dataframe['rsi'] < 70) &
                
                # Strong trend (ADX)
                (dataframe['adx'] > 25) &
                
                # Not overbought (Stochastic)
                (dataframe['stoch_k'] < 80) &
                
                # Above Bollinger middle band
                (dataframe['close'] > dataframe['bb_middleband'])
            ),
            'enter_long'] = 1
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                # Trend weakening
                (dataframe['close'] < dataframe['sma20']) |
                
                # MACD bearish crossover
                (dataframe['macd'] < dataframe['macdsignal']) |
                
                # Overbought conditions
                (dataframe['rsi'] > 75) |
                (dataframe['stoch_k'] > 85) |
                
                # Weak trend
                (dataframe['adx'] < 20)
            ),
            'exit_long'] = 1
        return dataframe
