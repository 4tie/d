# pragma pylint: disable=missing-docstring, invalid-name
# --- Do not remove these libs ---
from typing import Dict, List, Any
import numpy as np  # noqa
import pandas as pd  # noqa
from pandas import DataFrame
from freqtrade.strategy.interface import IStrategy
from freqtrade.strategy import IntParameter, DecimalParameter, merge_informative_pair
# --------------------------------
# Add your lib to import here
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class QuickScalpV1(IStrategy):
    """
    QuickScalpV1 – Minimal, fast scalping strategy.

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
    timeframe = '5m'

    # Process only new candles for speed
    process_only_new_candles = True

    # Number of candles required before producing valid signals
    startup_candle_count: int = 50

    # Minimal ROI – scalp ladder (faster profit taking)
    # Config will override if it contains "minimal_roi".
    minimal_roi: Dict[str, float] = {
        "0": 0.005
    }

    # Tight fixed stoploss for scalps – keep losers very small (config can override)
    stoploss = -0.0035

    # Trailing stop – disabled; use fixed SL + ROI
    trailing_stop = False
    trailing_stop_positive = 0.002
    trailing_stop_positive_offset = 0.008
    trailing_only_offset_is_reached = True

    # Use only ROI/Stoploss for exits by default (reduce loss exits by signal)
    use_exit_signal = False
    # If exit signals are enabled, only honor them when trade is in profit
    exit_profit_only = True
    ignore_roi_if_entry_signal = False
    # Use fixed stoploss only (disable custom trailing)
    use_custom_stoploss = False
    can_short = False

    # Order settings
    order_types = {
        'entry': 'limit',
        'exit': 'limit',
        'stoploss': 'market',
        'stoploss_on_exchange': False,
    }

    order_time_in_force = {
        'entry': 'gtc',
        'exit': 'gtc'
    }

    # Protections (strategy-level)
    def protections(self, pair: str) -> List[Dict[str, Any]]:
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 3},
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 60,
                "trade_limit": 3,
                "stop_duration_candles": 60,
                "only_per_pair": False,
                "only_per_side": False,
                "sell_reason_list": [
                    "stop_loss",
                    "stoploss_on_exchange",
                    "trailing_stop_loss",
                    "force_exit",
                    "emergency_exit",
                ],
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 720,
                "trade_limit": 20,
                "stop_duration_candles": 60,
                "max_allowed_drawdown": 0.10,
            },
        ]

    def informative_pairs(self):
        pairs = []
        if self.dp:
            pairs = [(pair, '15m') for pair in self.dp.current_whitelist()]
        return pairs

    # --- Hyperoptable parameters ---
    # Buy parameters
    buy_rsi = IntParameter(15, 70, default=60, space="buy")
    ema_fast_len = IntParameter(5, 21, default=7, space="buy")
    ema_slow_len = IntParameter(20, 55, default=21, space="buy")
    # Trend/Chop filters
    adx_min = IntParameter(5, 40, default=27, space="buy")
    bb_width_min = DecimalParameter(0.010, 0.060, decimals=3, default=0.020, space="buy")
    bb_width_max = DecimalParameter(0.015, 0.150, decimals=3, default=0.055, space="buy")

    # Additional hyperoptable buy gates
    freqai_buy_k = DecimalParameter(0.10, 0.60, decimals=2, default=0.36, space="buy")
    freqai_buy_floor = DecimalParameter(0.0005, 0.0030, decimals=4, default=0.0020, space="buy")
    ema_buf_mult = DecimalParameter(1.0001, 1.0020, decimals=6, default=1.001500, space="buy")
    dip_buf_mult = DecimalParameter(0.9950, 1.0005, decimals=4, default=0.9983, space="buy")
    atrp_min = DecimalParameter(0.001, 0.006, decimals=3, default=0.002, space="buy")

    # Short-entry hyperoptable gates
    short_rsi = IntParameter(15, 65, default=45, space="buy")
    short_ema_buf_mult = DecimalParameter(0.9975, 0.9999, decimals=6, default=0.9991, space="buy")
    freqai_short_k = DecimalParameter(0.10, 0.90, decimals=2, default=0.55, space="buy")
    freqai_short_floor = DecimalParameter(-0.0150, -0.0010, decimals=4, default=-0.0060, space="buy")

    # Sell parameters
    sell_rsi = IntParameter(55, 90, default=70, space="sell")
    exit_ema_loss_mult = DecimalParameter(0.985, 0.999, decimals=3, default=0.996, space="sell")
    # Additional hyperoptable sell gates
    freqai_sell_k = DecimalParameter(0.20, 0.60, decimals=2, default=0.32, space="sell")
    freqai_sell_floor = DecimalParameter(-0.0050, -0.0005, decimals=4, default=-0.0023, space="sell")
    # ATR-based dynamic stoploss params
    atr_period = IntParameter(10, 24, default=16, space="sell")
    atr_mult = DecimalParameter(1.5, 4.5, decimals=1, default=2.5, space="sell")
    atr_min_sl = DecimalParameter(0.004, 0.014, decimals=3, default=0.007, space="sell")  # 0.4% - 1.4%
    atr_max_sl = DecimalParameter(0.009, 0.025, decimals=3, default=0.011, space="sell")  # cap at ~2.5%

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if getattr(self, "config", None) and self.config.get("freqai", {}).get("enabled", False):
            dataframe = self.freqai.start(dataframe, metadata, self)
        # 15m informative trend
        if self.dp:
            informative = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe='15m')
            informative['ema_fast'] = ta.EMA(informative, timeperiod=int(self.ema_fast_len.value))
            informative['ema_slow'] = ta.EMA(informative, timeperiod=int(self.ema_slow_len.value))
            dataframe = merge_informative_pair(dataframe, informative, self.timeframe, '15m', ffill=True)
        if self.dp:
            informative_1h = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe='1h')
            informative_1h['ema_fast'] = ta.EMA(informative_1h, timeperiod=int(self.ema_fast_len.value))
            informative_1h['ema_slow'] = ta.EMA(informative_1h, timeperiod=int(self.ema_slow_len.value))
            dataframe = merge_informative_pair(dataframe, informative_1h, self.timeframe, '1h', ffill=True)
        # EMAs
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=int(self.ema_fast_len.value))
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=int(self.ema_slow_len.value))
        dataframe['ema200'] = ta.EMA(dataframe, timeperiod=200)
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        # ADX for trend-strength filter
        dataframe['adx'] = ta.ADX(dataframe)
        # ATR for dynamic SL sizing (use param period) and ATR% of price for volatility gate
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=int(self.atr_period.value))
        dataframe['atrp'] = dataframe['atr'] / dataframe['close']
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
        # 20-candle breakout levels
        dataframe['high20'] = dataframe['high'].rolling(20).max()
        dataframe['prev_high20'] = dataframe['high20'].shift(1)
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
        # Trend filter to avoid chop / crazy-volatility zones
        trend_ok = (
            (dataframe['adx'] >= self.adx_min.value) &
            (dataframe['bb_width'] >= float(self.bb_width_min.value)) &
            (dataframe['bb_width'] <= float(self.bb_width_max.value))
        )

        # Momentum: RSI above threshold and price above fast EMA
        momo = (
            (dataframe['rsi'] > self.buy_rsi.value) &
            (dataframe['close'] > dataframe['ema_fast'] * float(self.ema_buf_mult.value))
        )
        ema_slope_up = (dataframe['ema_fast'] > dataframe['ema_fast'].shift(1))
        # 15m trend alignment
        tf15_up = (dataframe['ema_fast_15m'] > dataframe['ema_slow_15m']) if ('ema_fast_15m' in dataframe.columns and 'ema_slow_15m' in dataframe.columns) else True
        vol_rising = (dataframe['volume'] > dataframe['vol_ema14'] * 1.05)
        close_above_slow = (dataframe['close'] > dataframe['ema_slow'])
        close_above_ema200 = (dataframe['close'] > dataframe['ema200'])
        tf1h_up = (dataframe['ema_fast_1h'] > dataframe['ema_slow_1h']) if ('ema_fast_1h' in dataframe.columns and 'ema_slow_1h' in dataframe.columns) else True
        # Breakout condition
        breakout = (
            (dataframe['close'] > dataframe['prev_high20'])
        )
        # Dip-buy fallback (mean-reversion) within broader uptrend
        dip_ok = (
            (dataframe['rsi'] > 45) &
            (dataframe['rsi'] < self.buy_rsi.value) &
            (dataframe['close'] <= dataframe['ema_fast'] * float(self.dip_buf_mult.value)) &
            close_above_slow & close_above_ema200 & tf1h_up
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

        dataframe.loc[
            (
                (uptrend & trend_ok & tf15_up & tf1h_up & ema_slope_up & trusted & pred_ok & close_above_slow & close_above_ema200 & ((momo & breakout) | dip_ok) & (dataframe['atrp'] >= float(self.atrp_min.value))) &
                (dataframe['volume'] > dataframe['vol_ma20']) & vol_rising
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
            (dataframe['bb_width'] <= float(self.bb_width_max.value))
        )
        ema_slope_down = (dataframe['ema_fast'] < dataframe['ema_fast'].shift(1))
        momo_short = (
            (dataframe['rsi'] < self.short_rsi.value) &
            (dataframe['close'] < dataframe['ema_fast'] * float(self.short_ema_buf_mult.value))
        )

        trusted = (dataframe["do_predict"] == 1) if "do_predict" in dataframe.columns else True
        if "&-s_close" in dataframe.columns:
            if "&-s_close_mean" in dataframe.columns and "&-s_close_std" in dataframe.columns:
                short_thresh = np.minimum(float(self.freqai_short_floor.value), dataframe["&-s_close_mean"] - float(self.freqai_short_k.value) * dataframe["&-s_close_std"])
                pred_short_ok = dataframe["&-s_close"] < short_thresh
            else:
                pred_short_ok = dataframe["&-s_close"] < float(self.freqai_short_floor.value)
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
            if age_minutes < 30:
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

            # Keep fixed SL until decent profit is reached, then lock BE and trail upwards only.
            sl = self.stoploss
            if current_profit >= 0.008:
                sl = max(sl, 0.0)
                if current_profit >= 0.012:
                    sl = max(sl, 0.003)
                if current_profit >= 0.018:
                    sl = max(sl, 0.006)
                if current_profit >= 0.025:
                    sl = max(sl, 0.010)
                # Time-based gentle tightening only once in profit
                if age_minutes > 60:
                    sl = max(sl, 0.002)
                if age_minutes > 120:
                    sl = max(sl, 0.004)
                if age_minutes > 180:
                    sl = max(sl, 0.006)
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
