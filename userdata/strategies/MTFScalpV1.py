# MTFScalpV1 - Multi-timeframe gated scalp strategy for Freqtrade
# - 15m trend gate (EMA50 > EMA100) to avoid chop
# - 3m entries with momentum filter
# - ATR-based initial stoploss computed at entry
# - Break-even bump and soft trailing via custom_stoploss to reduce quick whipsaw losses
# - Small ROI ladder for fast exits
# - Profit-only exit signals disabled (ROI + SL only)

from freqtrade.strategy.interface import IStrategy
from freqtrade.strategy import merge_informative_pair, IntParameter, DecimalParameter
from typing import Dict, List, Tuple
from pandas import DataFrame
import talib.abstract as ta
import numpy as np


class MTFScalpV1(IStrategy):
    INTERFACE_VERSION = 3

    # Base timeframe and informative timeframe
    timeframe = '1m'
    informative_timeframe = '15m'

    # Minimal ROI ladder for scalps (decreasing faster over time)
    minimal_roi: Dict[str, float] = {
        "0": 0.003,    # 0.3%
        "8": 0.001,    # 0.1% after 8 min
        "20": 0.0      # 0% after 20 min
    }

    # Disable trailing to avoid death-by-1k-cuts
    trailing_stop = False
    trailing_stop_positive = 0.003
    trailing_stop_positive_offset = 0.006
    trailing_only_offset_is_reached = True

    # Engine / runtime
    process_only_new_candles = True
    startup_candle_count = 2000  # 1m base: ensure enough history for 15m EMA(100) + features
    use_custom_stoploss = True

    # Exit handling
    use_exit_signal = False      # rely on ROI + fixed SL + custom_exit
    use_custom_exit = True       # enable custom_exit() callbacks
    exit_profit_only = False     # allow time-based scratches / cuts even if < 0
    ignore_roi_if_entry_signal = False

    # Order settings (config may override)
    order_types = {
        'entry': 'limit',
        'exit': 'limit',
        'stoploss': 'market',
        'stoploss_on_exchange': False,
    }

    # Protections
    protections = [
        {
            "method": "CooldownPeriod",
            "stop_duration_candles": 20,
        },
        {
            "method": "StoplossGuard",
            "lookback_period_candles": 120,
            "trade_limit": 1,
            "stop_duration_candles": 40,
            "only_per_pair": False,
        },
        {
            "method": "MaxDrawdown",
            "lookback_period_candles": 720,
            "trade_limit": 10,
            "stop_duration_candles": 1440,
            "max_drawdown": 0.2,
            "only_per_pair": False,
        },
    ]

    # Params (hyperoptable)
    buy_rsi = IntParameter(45, 65, default=48, space='buy')
    ema_fast_len = IntParameter(8, 20, default=12, space='buy')
    ema_slow_len = IntParameter(24, 72, default=36, space='buy')
    adx_min = IntParameter(18, 35, default=20, space='buy')
    bb_width_max = DecimalParameter(0.06, 0.14, decimals=3, default=0.10, space='buy')
    bb_width_min = DecimalParameter(0.008, 0.020, decimals=3, default=0.012, space='buy')
    bb_width15_min = DecimalParameter(0.015, 0.040, decimals=3, default=0.016, space='buy')
    bb_width15_max = DecimalParameter(0.090, 0.200, decimals=3, default=0.12, space='buy')

    # ATR stop params (faster and tighter for 1m)
    atr_period = 7
    atr_mult = DecimalParameter(1.2, 2.2, decimals=2, default=1.4, space='stoploss')
    atr_min_sl = DecimalParameter(0.001, 0.004, decimals=3, default=0.002, space='stoploss')   # 0.1% - 0.4%
    atr_max_sl = DecimalParameter(0.004, 0.008, decimals=3, default=0.005, space='stoploss')  # 0.4% - 0.8%

    # Fallback SL (used by stoploss hyperopt space, but custom_stoploss governs actual exits).
    stoploss = DecimalParameter(-0.050, -0.008, decimals=3, default=-0.020, space='stoploss')

    # Break-even and soft trailing parameters (all ratios)
    be_profit = DecimalParameter(0.002, 0.006, decimals=3, default=0.003, space='stoploss')      # Arm BE sooner on 1m
    be_offset = DecimalParameter(0.000, 0.002, decimals=3, default=0.001, space='stoploss')      # Lock slightly above entry to cover fees
    trail_arm = DecimalParameter(0.008, 0.020, decimals=3, default=0.010, space='stoploss')      # Start trailing conservatively
    trail_dist = DecimalParameter(0.003, 0.008, decimals=3, default=0.004, space='stoploss')     # Trail distance 0.4%

    def informative_pairs(self) -> List[Tuple[str, str]]:
        # Use current whitelist for informative timeframes (15m and 5m)
        if hasattr(self.dp, 'current_whitelist') and callable(self.dp.current_whitelist):
            pairs = self.dp.current_whitelist()
        else:
            pairs = []
        inf: List[Tuple[str, str]] = []
        for p in pairs:
            inf.append((p, self.informative_timeframe))
            inf.append((p, '5m'))
        return inf

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Base timeframe indicators
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=int(self.ema_fast_len.value))
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=int(self.ema_slow_len.value))
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi7'] = ta.RSI(dataframe, timeperiod=7)
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=7)
        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_upper'] = bb['upperband']
        dataframe['bb_middle'] = bb['middleband']
        dataframe['bb_lower'] = bb['lowerband']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle'].replace(0, np.nan)
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=self.atr_period)
        dataframe['vol_ema'] = dataframe['volume'].ewm(span=20, adjust=False).mean()
        # Candle quality / extension filters
        dataframe['candle_range'] = (dataframe['high'] - dataframe['low']).replace(0, np.nan)
        dataframe['body'] = (dataframe['close'] - dataframe['open']).abs()
        dataframe['body_pct'] = dataframe['body'] / dataframe['candle_range']
        dataframe['dist_ema_fast'] = (dataframe['close'] / dataframe['ema_fast']) - 1.0

        # 15m informative
        pair = metadata.get('pair') if metadata else None
        if pair:
            informative = self.dp.get_pair_dataframe(pair=pair, timeframe=self.informative_timeframe)
            if informative is not None and len(informative) > 0:
                informative['ema50'] = ta.EMA(informative, timeperiod=50)
                informative['ema100'] = ta.EMA(informative, timeperiod=100)
                informative['adx'] = ta.ADX(informative, timeperiod=14)
                bb15 = ta.BBANDS(informative, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
                informative['bb_upper'] = bb15['upperband']
                informative['bb_middle'] = bb15['middleband']
                informative['bb_lower'] = bb15['lowerband']
                informative['bb_width'] = (informative['bb_upper'] - informative['bb_lower']) / informative['bb_middle'].replace(0, np.nan)
                # Merge into base timeframe
                dataframe = merge_informative_pair(dataframe, informative, self.timeframe, self.informative_timeframe, ffill=True)
                # Ensure no div-by-zero
                if 'ema50_15m' not in dataframe:
                    dataframe['ema50_15m'] = np.nan
                if 'ema100_15m' not in dataframe:
                    dataframe['ema100_15m'] = np.nan
                if 'adx_15m' not in dataframe:
                    dataframe['adx_15m'] = np.nan
                if 'bb_width_15m' not in dataframe:
                    dataframe['bb_width_15m'] = np.nan
            # 5m informative (additional trend confirmation to increase opportunities)
            inf5 = self.dp.get_pair_dataframe(pair=pair, timeframe='5m')
            if inf5 is not None and len(inf5) > 0:
                inf5['ema50'] = ta.EMA(inf5, timeperiod=50)
                inf5['ema100'] = ta.EMA(inf5, timeperiod=100)
                inf5['adx'] = ta.ADX(inf5, timeperiod=14)
                bb5 = ta.BBANDS(inf5, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
                inf5['bb_upper'] = bb5['upperband']
                inf5['bb_middle'] = bb5['middleband']
                inf5['bb_lower'] = bb5['lowerband']
                inf5['bb_width'] = (inf5['bb_upper'] - inf5['bb_lower']) / inf5['bb_middle'].replace(0, np.nan)
                dataframe = merge_informative_pair(dataframe, inf5, self.timeframe, '5m', ffill=True)
                if 'ema50_5m' not in dataframe:
                    dataframe['ema50_5m'] = np.nan
                if 'ema100_5m' not in dataframe:
                    dataframe['ema100_5m'] = np.nan
                if 'adx_5m' not in dataframe:
                    dataframe['adx_5m'] = np.nan
                if 'bb_width_5m' not in dataframe:
                    dataframe['bb_width_5m'] = np.nan
        
        # Donchian breakout (20) - shifted to avoid same-candle lookahead
        dataframe['donchian_high_20'] = dataframe['high'].rolling(20).max().shift(1)
        dataframe['breakout20'] = dataframe['close'] > dataframe['donchian_high_20'] * 1.001
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['enter_long'] = 0

        # Trend gates: accept either 15m (with slope) or 5m
        trend_up_15m = (
            (dataframe['ema50_15m'] > dataframe['ema100_15m']) &
            (dataframe['ema50_15m'] > dataframe['ema50_15m'].shift(1)) &
            (dataframe['adx_15m'] >= 22)
        )
        trend_up_5m = (
            (dataframe['ema50_5m'] > dataframe['ema100_5m']) &
            (dataframe['ema50_5m'] > dataframe['ema50_5m'].shift(1)) &
            (dataframe['adx_5m'] >= 22)
        )
        trend_ok = trend_up_15m | trend_up_5m

        # Momentum entry on base timeframe
        above_trend_ma = (dataframe['close'] > dataframe['ema50_15m']) | (dataframe['close'] > dataframe['ema50_5m'])
        cond_momo = (
            trend_ok &
            (dataframe['ema_fast'] > dataframe['ema_slow']) &
            (dataframe['close'] > dataframe['ema_fast']) &
            (above_trend_ma) &
            (dataframe['rsi'] >= int(self.buy_rsi.value)) &
            (dataframe['adx'] >= int(self.adx_min.value)) &
            (dataframe['body_pct'] >= 0.50) &                  # Avoid wick-dominated candles
            (dataframe['dist_ema_fast'] <= 0.010) &            # Allow slight extension on 3m
            (dataframe['bb_width'] <= float(self.bb_width_max.value)) &
            (dataframe['bb_width'] >= float(self.bb_width_min.value)) &
            (dataframe['bb_width_15m'] >= float(self.bb_width15_min.value)) &
            (dataframe['bb_width_15m'] <= float(self.bb_width15_max.value)) &
            (dataframe['volume'] >= dataframe['vol_ema'] * 0.7)
        )

        # Add a breakout condition to avoid mid-range entries
        cond_breakout = dataframe['breakout20']

        cond_final = cond_momo & cond_breakout
        dataframe.loc[cond_final, 'enter_long'] = 1
        dataframe.loc[cond_final, 'enter_tag'] = 'momo_breakout'

        # Additional pullback-to-EMA entry to increase trade frequency
        cond_pullback = (
            trend_ok &
            (dataframe['ema_fast'] > dataframe['ema_slow']) &
            above_trend_ma &
            (dataframe['close'] > dataframe['ema_fast']) &
            (dataframe['close'].shift(1) <= dataframe['ema_fast'].shift(1)) &  # cross back above EMA fast
            (dataframe['close'] > dataframe['open']) & (dataframe['close'].shift(1) < dataframe['open'].shift(1)) &  # red -> green
            (dataframe['rsi7'] >= 45) &
            (dataframe['dist_ema_fast'] <= 0.012) &
            (dataframe['bb_width'] >= float(self.bb_width_min.value)) &
            (dataframe['bb_width'] <= float(self.bb_width_max.value)) &
            (dataframe['volume'] >= dataframe['vol_ema'] * 0.8)
        )

        dataframe.loc[cond_pullback, 'enter_long'] = 1
        dataframe.loc[cond_pullback, 'enter_tag'] = 'pullback_cross'
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # We rely on ROI table and custom stoploss only
        dataframe['exit_long'] = 0
        return dataframe

    def custom_exit(self, pair: str, trade, current_time, current_rate: float, current_profit: float, **kwargs):
        """
        Time-based scratch exits tuned for 1m:
        - Scratch near BE if trade goes nowhere for ≥ 6 minutes.
        - Hard time stop at ≥ 15 minutes if still red beyond a small threshold.
        """
        try:
            # Duration in minutes
            trade_dur_min = int((current_time - trade.open_date_utc).total_seconds() / 60)
        except Exception:
            return None

        # Scratch near break-even if trade goes nowhere for 6+ candles (6 minutes on 1m)
        if trade_dur_min >= 6 and current_profit is not None and current_profit > -0.001:
            return "time_exit_scratch"

        # Hard time stop after ~15 candles (15 minutes on 1m)
        if trade_dur_min >= 15 and current_profit is not None and current_profit <= -0.003:
            return "time_exit_cut"

        return None
    def custom_stoploss(self, pair: str, trade, current_time, current_rate: float, current_profit: float, **kwargs) -> float:
        """Dynamic stoploss:
        - Compute ATR-based initial stop once per trade.
        - Move to break-even once profit exceeds threshold.
        - Soft trail after a higher profit threshold to lock in gains.
        Returns negative ratio relative to current_rate as required by Freqtrade.
        """

        # Ensure user_data dict exists
        if not hasattr(trade, 'user_data') or trade.user_data is None:
            trade.user_data = {}

        # Initialize per-trade constants on first call
        if 'fixed_sl' not in trade.user_data or 'entry_price' not in trade.user_data or 'initial_sl_rate' not in trade.user_data:
            df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if df is None or len(df) == 0:
                return None
            last = df.iloc[-1]
            atr = last.get('atr', None)
            entry = float(trade.open_rate or current_rate or last.get('close', np.nan))
            if atr is None or np.isnan(atr) or atr == 0 or np.isnan(entry) or entry == 0:
                return None

            atr_frac = float(atr) / float(last['close'])
            sl_frac = atr_frac * float(self.atr_mult.value)
            sl_frac = max(float(self.atr_min_sl.value), min(sl_frac, float(self.atr_max_sl.value)))

            trade.user_data['fixed_sl'] = float(sl_frac)
            trade.user_data['entry_price'] = float(entry)
            trade.user_data['initial_sl_rate'] = float(entry * (1.0 - sl_frac))

        entry_price: float = float(trade.user_data['entry_price'])
        initial_sl_rate: float = float(trade.user_data['initial_sl_rate'])

        # Start with the initial fixed stop
        new_stop_rate = initial_sl_rate

        # Break-even bump
        if current_profit is not None and current_profit >= float(self.be_profit.value):
            be_rate = entry_price * (1.0 + float(self.be_offset.value))
            new_stop_rate = max(new_stop_rate, be_rate)

        # Soft trailing once armed
        if current_profit is not None and current_profit >= float(self.trail_arm.value):
            trail_rate = current_rate * (1.0 - float(self.trail_dist.value))
            new_stop_rate = max(new_stop_rate, trail_rate)

        # Convert absolute stop rate to distance relative to current_rate
        distance = (new_stop_rate / float(current_rate)) - 1.0

        # Ensure the stop distance is negative (below current price). If not, clamp just below market.
        if distance >= -1e-6:
            distance = -0.0001  # 0.01%

        return float(distance)
