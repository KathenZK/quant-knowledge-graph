"""Explicit research specifications transcribed from pinned implementation evidence.

DSL ingestion describes a hypothesis. It does not certify its source, rights or
execution, and cannot make any candidate eligible without independent review.
"""
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class LongOnlySpec(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    type: Literal['long_only_signal']
    signal: Literal['PRICE_SMA','ZSCORE_REVERSION','EMA_CROSSOVER']
    asset: str = Field(pattern=r'^[A-Z][A-Z0-9./-]{1,19}$')
    schedule: Literal['daily_eod','4h_close']
    parameters: list[float] = Field(min_length=1,max_length=3)
    comparison: Literal['gt_else_cash','lt_negative_threshold_else_cash','cross_up_enter_cross_down_exit']
    allocation: Literal['all_equity_net_of_costs']
    cash: Literal['USD_ZERO_INTEREST','EUR_ZERO_INTEREST']
    initial_position: Literal['cash']
    indicator_semantics: str = Field(min_length=1)
    entry: str = Field(min_length=1)
    exit: str = Field(min_length=1)
    rebalance: Literal['signal_change_only']
    stop_loss_fraction: float | None = Field(ge=0,lt=1)
    take_profit_fraction: float | None = Field(gt=0)
    parent_record_id: str = Field(min_length=1)
    derivation: str = Field(min_length=1)

    @model_validator(mode='after')
    def valid_parameters(self):
        p=self.parameters
        if any(x<=0 for x in p) or p[0]!=int(p[0]):raise ValueError('Positive explicit lookbacks required')
        expected={'PRICE_SMA':(1,'gt_else_cash'),'ZSCORE_REVERSION':(2,'lt_negative_threshold_else_cash'),
                  'EMA_CROSSOVER':(2,'cross_up_enter_cross_down_exit')}
        n,condition=expected[self.signal]
        if len(p)!=n or condition!=self.comparison:raise ValueError('Signal/parameter/condition mismatch')
        if self.signal=='EMA_CROSSOVER' and (p[1]!=int(p[1]) or p[0]>=p[1]):raise ValueError('Fast < slow required')
        if self.signal=='ZSCORE_REVERSION' and p[0]<2:raise ValueError('Sample standard deviation needs at least two observations')
        return self


def parse_dsl(text):
    if not text.startswith('QG-DSL/1\n'):return None
    try:
        spec=LongOnlySpec.model_validate_json(text.split('\n',1)[1]).model_dump(mode='json')
    except (ValueError,TypeError):return None
    # Binding cash explicitly avoids fabricating an ETF or an unknown cash yield.
    return {**spec,'then':{'asset':spec['asset'],'allocation':'full'},
            'else':{'asset':None,'cash':True,'allocation':'full'},
            'execution_timing':None,'price_adjustment':None,'missing_data_policy':None,'costs':None}
