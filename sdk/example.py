from quantgraph import FactorDB

if __name__=='__main__':
    db=FactorDB()
    print(db.stats())
    candidates=db.search_factors(category='momentum',asset_class='equity',limit=3)
    for v in candidates:
        print(v['source_name'],v['variant_name'],v['factor_variant_id'],v['rights_status'])
    print('Strategies using momentum:',db.find_strategies(factor='momentum'))
