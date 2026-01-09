# AI-Generated Live Test Strategy
from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib

class ai_live_test_strategy(IStrategy):
    """
    AI-Generated strategy for live testing
    Focus: Balanced approach with proper risk management
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short: bool = False
    
    # Conservative ROI for live testing
    minimal_roi = {
        "0": 0.15,    # 15% target
        "60": 0.08,   # 8% after 1 hour
        "120": 0.04,  # 4% after 2 hours
        "240": 0.02   # 2% after 4 hours
    }
    
    # Reasonable stop loss
    stoploss = -0.06  # 6% stop loss
    
    # Trailing stop for profit protection
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.04
    
    startup_candle_count: int = 80
    use_exit_signal = True
    exit_profit_only = False
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.freqai.start(dataframe, metadata, self)
        return dataframe

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata, **kwargs) -> DataFrame:
        dataframe["%-pct-change"] = dataframe["close"].pct_change()
        dataframe["%-ema-200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["%-raw_volume"] = dataframe["volume"]
        dataframe["%-raw_price"] = dataframe["close"]
        return dataframe

    def feature_engineering_standard(self, dataframe: DataFrame, metadata, **kwargs) -> DataFrame:
        dataframe["%-day_of_week"] = (dataframe["date"].dt.dayofweek + 1) / 7
        dataframe["%-hour_of_day"] = (dataframe["date"].dt.hour + 1) / 25
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata, **kwargs) -> DataFrame:
        h = self.freqai_info["feature_parameters"]["label_period_candles"]
        dataframe["&-s_close"] = (
            dataframe["close"].shift(-h).rolling(h).mean() / dataframe["close"] - 1
        )
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        trusted = (dataframe["do_predict"] >= 1) if "do_predict" in dataframe.columns else True
        di_ok = (dataframe["DI_values"] < 1.0) if "DI_values" in dataframe.columns else True
        cond = (trusted & di_ok & (dataframe["&-s_close"] > 0.005))
        dataframe.loc[cond, 'enter_long'] = 1
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        trusted = (dataframe["do_predict"] >= 1) if "do_predict" in dataframe.columns else True
        di_ok = (dataframe["DI_values"] < 1.0) if "DI_values" in dataframe.columns else True
        cond = (trusted & di_ok & (dataframe["&-s_close"] < 0.0))
        dataframe.loc[cond, 'exit_long'] = 1
        return dataframe
