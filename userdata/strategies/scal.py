from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class scal(IStrategy):
    """
    SCAL - Optimized scalping strategy with tighter risk management
    """
    
    # Strategy interface version - allow new iterations of the strategy interface.
    INTERFACE_VERSION = 3

    # Optimal timeframe for the strategy. 
    timeframe = '5m'

    # Can this strategy go short?
    can_short: bool = False

    # Minimal ROI designed for the strategy - STEEPER for scalping
    # Adjusted to secure profits IMMEDIATELY (within 5 mins) to combat time drag
    # Base ROI lowered slightly to 2.0% to allow for volatility, but steps are faster
    minimal_roi = {
        "1": 0.01,   # 1% after 1 minute (faster capture)
        "0": 0.015   # 1.5% immediate entry
    }

    # Stoploss - Kept at -4% to prevent immediate large losses
    stoploss = -0.04

    # Trailing stoploss - Adjusted to be less sensitive to 5m noise
    # Offset increased to 1.5% to allow price to run before trailing
    trailing_stop = True
    trailing_stop_positive = 0.01  # 1% profit protection
    trailing_stop_positive_offset = 0.015  # 1.5% offset before trailing activates
    trailing_only_offset_is_reached = True

    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = False

    # These values can be overridden in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30

    # --- RISK MANAGEMENT ADDITIONS ---
    # Force close trades after 30 minutes to prevent profit erosion (Time Drag fix)
    max_trade_duration_minutes = 30
    
    # Disable custom stoploss
    use_custom_stoploss = False
    
    # Reduce position size to improve risk-adjusted returns
    position_adjustment_enable = True
    stake_amount = None
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame
        """
        
        # RSI with adjusted period
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=10)

        # MACD with faster settings
        macd = ta.MACD(dataframe, fastperiod=8, slowperiod=17, signalperiod=5)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']

        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']

        # EMA - Exponential Moving Average
        dataframe['ema12'] = ta.EMA(dataframe, timeperiod=12)
        dataframe['ema26'] = ta.EMA(dataframe, timeperiod=26)

        # Volume filter
        dataframe['volume_mean'] = dataframe['volume'].rolling(10).mean()

        # ATR for Stoploss (Retained for indicators, though not used in custom stoploss anymore)
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # ADX for trend strength confirmation
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """
        dataframe.loc[
            (
                # Signal: RSI crosses above 60 (Stronger momentum filter)
                (dataframe['rsi'] > 60) &
                # Signal: MACD above Signal with positive histogram (Stronger Momentum)
                (dataframe['macd'] > dataframe['macdsignal']) &
                (dataframe['macdhist'] > 0) &
                # Price above EMA12 for immediate uptrend
                (dataframe['close'] > dataframe['ema12']) &
                # Stronger Trend: EMA12 must be above EMA26 (Added to filter noise)
                (dataframe['ema12'] > dataframe['ema26']) &
                # NEW: Price must be above EMA26 (Medium term trend filter)
                (dataframe['close'] > dataframe['ema26']) &
                # Volume confirmation - at least 2.5x average (Stricter filter)
                (dataframe['volume'] > dataframe['volume_mean'] * 2.5) &
                # Price above middle Bollinger Band
                (dataframe['close'] > dataframe['bb_middleband']) &
                # ADX > 25 to confirm trend strength
                (dataframe['adx'] > 25)
            ),
            'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        """
        # Rely on ROI and Trailing Stop for exits primarily.
        # The RSI exit is removed to prevent premature exits on minor pullbacks,
        # allowing the trailing stop and steep ROI to manage the trade.
        # However, we keep a very tight RSI exit to catch immediate reversals.
        dataframe.loc[
            (
                # Exit if RSI drops below 45 (Oversold/Reversal - tightened from 30)
                (dataframe['rsi'] < 45) |
                # Exit if price closes below EMA12 (trend breakdown)
                (dataframe['close'] < dataframe['ema12'])
            ),
            'exit_long'] = 1

        return dataframe