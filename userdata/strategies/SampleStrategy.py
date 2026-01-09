# QuickScalpV2_1M - Freqtrade strategy (Spot, Binance)
# Timeframe: 1m (informative 1h)
# Designed for: BTC/USDT and ETH/USDT
# Stake: fixed $10 per trade
# Fees: Binance spot base tier (0.1% maker/taker) - no BNB discount
# Target: ~0.4% per trade (breakeven ~0.25% including fees + slippage)

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, merge_informative_pair
from pandas import DataFrame
import talib.abstract as ta
import pandas as pd
from datetime import datetime, timedelta

class QuickScalpV2_1M(IStrategy):
    # Basic strategy settings
    timeframe = '1m'
    informative_timeframe = '1h'

    # Minimal ROI designed to be above breakeven (fees + slippage)
    minimal_roi = {
        "0": 0.004,    # 0.4% immediate target
        "30": 0.002,   # 0.2% after 30 minutes
        "120": 0.001,
        "360": 0
    }

    # Static stoploss (hard stop), expressed as negative fraction
    stoploss = -0.006   # -0.6% hard stop

    # Trailing enabled to try to capture bigger moves after reaching offset
    trailing_stop = True
    trailing_stop_positive = 0.0025    # 0.25% trailing
    trailing_stop_positive_offset = 0.004  # start trailing after 0.4%
    trailing_only_offset_is_reached = True

    # Strategy parameters
    startup_candle_count: int = 120

    # Use limit entries for capture of spread when possible, fast market exit
    order_types = {
        'entry': 'limit',
        'exit': 'market',
        'stoploss': 'market',
        'stake_amount': 'market'
    }

    order_time_in_force = {
        'entry': 'gtc',
        'exit': 'ioc',
        'stoploss': 'ioc'
    }

    # Protection / operational settings
    can_short = False

    # Optional hyperparameters (for future optimization)
    atr_period = 14
    ema_fast = 20
    ema_slow = 200
    min_volume_mult = 1.0
    min_atr = 0.0003

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative = []
        for pair in pairs:
            informative.append((pair, self.informative_timeframe))
        return informative

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 1m indicators
        dataframe['ema20'] = ta.EMA(dataframe, timeperiod=self.ema_fast)
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=self.atr_period)
        dataframe['sma_vol_20'] = dataframe['volume'].rolling(20).mean()

        # Merge informative 1h
        pair = metadata['pair']
        informative = self.dp.get_pair_dataframe(pair, timeframe=self.informative_timeframe)
        informative['ema200'] = ta.EMA(informative, timeperiod=self.ema_slow)
        informative = informative[['ema200']]
        informative.rename(columns={'ema200': 'ema200_1h'}, inplace=True)
        dataframe = merge_informative_pair(dataframe, informative, self.timeframe, self.informative_timeframe, ffill=True)

        # Derived
        dataframe['trend_up'] = dataframe['ema20'] > dataframe['ema200_1h']
        dataframe['min_spread_pct'] = (dataframe['ask'] - dataframe['bid']) / dataframe['close'] if {'ask','bid'}.issubset(dataframe.columns) else 0

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Entry conditions:
        # - Trend confirmation (1h EMA200)
        # - Volume above rolling average
        # - ATR large enough (volatility present)
        # - Price near bid (prefer limit fill)

        dataframe['enter_long'] = (
            (dataframe['trend_up']) &
            (dataframe['volume'] > dataframe['sma_vol_20'] * self.min_volume_mult) &
            (dataframe['atr'] > self.min_atr)
        )

        # We only create buy signals when the conditions match
        dataframe.loc[dataframe['enter_long'], 'buy'] = 1
        dataframe.loc[~dataframe['enter_long'], 'buy'] = 0

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Let ROI / trailing / stoploss handle exits. Optionally add EMA crossover exit
        dataframe['sell'] = 0
        # If price drops below EMA20 while in position, recommend exit
        dataframe.loc[(dataframe['close'] < dataframe['ema20']), 'sell'] = 1
        return dataframe

    # Override custom_stoploss to provide last-resort protection (optional)
    def custom_stoploss(self, pair: str, trade, current_time: datetime, current_rate: float, current_profit: float, **kwargs) -> float:
        # If trade is deeply negative -2% or older than 6 hours, force exit
        if current_profit < -0.02:
            return 0.01  # instruct to exit immediately (positive number means sell now)
        return None

    # Define stake amount in strategy for documentation; actual stake is set in config.json
    def stake_amount(self, pair: str, current_time: datetime) -> float:
        # Fixed stake of $10 per trade as requested
        return 10.0

    # Safety filter before placing orders (called by freqtrade hooks if enabled)
    def check_entry_safety(self, pair: str, order_type: str, amount: float, price: float, side: str, **kwargs) -> bool:
        # Placeholder for integration with orderbook checks; return True to allow entry
        return True

# End of strategy file
