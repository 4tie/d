from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import numpy as np
from datetime import datetime  # Added missing import

class scalp(IStrategy):
    """
    SCALP V8 - Optimized for Profitability and Risk Control
    Focus: Reduced frequency, stronger trend confirmation, aggressive profit taking.
    """
    
    INTERFACE_VERSION = 3
    timeframe = '15m'
    can_short = False
    
    # Optimized ROI: Higher initial target to cover fees, faster decay to lock in gains
    minimal_roi = {
        "0": 0.008,     # 0.8% target (covers fees + small profit)
        "5": 0.006,     # 0.6% after 5 mins
        "15": 0.003,    # 0.3% after 15 mins
        "30": 0         # Exit after 30 mins
    }
    
    # Wider stoploss to avoid noise, but tighter trailing to protect profits
    stoploss = -0.020
    
    # Aggressive trailing stop to lock in profits immediately
    trailing_stop = True
    trailing_stop_positive = 0.004
    trailing_stop_positive_offset = 0.006
    trailing_only_offset_is_reached = True
    
    process_only_new_candles = False
    use_exit_signal = True
    exit_profit_only = True  # Only use exit signals if in profit
    ignore_roi_if_entry_signal = False
    startup_candle_count = 34
    
    # Reduced max trade duration to prevent time drag
    max_trade_duration_minutes = 60
    use_custom_stoploss = True
    position_adjustment_enable = False
    
    # Keep max trades low to reduce fee impact
    max_open_trades = 1
    
    protections = [
        {
            "method": "CooldownPeriod",
            "stop_duration": 10
        },
        {
            "method": "MaxDrawdown",
            "lookback_period": 240,
            "stop_duration": 60,
            "trade_limit": 5,
            "max_allowed_drawdown": 0.05
        }
    ]
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Core indicators with trend strength filtering"""
        
        # Trend identification
        dataframe['ema_9'] = ta.EMA(dataframe['close'], timeperiod=9)
        dataframe['ema_21'] = ta.EMA(dataframe['close'], timeperiod=21)
        dataframe['ema_50'] = ta.EMA(dataframe['close'], timeperiod=50)
        
        # Momentum & Strength
        dataframe['rsi'] = ta.RSI(dataframe['close'], timeperiod=14)
        
        # MACD for confirmation
        macd = ta.MACD(dataframe['close'])
        dataframe['macd'] = macd[0]
        dataframe['macdsignal'] = macd[1]
        dataframe['macdhist'] = macd[2]
        
        # Volatility (ATR) for dynamic stoploss calculation
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Volume Filter (Relative Volume)
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        # Trend Strength (ADX) - Added to filter weak trends
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Strict Entry Logic: Requires Trend + Momentum + Volume
        Reduced from 5 conditions to 3 high-conviction signals.
        """
        dataframe.loc[
            (
                # 1. Strong Trend: EMA9 > EMA21 > EMA50 (Stacked EMAs)
                (dataframe['ema_9'] > dataframe['ema_21']) &
                (dataframe['ema_21'] > dataframe['ema_50']) &
                
                # 2. Momentum: RSI above 50 (Bullish) but not overbought (< 75)
                (dataframe['rsi'] > 50) &
                (dataframe['rsi'] < 75) &
                
                # 3. Trend Strength: ADX > 20 (Avoids choppy markets)
                (dataframe['adx'] > 20) &
                
                # 4. Volume: Above average volume (Confirms the move)
                (dataframe['volume_ratio'] > 1.0)
            ),
            'enter_long'] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Aggressive Exit Logic: Capture gains early, cut losses fast.
        """
        dataframe.loc[
            (
                # 1. Trend Reversal: EMA9 crosses below EMA21
                (dataframe['ema_9'] < dataframe['ema_21']) |
                
                # 2. Momentum Loss: RSI drops below 45 (Early warning)
                (dataframe['rsi'] < 45) |
                
                # 3. MACD Bearish: Signal line cross under
                (dataframe['macd'] < dataframe['macdsignal'])
            ),
            'exit_long'] = 1
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: datetime, current_profit: float, **kwargs) -> float:
        """
        Dynamic Stoploss based on Time and Profit.
        - If profit > 0.5%: Tighten stop to 0.2% to lock in gains.
        - If trade > 15 mins: Tighten stop to prevent time drag.
        """
        trade_duration = (current_time - trade.open_date).total_seconds() / 60
        
        # Scenario 1: Trade is profitable (> 0.5%) -> Lock in profit immediately
        if current_profit > 0.005:
            return 0.002  # Trailing at +0.2%
            
        # Scenario 2: Trade has been open for > 15 mins but not profitable -> Tighten to prevent bleed
        if trade_duration > 15 and current_profit < 0.002:
            return -0.010  # Tighten stop to -1.0%
            
        # Default: Allow normal breathing room
        return -0.020