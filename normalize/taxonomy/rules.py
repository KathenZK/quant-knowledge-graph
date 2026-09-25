"""Explicit categories. No name-based equivalence or unsupported crypto claims."""
CONCEPT_CATEGORIES = {
    "历史价格动量": "momentum", "时间序列动量": "momentum", "动量多空组合": "momentum",
    "账面市值比": "value", "价值多空组合": "value", "股息率": "value",
    "规模": "size", "小盘减大盘组合": "size", "应计项目": "accounting",
    "资产增长": "investment", "投资强度": "investment",
    "毛利润能力": "profitability", "营业利润能力": "profitability",
    "市场贝塔": "risk", "低贝塔对冲高贝塔": "risk", "市场超额收益": "market",
    "特质波动率": "volatility", "短期反转": "reversal", "长期反转": "reversal",
    "质量": "quality", "优质减劣质组合": "quality", "盈余意外": "earnings",
    "净股权发行": "financing",
}
ALIASES = {
    "历史价格动量": ["Momentum", "Price Momentum", "MOM"],
    "时间序列动量": ["Time Series Momentum", "TSMOM"],
    "账面市值比": ["Book to Market", "Book-to-Market"],
    "动量多空组合": ["Momentum Portfolio", "WML", "UMD"],
}


def category(record):
    family = record["factor_concept"]
    if family in CONCEPT_CATEGORIES:
        return CONCEPT_CATEGORIES[family]
    if record["source_id"] == "qlib":
        name = family.removeprefix("qlib:")
        if name in {"lag_close_ratio", "MA", "BETA", "RSQR", "RESI", "RSV", "CNTP", "CNTN", "CNTD", "SUMP", "SUMN", "SUMD"}:
            return "momentum" if name == "lag_close_ratio" else "price_trend"
        if name in {"STD", "WVMA"}:
            return "volatility"
        return "technical_price_volume"
    return "unclassified"
