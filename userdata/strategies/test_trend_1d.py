# Long-Term Trend Following Strategy - 1 day timeframe
from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib

class test_trend_1d(IStrategy):
    """
    Long-term trend following strategy for 1d timeframe
    Focus: Major trends with extended holds (weeks/months)
    """
    
    INTERFACE_VERSION = 3
    timeframe = '1d'
    can_short: bool = False
    
    # Long-term ROI targets
    minimal_roi = {
        "0": 0.50,      # 50% ultimate target
        "1440": 0.30,   # 30% after 1 day
        "4320": 0.20,   # 20% after 3 days  
        "10080": 0.10   # 10% after 1 week
    }
    
    # Wide stop loss for long-term trends
    stoploss = -0.15  # 15% stop loss
    
    # Trailing stop for trend following
    trailing_stop = True
    trailing_stop_positive = 0.05
    trailing_stop_positive_offset = 0.10
    
    startup_candle_count: int = 200
    use_exit_signal = True
    exit_profit_only = False
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long-term moving averages
        dataframe['sma50'] = ta.SMA(dataframe, timeperiod=50)
        dataframe['sma100'] = ta.SMA(dataframe, timeperiod=100)
        dataframe['sma200'] = ta.SMA(dataframe, timeperiod=200)
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        
        # RSI for momentum
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # MACD for trend confirmation
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # ADX for trend strength
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        
        # Parabolic SAR for trend direction
        dataframe['sar'] = ta.SAR(dataframe)
        
        # Williams %R for momentum
        dataframe['willr'] = ta.WILLR(dataframe)
        
        # CCI for trend identification
        dataframe['cci'] = ta.CCI(dataframe)
        
        # Volume trend
        dataframe['volume_sma'] = dataframe['volume'].rolling(window=20).mean()
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                # Major trend confirmation (Golden Cross pattern)
                (dataframe['sma50'] > dataframe['sma100']) &
                (dataframe['sma100'] > dataframe['sma200']) &
                (dataframe['close'] > dataframe['sma50']) &
                
                # Price above EMA
                (dataframe['close'] > dataframe['ema50']) &
                
                # MACD strongly bullish
                (dataframe['macd'] > dataframe['macdsignal']) &
                (dataframe['macdhist'] > 0) &
                
                # Strong trend (ADX)
                (dataframe['adx'] > 30) &
                
                # Parabolic SAR bullish
                (dataframe['close'] > dataframe['sar']) &
                
                # RSI shows strength but not extreme
                (dataframe['rsi'] > 55) &
                (dataframe['rsi'] < 80) &
                
                # CCI trend confirmation
                (dataframe['cci'] > 0) &
                
                # Volume confirmation
                (dataframe['volume'] > dataframe['volume_sma'])
            ),
            'enter_long'] = 1
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                # Trend reversal signals (Death Cross pattern)
                (dataframe['sma50'] < dataframe['sma100']) |
                (dataframe['close'] < dataframe['sma50']) |
                
                # MACD bearish
                (dataframe['macd'] < dataframe['macdsignal']) |
                
                # Weak trend
                (dataframe['adx'] < 25) |
                
                # Parabolic SAR bearish
                (dataframe['close'] < dataframe['sar']) |
                
                # Overbought RSI
                (dataframe['rsi'] > 85) |
                
                # CCI overbought
                (dataframe['cci'] > 200)
            ),
            'exit_long'] = 1
        return dataframe
