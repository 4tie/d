"""
Auto Scalping Strategy - Fully Hyperoptable
Scalping strategy for 1m timeframe with dynamic TP/SL, works in volatile sideways and trending markets.
"""

from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from pandas import DataFrame
import talib.abstract as ta
import numpy as np
from freqtrade.persistence import Trade


class AutoScalpingStrategy(IStrategy):
    """
    Advanced scalping strategy with hyperoptable parameters.
    Short holding time (minutes to hours), dynamic take profit and stop loss.
    """

    INTERFACE_VERSION = 3
    timeframe = '1m'
    can_short = False

    # Hyperoptable parameters
    # EMA parameters
    ema_fast_period = IntParameter(5, 20, default=9, space="buy")
    ema_slow_period = IntParameter(15, 50, default=21, space="buy")

    # RSI parameters
    rsi_period = IntParameter(7, 21, default=14, space="buy")
    rsi_entry_threshold = IntParameter(20, 45, default=30, space="buy")
    rsi_exit_threshold = IntParameter(55, 80, default=70, space="sell")

    # Bollinger Bands parameters
    bb_period = IntParameter(10, 30, default=20, space="buy")
    bb_std = DecimalParameter(1.5, 3.0, default=2.0, space="buy")
    bb_position_min = DecimalParameter(0.0, 0.3, default=0.1, space="buy")
    bb_position_max = DecimalParameter(0.7, 1.0, default=0.9, space="sell")

    # Volume parameters
    volume_sma_period = IntParameter(10, 30, default=20, space="buy")
    volume_multiplier = DecimalParameter(1.0, 3.0, default=1.5, space="buy")

    # VWAP parameters
    vwap_enabled = IntParameter(0, 1, default=1, space="buy")

    # Dynamic TP/SL parameters
    tp_multiplier = DecimalParameter(1.0, 5.0, default=2.0, space="sell")
    sl_multiplier = DecimalParameter(0.5, 2.0, default=1.0, space="sell")

    # ROI table parameters
    roi_0 = DecimalParameter(0.002, 0.01, default=0.004, space="sell")
    roi_5 = DecimalParameter(0.001, 0.005, default=0.002, space="sell")
    roi_15 = DecimalParameter(0.0, 0.003, default=0.001, space="sell")
    roi_30 = DecimalParameter(0.0, 0.002, default=0.0, space="sell")

    # Stoploss parameter
    stoploss = -0.005

    # Trailing stop parameters
    trailing_stop = IntParameter(0, 1, default=1, space="sell")
    trailing_stop_positive = DecimalParameter(0.001, 0.01, default=0.003, space="sell")
    trailing_stop_positive_offset = DecimalParameter(0.002, 0.02, default=0.005, space="sell")

    # Startup and protection
    startup_candle_count: int = 50
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Order types
    order_types = {
        'entry': 'limit',
        'exit': 'market',
        'stoploss': 'market',
        'emergency_exit': 'market',
        'force_entry': 'limit',
        'force_exit': 'limit',
        'stoploss_on_exchange': False
    }

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all technical indicators"""

        # EMA
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.ema_fast_period.value)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.ema_slow_period.value)

        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)

        # Bollinger Bands
        bb = ta.BBANDS(dataframe, timeperiod=self.bb_period.value, nbdevup=self.bb_std.value, nbdevdn=self.bb_std.value)
        dataframe['bb_lower'] = bb['lowerband']
        dataframe['bb_middle'] = bb['middleband']
        dataframe['bb_upper'] = bb['upperband']
        dataframe['bb_percent'] = (dataframe['close'] - dataframe['bb_lower']) / (dataframe['bb_upper'] - dataframe['bb_lower'])

        # Volume SMA
        dataframe['volume_sma'] = dataframe['volume'].rolling(self.volume_sma_period.value).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']

        # VWAP
        if self.vwap_enabled.value:
            dataframe['vwap'] = (dataframe['volume'] * (dataframe['high'] + dataframe['low'] + dataframe['close']) / 3).cumsum() / dataframe['volume'].cumsum()

        # ATR for dynamic SL/TP
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)

        # Trend indicators
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        dataframe['plus_di'] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe['minus_di'] = ta.MINUS_DI(dataframe, timeperiod=14)

        # MACD for momentum
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_histogram'] = macd['macdhist']

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry conditions"""

        # Trend filter
        uptrend = (
            (dataframe['ema_fast'] > dataframe['ema_slow']) &
            (dataframe['adx'] > 20) &
            (dataframe['plus_di'] > dataframe['minus_di'])
        )

        # Momentum filter
        momentum_up = (
            (dataframe['rsi'] > self.rsi_entry_threshold.value) &
            (dataframe['rsi'] < 70) &
            (dataframe['macd'] > dataframe['macd_signal'])
        )

        # Volume filter
        volume_ok = dataframe['volume_ratio'] > self.volume_multiplier.value

        # Bollinger Band position
        bb_position = (
            (dataframe['bb_percent'] > self.bb_position_min.value) &
            (dataframe['bb_percent'] < self.bb_position_max.value)
        )

        # VWAP filter (optional)
        vwap_condition = True
        if self.vwap_enabled.value:
            vwap_condition = dataframe['close'] > dataframe['vwap']

        dataframe['enter_long'] = (
            uptrend &
            momentum_up &
            volume_ok &
            bb_position &
            vwap_condition
        )

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit conditions"""

        # RSI overbought
        rsi_overbought = dataframe['rsi'] > self.rsi_exit_threshold.value

        # MACD bearish crossover
        macd_bearish = dataframe['macd'] < dataframe['macd_signal']

        # Bollinger Band upper
        bb_upper = dataframe['bb_percent'] > self.bb_position_max.value

        # EMA bearish crossover
        ema_bearish = dataframe['ema_fast'] < dataframe['ema_slow']

        # Volume drying up
        volume_low = dataframe['volume_ratio'] < 1.0

        dataframe['exit_long'] = (
            rsi_overbought |
            macd_bearish |
            bb_upper |
            ema_bearish |
            volume_low
        )

        return dataframe

    # Static minimal_roi for Freqtrade compatibility
    minimal_roi = {
        0: 0.004,
        5: 0.002,
        15: 0.001,
        30: 0.0
    }

    def custom_stoploss(self, pair: str, trade: Trade, current_time, current_rate: float,
                        current_profit: float, **kwargs) -> float:
        """Dynamic stoploss based on ATR"""
        if current_profit > 0.01:  # 1% profit, tighten stoploss
            return 0.005  # 0.5% stop

        # ATR-based stoploss
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) > 0:
            atr_value = dataframe['atr'].iloc[-1]
            dynamic_sl = -atr_value * self.sl_multiplier.value / current_rate
            return max(dynamic_sl, -0.02)  # Max 2% loss

        return None

    def custom_exit(self, pair: str, trade: Trade, current_time, current_rate: float,
                    current_profit: float, **kwargs):
        """Custom exit logic with dynamic take profit"""

        # Dynamic take profit based on ATR
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) > 0:
            atr_value = dataframe['atr'].iloc[-1]
            dynamic_tp = atr_value * self.tp_multiplier.value / trade.open_rate

            if current_profit > dynamic_tp:
                return "dynamic_tp"

        # Time-based exit for scalping
        minutes_open = (current_time - trade.open_date_utc).seconds / 60
        if minutes_open > 60 and current_profit > 0.001:  # 1 hour max hold
            return "time_exit"

        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                           rate: float, time_in_force: str, current_time,
                           entry_tag, side: str, **kwargs) -> bool:
        """Trade entry confirmation"""

        # Avoid trading during low volatility periods
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) > 0:
            atr_value = dataframe['atr'].iloc[-1]
            if atr_value < dataframe['close'].iloc[-1] * 0.001:  # Less than 0.1% ATR
                return False

        return True
