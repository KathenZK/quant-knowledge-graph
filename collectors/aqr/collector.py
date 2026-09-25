"""AQR metadata only; no returns or copyrighted prose."""
def collect(c):
    aq=[
      ('BAB','Betting Against Beta','betting_against_beta','aqr_bab',['Andrea Frazzini','Lasse Heje Pedersen'],2014),
      ('QMJ','Quality Minus Junk','qmj_portfolio','aqr_qmj',['Clifford Asness','Andrea Frazzini','Lasse Heje Pedersen'],2014),
      ('ValueEverywhere','Value and Momentum Everywhere: Value','hml_portfolio','aqr_vm',['Clifford S. Asness','Tobias J. Moskowitz','Lasse Heje Pedersen'],2013),
      ('MomentumEverywhere','Value and Momentum Everywhere: Momentum','momentum_portfolio','aqr_vm',['Clifford S. Asness','Tobias J. Moskowitz','Lasse Heje Pedersen'],2013),
      ('HMLDevil',"The Devil in HML's Details",'hml_portfolio','aqr_hml',['Clifford S. Asness','Andrea Frazzini'],2013),
      ('TSMOM','Time Series Momentum','time_series_momentum','aqr_tsmom',['Tobias J. Moskowitz','Yao Hua Ooi','Lasse Heje Pedersen'],2012),
    ]
    for native,name,concept,key,authors,year in aq:
        c.add('aqr',native,name,concept,source_key=key,source_name='AQR Data Library',aliases=[native],paper_title='Value and Momentum Everywhere' if key=='aqr_vm' else name,paper_year=year,authors=authors,record_kind='factor_portfolio',frequency='monthly',asset_class='multi_asset' if key in {'aqr_vm','aqr_tsmom'} else 'equity',quality_tier='metadata_only',license='AQR Terms of Use; copyright; no blanket redistribution permission',terms='Copyright and Trademarks section requires express prior written consent for reproduction/distribution. Metadata only; no raw definition, formula, code or returns ingested.',terms_url=c.url('aqr_terms'),commercial_use_flag='permission_required',source_locator='dataset title and bibliographic reference',notes=['仅保存检索入口和书目信息，不收录页面正文、公式或收益序列。','年份按数据页引用版本；不等于最终期刊出版年。'])
