# Ultra-Fast Scalping Strategy - 1 minute timeframe
from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib

class test_scalping_1m(IStrategy):
    """
    Ultra-fast scalping strategy for 1m timeframe
    Focus: Quick profits with tight stops
    """
    
    INTERFACE_VERSION = 3
    timeframe = '1m'
    can_short: bool = False
    
    # Aggressive ROI for scalping
    minimal_roi = {
        "0": 0.02,   # 2% immediate target
        "3": 0.015,  # 1.5% after 3 minutes
        "5": 0.01,   # 1% after 5 minutes
        "10": 0.005  # 0.5% after 10 minutes
    }
    
    # Tight stop loss for scalping
    stoploss = -0.02  # 2% stop loss
    
    # Trailing stop for profit protection
    trailing_stop = True
    trailing_stop_positive = 0.005
    trailing_stop_positive_offset = 0.01
    
    startup_candle_count: int = 30
    use_exit_signal = True
    exit_profit_only = True
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Fast moving averages for scalping
        dataframe['ema5'] = ta.EMA(dataframe, timeperiod=5)
        dataframe['ema10'] = ta.EMA(dataframe, timeperiod=10)
        dataframe['ema21'] = ta.EMA(dataframe, timeperiod=21)
        
        # RSI for momentum
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # MACD for trend confirmation
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        
        # Volume analysis
        dataframe['volume_sma'] = dataframe['volume'].rolling(window=10).mean()
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                # Fast EMA above slower EMA (uptrend)
                (dataframe['ema5'] > dataframe['ema10']) &
                (dataframe['ema10'] > dataframe['ema21']) &
                
                # RSI shows momentum but not overbought
                (dataframe['rsi'] > 55) &
                (dataframe['rsi'] < 75) &
                
                # MACD bullish
                (dataframe['macd'] > dataframe['macdsignal']) &
                
                # High volume (interest)
                (dataframe['volume'] > dataframe['volume_sma'] * 1.5) &
                
                # Reasonable volatility
                (dataframe['atr'] > dataframe['atr'].rolling(10).mean() * 0.8)
            ),
            'enter_long'] = 1
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                # Trend reversal signals
                (dataframe['ema5'] < dataframe['ema10']) |
                
                # Overbought conditions
                (dataframe['rsi'] > 80) |
                
                # MACD bearish divergence
                (dataframe['macd'] < dataframe['macdsignal'])
            ),
            'exit_long'] = 1
        return dataframe
