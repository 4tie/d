# Mean Reversion Strategy - 15 minute timeframe
from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib

class test_mean_reversion_15m(IStrategy):
    """
    Mean reversion strategy for 15m timeframe
    Focus: Buying oversold conditions, selling overbought
    """
    
    INTERFACE_VERSION = 3
    timeframe = '15m'
    can_short: bool = False
    
    # Mean reversion ROI - quick profits
    minimal_roi = {
        "0": 0.08,     # 8% target
        "15": 0.06,    # 6% after 15 minutes
        "30": 0.04,    # 4% after 30 minutes
        "60": 0.02     # 2% after 1 hour
    }
    
    # Moderate stop loss
    stoploss = -0.05  # 5% stop loss
    
    # Conservative trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.03
    
    startup_candle_count: int = 40
    use_exit_signal = True
    exit_profit_only = False
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Bollinger Bands for mean reversion
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_percent'] = (dataframe['close'] - dataframe['bb_lowerband']) / (dataframe['bb_upperband'] - dataframe['bb_lowerband'])
        
        # RSI for oversold/overbought
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Stochastic for momentum
        stoch = ta.STOCH(dataframe)
        dataframe['stoch_k'] = stoch['slowk']
        dataframe['stoch_d'] = stoch['slowd']
        
        # Williams %R
        dataframe['willr'] = ta.WILLR(dataframe)
        
        # MFI (Money Flow Index)
        dataframe['mfi'] = ta.MFI(dataframe)
        
        # CCI for mean reversion signals
        dataframe['cci'] = ta.CCI(dataframe)
        
        # Moving averages for trend context
        dataframe['sma20'] = ta.SMA(dataframe, timeperiod=20)
        dataframe['sma50'] = ta.SMA(dataframe, timeperiod=50)
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe)
        
        # Volume analysis
        dataframe['volume_sma'] = dataframe['volume'].rolling(window=20).mean()
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                # Price near or below lower Bollinger Band (oversold)
                (dataframe['close'] <= dataframe['bb_lowerband'] * 1.02) &
                (dataframe['bb_percent'] < 0.2) &
                
                # Multiple oversold confirmations
                (dataframe['rsi'] < 30) &
                (dataframe['stoch_k'] < 20) &
                (dataframe['mfi'] < 25) &
                (dataframe['willr'] < -80) &
                
                # CCI oversold
                (dataframe['cci'] < -100) &
                
                # Still in overall uptrend (don't catch falling knife)
                (dataframe['sma20'] > dataframe['sma50']) &
                (dataframe['close'] > dataframe['sma50'] * 0.95) &
                
                # Volume confirmation (selling pressure)
                (dataframe['volume'] > dataframe['volume_sma'] * 0.8) &
                
                # Reasonable volatility
                (dataframe['atr'] > dataframe['atr'].rolling(10).mean() * 0.5)
            ),
            'enter_long'] = 1
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                # Price reaches upper Bollinger Band (overbought)
                (dataframe['close'] >= dataframe['bb_upperband'] * 0.98) |
                (dataframe['bb_percent'] > 0.8) |
                
                # Overbought conditions
                (dataframe['rsi'] > 70) |
                (dataframe['stoch_k'] > 80) |
                (dataframe['mfi'] > 75) |
                
                # CCI overbought
                (dataframe['cci'] > 100) |
                
                # Price back to mean
                (dataframe['close'] > dataframe['bb_middleband'])
            ),
            'exit_long'] = 1
        return dataframe
