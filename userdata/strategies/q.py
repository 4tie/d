# pragma pylint: disable=missing-docstring, invalid-name
# --- Do not remove these libs ---
from typing import Dict
import numpy as np  # noqa
import pandas as pd  # noqa
from pandas import DataFrame
from freqtrade.strategy.interface import IStrategy
from freqtrade.strategy.informative_decorator import informative
from freqtrade.strategy import IntParameter, DecimalParameter
# --------------------------------
# Add your lib to import here
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class q(IStrategy):
    """
    q – Minimal, fast scalping strategy.

    Goals:
    - Trade on short timeframes with lightweight indicators (EMA/RSI only).
    - Exit quickly on small profits via minimal ROI and positive trailing stop.
    - Momentum-based discretionary exits ("feels it should sell"): RSI high, price falling below fast EMA,
      or trend flip (fast EMA below slow EMA).

    Notes:
    - For the best results, let the strategy control trailing/ROI (avoid overriding in config.json).
    - Recommended timeframe: 15m (configure config.json "timeframe": "15m" or pass via CLI).
    """

    INTERFACE_VERSION = 3

    # Timeframe (config.json can override)
    timeframe = '15m'

    # Process only new candles for speed
    process_only_new_candles = True

    # Number of candles required before producing valid signals
    startup_candle_count: int = 210

    # Minimal ROI – scalp ladder (faster profit taking)
    # Config will override if it contains "minimal_roi".
    minimal_roi: Dict[str, float] = {
        "0": 0.0035,
        "20": 0.0030,
        "60": 0.0025,
        "120": 0.0020
    }

    # Tight fixed stoploss for scalps – keep losers very small (config can override)
    stoploss = -0.006

    # Trailing stop disabled – rely on ROI and custom ATR stoploss instead
    trailing_stop = False
    trailing_stop_positive = 0.004
    trailing_stop_positive_offset = 0.012
    trailing_only_offset_is_reached = True

    # Use exit signal in addition to ROI/Trailing
    use_exit_signal = True
    # Only honor exit signals when trade is in profit
    exit_profit_only = True
    ignore_roi_if_entry_signal = False
    # Disable custom stoploss (use fixed -0.5%)
    use_custom_stoploss = True


    # Order settings
    order_types = {
        'entry': 'limit',
        'exit': 'limit',
        'stoploss': 'market',
        'stoploss_on_exchange': True,
    }

    order_time_in_force = {
        'entry': 'gtc',
        'exit': 'gtc'
    }

    # Protections (moved from config; config-based protections are deprecated in your version)
    protections = [
        {
            "method": "CooldownPeriod",
            "stop_duration_candles": 4
        },
        {
            "method": "StoplossGuard",
            "lookback_period_candles": 96,
            "trade_limit": 1,
            "stop_duration_candles": 16,
            "only_per_pair": True,
            "only_per_side": "long"
        },
        {
            "method": "MaxDrawdown",
            "lookback_period_candles": 96,
            "trade_limit": 20,
            "stop_duration_candles": 96,
            "max_allowed_drawdown": 0.2
        }
    ]

    # --- Hyperoptable parameters ---
    # Buy parameters
    buy_rsi = IntParameter(20, 60, default=55, space="buy")
    ema_fast_len = IntParameter(5, 21, default=9, space="buy")
    ema_slow_len = IntParameter(20, 55, default=30, space="buy")
    # Trend/Chop filters
    adx_min = IntParameter(10, 35, default=18, space="buy")
    bb_width_max = DecimalParameter(0.020, 0.080, decimals=3, default=0.055, space="buy")
    bb_width_min = DecimalParameter(0.006, 0.025, decimals=3, default=0.010, space="buy")

    # Additional hyperoptable buy gates
    freqai_buy_k = DecimalParameter(0.30, 0.60, decimals=2, default=0.45, space="buy")
    freqai_buy_floor = DecimalParameter(0.0020, 0.0040, decimals=4, default=0.0030, space="buy")
    ema_buf_mult = DecimalParameter(1.0003, 1.0012, decimals=6, default=1.0008, space="buy")
    dip_buf_mult = DecimalParameter(0.9980, 1.0000, decimals=4, default=0.9990, space="buy")

    # Sell parameters
    sell_rsi = IntParameter(60, 90, default=70, space="sell")
    exit_ema_loss_mult = DecimalParameter(0.990, 0.999, decimals=3, default=0.997, space="sell")
    # Additional hyperoptable sell gates
    freqai_sell_k = DecimalParameter(0.25, 0.45, decimals=2, default=0.30, space="sell")
    freqai_sell_floor = DecimalParameter(-0.0030, -0.0010, decimals=4, default=-0.0025, space="sell")
    # ATR-based dynamic stoploss params
    atr_period = IntParameter(10, 24, default=14, space="sell")
    atr_mult = DecimalParameter(2.0, 4.0, decimals=1, default=3.0, space="sell")
    atr_min_sl = DecimalParameter(0.004, 0.012, decimals=3, default=0.005, space="sell")  # 0.4% - 1.2%
    atr_max_sl = DecimalParameter(0.007, 0.018, decimals=3, default=0.009, space="sell")  # cap at ~0.9%

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if getattr(self, "config", None) and self.config.get("freqai", {}).get("enabled", False):
            dataframe = self.freqai.start(dataframe, metadata, self)
        # EMAs
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=int(self.ema_fast_len.value))
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=int(self.ema_slow_len.value))
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        # ADX for trend-strength filter
        dataframe['adx'] = ta.ADX(dataframe)
        # ATR for dynamic SL sizing (use param period)
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=int(self.atr_period.value))
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']
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
        # Breakout over prior highs
        dataframe['hh20'] = dataframe['high'].rolling(20).max()
        dataframe['prev_hh20'] = dataframe['hh20'].shift(1)
        return dataframe

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int, metadata: dict, **kwargs) -> DataFrame:
        dataframe["%-rsi-period"] = ta.RSI(dataframe, timeperiod=period)
        dataframe["%-adx-period"] = ta.ADX(dataframe, timeperiod=period)
        dataframe["%-sma-period"] = ta.SMA(dataframe, timeperiod=period)
        dataframe["%-ema-period"] = ta.EMA(dataframe, timeperiod=period)
        dataframe["%-roc-period"] = ta.ROC(dataframe, timeperiod=period)
        bb = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=period, stds=2.0)
        dataframe["%-bb_width-period"] = (bb["upper"] - bb["lower"]) / bb["mid"]
        dataframe["%-close-bb_lower-period"] = dataframe["close"] / bb["lower"]
        return dataframe

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        dataframe["%-pct-change"] = dataframe["close"].pct_change()
        dataframe["%-raw_volume"] = dataframe["volume"]
        dataframe["%-raw_price"] = dataframe["close"]
        return dataframe

    def feature_engineering_standard(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        dataframe["%-day_of_week"] = (dataframe["date"].dt.dayofweek + 1) / 7
        dataframe["%-hour_of_day"] = (dataframe["date"].dt.hour + 1) / 25
        return dataframe

    @informative('1h')
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        dataframe['adx'] = ta.ADX(dataframe)
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['hh20'] = dataframe['high'].rolling(20).max()
        return dataframe

    @informative('4h')
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        dataframe['adx'] = ta.ADX(dataframe)
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        h = self.freqai_info["feature_parameters"]["label_period_candles"]
        dataframe["&-s_close"] = (
            dataframe["close"].shift(-h).rolling(h).mean() / dataframe["close"] - 1
        )
        return dataframe

    def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Generate buys more readily on 3m:
        # - Uptrend filter using EMAs
        # - Momentum breakout OR mild dip near fast EMA
        uptrend = (dataframe['ema_fast'] > dataframe['ema_slow'])
        macro_trend = (dataframe['ema_slow'] > dataframe['ema_200'])
        macro_slope = (dataframe['ema_slow'] > dataframe['ema_slow'].shift(1))
        trend_ok = (
            (dataframe['adx'] >= self.adx_min.value) &
            (dataframe['volume'] > dataframe['vol_ema14'])
        )
        bb_ok = (
            (dataframe['bb_width'] >= float(self.bb_width_min.value)) &
            (dataframe['bb_width'] <= float(self.bb_width_max.value))
        )
        atr_ok = (dataframe['atr_pct'] <= 0.015)
        atr_low_ok = (dataframe['atr_pct'] >= 0.0032)

        macro_1h_ok = (
            (dataframe.get('ema_50_1h') is not None) &
            (dataframe['ema_50_1h'] > dataframe['ema_200_1h']) &
            (dataframe['adx_1h'] >= 18) &
            (dataframe['rsi_1h'] >= 52)
        )

        macro_4h_ok = (
            (dataframe.get('ema_50_4h') is not None) &
            (dataframe['ema_50_4h'] > dataframe['ema_200_4h']) &
            (dataframe['adx_4h'] >= 15) &
            (dataframe['rsi_4h'] >= 48)
        )
        macro_4h_trend = (
            (dataframe.get('ema_50_4h') is not None) &
            (dataframe['ema_50_4h'] > dataframe['ema_200_4h'])
        )

        # Momentum: RSI above threshold and price above fast EMA with breakout
        momo = (
            (dataframe['rsi'] > self.buy_rsi.value) &
            (dataframe['rsi'] > dataframe['rsi'].shift(1)) &
            (dataframe['close'] > dataframe['close'].shift(1)) &
            (dataframe['close'] > dataframe['ema_fast'] * float(self.ema_buf_mult.value)) &
            (dataframe['close'] > dataframe['bb_middle']) &
            (dataframe['close'] > dataframe['prev_hh20'] * 1.0005)
        )
        ema_slope_up = (dataframe['ema_fast'] > dataframe['ema_fast'].shift(1))
        pump_filter = (dataframe['close'] <= dataframe['bb_upper'] * 1.010)
        momo_cross = (
            (dataframe['close'].shift(1) <= dataframe['ema_fast'].shift(1)) &
            (dataframe['rsi'] > dataframe['rsi'].shift(1)) &
            (dataframe['close'] > dataframe['ema_fast'] * float(self.ema_buf_mult.value))
        )

        dip = (
            (dataframe['rsi'] >= (self.buy_rsi.value - 8)) &
            (dataframe['close'] <= dataframe['ema_fast'] * float(self.dip_buf_mult.value)) &
            (dataframe['close'] > dataframe['ema_slow'])
        )

        trusted = (dataframe["do_predict"] == 1) if "do_predict" in dataframe.columns else True
        if "&-s_close" in dataframe.columns:
            if "&-s_close_mean" in dataframe.columns and "&-s_close_std" in dataframe.columns:
                buy_thresh = np.maximum(float(self.freqai_buy_floor.value), dataframe["&-s_close_mean"] + float(self.freqai_buy_k.value) * dataframe["&-s_close_std"])
                pred_ok = dataframe["&-s_close"] > buy_thresh
            else:
                pred_ok = dataframe["&-s_close"] > float(self.freqai_buy_floor.value)
        else:
            pred_ok = True

        breakout_extension_ok = True
        macro_regime_ok = (macro_trend & macro_4h_trend & (macro_1h_ok | macro_slope))
        dataframe.loc[
            (
                (uptrend & macro_regime_ok & trend_ok & bb_ok & atr_low_ok & atr_ok & ema_slope_up & pump_filter & breakout_extension_ok & trusted & pred_ok & (momo | momo_cross)) &
                (dataframe['volume'] > dataframe['vol_ma20'] * 1.10)
            ),
            'buy'
        ] = 1
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.populate_buy_trend(dataframe, metadata)
        if 'buy' in dataframe.columns:
            dataframe.loc[(dataframe['buy'] == 1), 'enter_long'] = 1

        downtrend = (dataframe['ema_fast'] < dataframe['ema_slow'])
        trend_ok = (
            (dataframe['adx'] >= self.adx_min.value) &
            (dataframe['bb_width'] <= float(self.bb_width_max.value)) &
            (dataframe['volume'] > dataframe['vol_ema14'])
        )
        ema_slope_down = (dataframe['ema_fast'] < dataframe['ema_fast'].shift(1))
        momo_short = (
            (dataframe['rsi'] < 45) &
            (dataframe['close'] < dataframe['ema_fast'] * 0.999)
        )

        trusted = (dataframe["do_predict"] == 1) if "do_predict" in dataframe.columns else True
        if "&-s_close" in dataframe.columns:
            if "&-s_close_mean" in dataframe.columns and "&-s_close_std" in dataframe.columns:
                short_thresh = np.minimum(-0.006, dataframe["&-s_close_mean"] - 0.8 * dataframe["&-s_close_std"])
                pred_short_ok = dataframe["&-s_close"] < short_thresh
            else:
                pred_short_ok = dataframe["&-s_close"] < -0.006
        else:
            pred_short_ok = False

        dataframe.loc[
            (
                (downtrend & trend_ok & ema_slope_down & trusted & pred_short_ok & (momo_short)) &
                (dataframe['volume'] > dataframe['vol_ma20'])
            ),
            'enter_short'
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.populate_sell_trend(dataframe, metadata)
        if 'sell' in dataframe.columns:
            dataframe.loc[(dataframe['sell'] == 1), 'exit_long'] = 1

        trusted = (dataframe["do_predict"] == 1) if "do_predict" in dataframe.columns else True
        if "&-s_close" in dataframe.columns:
            if "&-s_close_mean" in dataframe.columns and "&-s_close_std" in dataframe.columns:
                buy_thresh = np.maximum(0.001, dataframe["&-s_close_mean"] + 0.3 * dataframe["&-s_close_std"])
                pred_pos = dataframe["&-s_close"] > buy_thresh
            else:
                pred_pos = dataframe["&-s_close"] > 0.002
        else:
            pred_pos = False

        ema_gain_cond_short = (
            (dataframe['close'] > dataframe['ema_fast'] / float(self.exit_ema_loss_mult.value)) &
            ((dataframe['rsi'] < 60) | (dataframe['volume'] < dataframe['vol_ema14']))
        )

        dataframe.loc[
            (
                (
                    (trusted & pred_pos) |
                    (dataframe['rsi'] < (100 - self.sell_rsi.value)) |
                    ema_gain_cond_short |
                    (dataframe['ema_fast'] > dataframe['ema_slow'])
                ) &
                (dataframe['volume'] > 0)
            ),
            'exit_short'
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
            (dataframe['close'] < dataframe['ema_fast'] * float(self.exit_ema_loss_mult.value)) &
            ((dataframe['rsi'] > 40) | (dataframe['volume'] < dataframe['vol_ema14']))
        )

        trusted = (dataframe["do_predict"] == 1) if "do_predict" in dataframe.columns else True
        if "&-s_close" in dataframe.columns:
            if "&-s_close_mean" in dataframe.columns and "&-s_close_std" in dataframe.columns:
                sell_thresh = np.minimum(float(self.freqai_sell_floor.value), dataframe["&-s_close_mean"] - float(self.freqai_sell_k.value) * dataframe["&-s_close_std"])
                pred_neg = dataframe["&-s_close"] < sell_thresh
            else:
                pred_neg = dataframe["&-s_close"] < float(self.freqai_sell_floor.value)
        else:
            pred_neg = False

        dataframe.loc[
            (
                (
                    ((trusted & pred_neg)) |
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
            age_minutes = (current_time - trade.open_date_utc).total_seconds() / 60.0
            if age_minutes < 15:
                return self.stoploss
            # Only use dynamic ATR stop when trade is already in profit; otherwise keep fixed SL
            if current_profit <= 0:
                return self.stoploss
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
            # Delay tightening until the trade has decent profit to reduce premature stopouts.
            if current_profit > 0.004:   # > 0.4%
                sl = max(sl, -0.004)
            if current_profit > 0.006:   # > 0.6%
                sl = max(sl, -0.002)
            if current_profit > 0.008:   # > 0.8%
                sl = max(sl, -0.001)
            # Break-even and profit locks (replacing built-in trailing)
            if current_profit > 0.006:   # > 0.6%
                sl = max(sl, 0.0)
            if current_profit > 0.010:   # > 1.0%
                sl = max(sl, 0.003)
            if current_profit > 0.016:   # > 1.6%
                sl = max(sl, 0.006)
            if current_profit > 0.024:   # > 2.4%
                sl = max(sl, 0.010)
            # Time-based gentle tightening for long-running trades
            if age_minutes > 60:
                sl = max(sl, -0.004)
            if age_minutes > 120:
                sl = max(sl, -0.003)
            if age_minutes > 180:
                sl = max(sl, -0.002)
            # Never loosen beyond the initial configured stoploss
            sl = max(sl, self.stoploss)
            return sl
        except Exception:
            # In case dp is not available (unit tests / edge cases)
            return self.stoploss

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        try:
            age_minutes = (current_time - trade.open_date_utc).total_seconds() / 60.0
            if age_minutes >= 120 and current_profit <= 0.0:
                return None
        except Exception:
            # Fallback: no custom exit
            return None
        return None
