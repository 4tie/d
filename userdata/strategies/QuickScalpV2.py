# pragma pylint: disable=missing-docstring, invalid-name
# --- Do not remove these libs ---
from typing import Dict
import numpy as np  # noqa
import pandas as pd  # noqa
from pandas import DataFrame
from freqtrade.strategy.interface import IStrategy
from freqtrade.strategy import IntParameter, DecimalParameter
# --------------------------------
# Add your lib to import here
import talib.abstract as ta


class QuickScalpV2(IStrategy):
    """
    QuickScalpV2 – Minimal, fast scalping strategy.

    Goals:
    - Trade on short timeframes with lightweight indicators (EMA/RSI only).
    - Exit quickly on small profits via minimal ROI and positive trailing stop.
    - Momentum-based discretionary exits ("feels it should sell"): RSI high, price falling below fast EMA,
      or trend flip (fast EMA below slow EMA).

    Notes:
    - For the best results, let the strategy control trailing/ROI (avoid overriding in config.json).
    - Recommended timeframe: 15m (configure config.json "timeframe": "15m" or pass via CLI).
    """

    INTERFACE_VERSION = 2

    # Timeframe (config.json can override)
    timeframe = '15m'

    # Process only new candles for speed
    process_only_new_candles = True

    # Number of candles required before producing valid signals
    startup_candle_count: int = 50

    # Minimal ROI – scalp ladder (fast targets)
    # Config will override if it contains "minimal_roi".
    minimal_roi: Dict[str, float] = {
        "0": 0.15,   # 0.5% instantly (was 0.3%)
        "30": 0.03   # 0.2% floor after 60 min (avoid breakeven exits)
    }

    # Tight fixed stoploss for scalps – keep losers very small (config can override)
    stoploss = -0.03
    # Trailing stop – positive-only trailing; small trail tuned for scalps
    trailing_stop = True   
    trailing_stop_positive = 0.003  # trail 0.3% (slightly higher than before)
    trailing_stop_positive_offset = 0.01  # arm after 0.6% profit (slightly higher)
    trailing_only_offset_is_reached = True

    # Use exit signal in addition to ROI/Trailing
    use_exit_signal = False
    # Only honor exit signals when trade is in profit
    exit_profit_only = True
    ignore_roi_if_entry_signal = False
    # Disable custom stoploss (use fixed -0.5%)
    use_custom_stoploss = False

    # Order settings
    order_types = {
        'entry': 'limit',
        'exit': 'market',
        'stoploss': 'market',
        'stoploss_on_exchange': True,
    }

    order_time_in_force = {
        'entry': 'gtc',
        'exit': 'gtc'
    }

    # Protections (moved from config; config-based protections are deprecated in your version)


    # --- Hyperoptable parameters ---
    # Buy parameters
    buy_rsi = IntParameter(20, 60, default=40, space="buy")
    ema_fast_len = IntParameter(5, 21, default=9, space="buy")
    ema_slow_len = IntParameter(20, 55, default=30, space="buy")
    # Trend/Chop filters
    adx_min = IntParameter(10, 35, default=20, space="buy")
    bb_width_max = DecimalParameter(0.020, 0.080, decimals=3, default=0.060, space="buy")

    # Sell parameters
    sell_rsi = IntParameter(60, 90, default=75, space="sell")
    # ATR-based dynamic stoploss params
    atr_period = IntParameter(10, 24, default=14, space="sell")
    atr_mult = DecimalParameter(2.0, 4.0, decimals=1, default=3.0, space="sell")
    atr_min_sl = DecimalParameter(0.006, 0.012, decimals=3, default=0.008, space="sell")  # 0.6% - 1.2%
    atr_max_sl = DecimalParameter(0.008, 0.018, decimals=3, default=0.012, space="sell")  # cap at ~1.2%

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # EMAs
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=int(self.ema_fast_len.value))
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=int(self.ema_slow_len.value))
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        # ADX for trend-strength filter
        dataframe['adx'] = ta.ADX(dataframe)
        # ATR for dynamic SL sizing (use param period)
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=int(self.atr_period.value))
        # Bollinger Bands for volatility gauging
        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0, matype=0)
        dataframe['bb_upper'] = bb['upperband']
        dataframe['bb_middle'] = bb['middleband']
        dataframe['bb_lower'] = bb['lowerband']
        # Width relative to middle band
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        # Volume MA for basic liquidity filter
        dataframe['vol_ma20'] = dataframe['volume'].rolling(20).mean()
        # Volume EMA(14) for rising volume filter
        dataframe['vol_ema14'] = dataframe['volume'].ewm(span=14, adjust=False).mean()
        return dataframe

    def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Generate buys more readily on 3m:
        # - Uptrend filter using EMAs
        # - Momentum breakout OR mild dip near fast EMA
        uptrend = (dataframe['ema_fast'] > dataframe['ema_slow'])
        # Trend filter to avoid chop / crazy-volatility zones
        trend_ok = (
            (dataframe['adx'] >= self.adx_min.value) &
            (dataframe['bb_width'] <= float(self.bb_width_max.value)) &
            (dataframe['volume'] > dataframe['vol_ema14'])  # rising volume
        )

        # Momentum: RSI above threshold and price above fast EMA
        momo = (
            (dataframe['rsi'] > self.buy_rsi.value) &
            (dataframe['close'] > dataframe['ema_fast'] * 1.0005)  # small buffer above EMA
        )

        dataframe.loc[
            (
                (uptrend & trend_ok & (momo)) &
                (dataframe['volume'] > dataframe['vol_ma20'])
            ),
            'buy'
        ] = 1
        return dataframe

    def populate_sell_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # نسمح بالخروج على:
        # - RSI مرتفع (جني ربح)
        # - هبوط واضح تحت EMA ولكن فقط إذا RSI ليس منخفضًا (نقطة ضعف الزوابع الصغيرة)
        # - أو تقلب/فليب للاتجاه (ema_fast < ema_slow)

        # شرط هبوط تحت EMA: فقط إذا السعر هبط أكثر من هامش (exit_ema_loss_mult) 
        # ولـتجنب الخروج من هبوط طفيف نضيف شرط rsi > 40 أو volume أقل من المتوسط
        ema_loss_cond = (
            (dataframe['close'] < dataframe['ema_fast'] * 0.995) &
            ((dataframe['rsi'] > 40) | (dataframe['volume'] < dataframe['vol_ema14']))
        )

        dataframe.loc[
            (
                (
                    (dataframe['rsi'] > self.sell_rsi.value) |
                    ema_loss_cond |
                    (dataframe['ema_fast'] < dataframe['ema_slow'])
                ) &
                (dataframe['volume'] > 0)
            ),
            'sell'
        ] = 1
        return dataframe


    # Dynamic, ATR-based stoploss. Keeps risk adaptive per pair/period and tightens as profit increases.
    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
            row = dataframe.iloc[-1]
            atr = float(row.get('atr', np.nan))
            close = float(row.get('close', np.nan))
            if np.isnan(atr) or np.isnan(close) or close <= 0:
                return self.stoploss

            atrp = atr / close  # ATR as % of price
            # Base SL sized by ATR, bounded by [atr_min_sl, atr_max_sl]
            base_sl = -min(max(float(self.atr_mult.value) * atrp, float(self.atr_min_sl.value)), float(self.atr_max_sl.value))

            sl = base_sl
            # Tighten a bit as profit grows; trailing_stop handles the rest once armed.
            if current_profit > 0.005:   # > 0.5%
                sl = max(sl, -0.004)
            if current_profit > 0.015:   # > 1.5%
                sl = max(sl, -0.002)
            # Never loosen beyond the initial configured stoploss
            sl = max(sl, self.stoploss)
            return sl
        except Exception:
            # In case dp is not available (unit tests / edge cases)
            return self.stoploss
