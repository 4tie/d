"""
Winning Scalping Strategy - Optimized for Profitability
Advanced scalping strategy with trend following and momentum confirmation.

⚠️ RISK WARNING: Scalping strategy with optimized parameters for profitability.
"""

import talib.abstract as ta
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from pandas import DataFrame
import numpy as np


class WinningScalpingStrategy(IStrategy):
    """
    Optimized scalping strategy with higher win rate focus.
    Uses trend following with tight risk management.
    """
    
    # Strategy interface version
    INTERFACE_VERSION = 3
    
    # Optimal timeframe for scalping
    timeframe = '1m'
    
    # Can this strategy go short?
    can_short = False
    
    # Conservative ROI for consistent profits
    minimal_roi = {
        "0": 0.008,     # 0.8% immediate exit
        "2": 0.006,     # 0.6% after 2 minutes
        "5": 0.004,     # 0.4% after 5 minutes
        "10": 0.002,    # 0.2% after 10 minutes
        "20": 0.0       # Break even after 20 minutes
    }
    
    # Tight stoploss
    stoploss = -0.006  # -0.6% max loss
    
    # Trailing stoploss
    trailing_stop = True
    trailing_stop_positive = 0.002      # Start trailing at 0.2% profit
    trailing_stop_positive_offset = 0.003   # Trail 0.3% behind peak
    trailing_only_offset_is_reached = True
    
    # Startup candle count
    startup_candle_count: int = 50
    
    # Strategy parameters
    buy_rsi_threshold = IntParameter(30, 50, default=45, space="buy")
    sell_rsi_threshold = IntParameter(50, 70, default=60, space="sell")
    volume_multiplier = DecimalParameter(1.0, 2.0, default=1.3, space="buy")
    
    # Protection settings
    use_exit_signal = True
    exit_profit_only = False
    exit_profit_offset = 0.001
    ignore_roi_if_entry_signal = False
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Calculate indicators optimized for winning trades
        """
        
        # RSI with multiple timeframes
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_fast'] = ta.RSI(dataframe, timeperiod=7)
        
        # Bollinger Bands
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_middle'] = bollinger['middleband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_percent'] = (dataframe['close'] - dataframe['bb_lower']) / (dataframe['bb_upper'] - dataframe['bb_lower'])
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        # EMA trend system
        dataframe['ema5'] = ta.EMA(dataframe, timeperiod=5)
        dataframe['ema13'] = ta.EMA(dataframe, timeperiod=13)
        dataframe['ema21'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        
        # MACD
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_histogram'] = macd['macdhist']
        
        # Volume analysis
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        # ADX for trend strength
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        dataframe['plus_di'] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe['minus_di'] = ta.MINUS_DI(dataframe, timeperiod=14)
        
        # Stochastic
        stoch = ta.STOCH(dataframe, fastk_period=14, slowk_period=3, slowd_period=3)
        dataframe['stoch_k'] = stoch['slowk']
        dataframe['stoch_d'] = stoch['slowd']
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Price action
        dataframe['price_change'] = dataframe['close'].pct_change()
        dataframe['high_low_pct'] = (dataframe['high'] - dataframe['low']) / dataframe['close']
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry conditions focused on trend following with confirmation
        """
        
        # Trend conditions
        uptrend = (
            (dataframe['ema5'] > dataframe['ema13']) &
            (dataframe['ema13'] > dataframe['ema21']) &
            (dataframe['close'] > dataframe['ema21'])
        )
        
        # Momentum conditions
        momentum_up = (
            (dataframe['rsi'] > 30) & (dataframe['rsi'] < self.buy_rsi_threshold.value) &
            (dataframe['rsi_fast'] > 25) &
            (dataframe['macd'] > dataframe['macd_signal']) &
            (dataframe['stoch_k'] > 20) & (dataframe['stoch_k'] < 80)
        )
        
        # Volume and volatility
        volume_ok = (
            (dataframe['volume_ratio'] > self.volume_multiplier.value) &
            (dataframe['volume'] > 0)
        )
        
        # Bollinger band position
        bb_position = (
            (dataframe['bb_percent'] > 0.1) & (dataframe['bb_percent'] < 0.4) &
            (dataframe['bb_width'] > 0.02)  # Sufficient volatility
        )
        
        # ADX trend strength
        trend_strength = (dataframe['adx'] > 20) & (dataframe['plus_di'] > dataframe['minus_di'])
        
        dataframe['enter_long'] = (
            uptrend &
            momentum_up &
            volume_ok &
            bb_position &
            trend_strength
        )
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit conditions for profit protection
        """
        
        dataframe['exit_long'] = (
            # RSI overbought
            (dataframe['rsi'] > self.sell_rsi_threshold.value) |
            
            # MACD turning down
            ((dataframe['macd'] < dataframe['macd_signal']) & 
             (dataframe['macd_histogram'] < dataframe['macd_histogram'].shift(1))) |
            
            # Stochastic overbought
            ((dataframe['stoch_k'] > 80) & (dataframe['stoch_d'] > 80)) |
            
            # EMA trend breaking
            (dataframe['close'] < dataframe['ema5']) |
            
            # Bollinger band upper
            (dataframe['bb_percent'] > 0.9) |
            
            # Volume drying up
            (dataframe['volume_ratio'] < 0.8) |
            
            # ADX declining with negative momentum
            ((dataframe['adx'] < 20) & (dataframe['minus_di'] > dataframe['plus_di']))
        )
        
        return dataframe
    
    def custom_exit(self, pair: str, trade, current_time, current_rate,
                    current_profit, **kwargs):
        """
        Custom exit logic for optimal profit taking
        """
        
        # Quick profit on good moves
        if current_profit > 0.004:  # 0.4% profit
            return "quick_profit"
        
        # Time-based exits
        minutes_open = (current_time - trade.open_date_utc).seconds / 60
        
        # Take small profit if holding too long
        if minutes_open > 15 and current_profit > 0.001:
            return "time_profit"
        
        # Cut losses quickly
        if minutes_open > 3 and current_profit < -0.003:
            return "cut_loss"
        
        return None
    
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                           rate: float, time_in_force: str, current_time,
                           entry_tag, side: str, **kwargs) -> bool:
        """
        Trade entry confirmation
        """
        
        # Avoid low activity periods
        hour = current_time.hour
        if hour < 6 or hour > 22:
            return False
        
        return True
