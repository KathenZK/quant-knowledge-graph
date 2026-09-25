"""Typed SQLite tables plus JSONL/CSV/Parquet exports, including empty phase-2 contracts."""
import json
import sqlite3
from pathlib import Path
import pandas as pd
from quantgraph.models.entities import ENTITY_MODELS

PRIMARY_KEYS={
    'factor_concepts':'canonical_factor_id','factor_variants':'factor_variant_id',
    'formulas':'formula_id','papers':'paper_id','authors':'author_id','sources':'source_id',
    'licenses':'license_id','datasets':'dataset_id','implementations':'implementation_id',
    'strategies':'strategy_id','backtest_results':'backtest_result_id',
    'relationships':'relationship_id','aliases':'alias_id','source_records':'record_id',
    'id_map':'legacy_record_id',
}
TYPES={'factor_concepts':'FactorConcept','factor_variants':'FactorVariant','formulas':'Formula','papers':'Paper',
    'authors':'Author','sources':'Source','licenses':'License','datasets':'Dataset','implementations':'Implementation',
    'strategies':'Strategy','backtest_results':'BacktestResult','aliases':'Alias','source_records':'SourceRecord'}
REFS={
    'factor_variants':{'canonical_factor_id':('factor_concepts','canonical_factor_id'),'source_id':('sources','source_id'),'license_id':('licenses','license_id'),'formula_id':('formulas','formula_id')},
    'sources':{'license_id':('licenses','license_id')},
    'datasets':{'source_id':('sources','source_id'),'license_id':('licenses','license_id')},
    'implementations':{'factor_variant_id':('factor_variants','factor_variant_id'),'source_record_id':('source_records','record_id')},
    'aliases':{'factor_variant_id':('factor_variants','factor_variant_id'),'canonical_factor_id':('factor_concepts','canonical_factor_id')},
    'source_records':{'factor_variant_id':('factor_variants','factor_variant_id'),'source_id':('sources','source_id'),'dataset_id':('datasets','dataset_id')},
    'strategy_factor':{'strategy_id':('strategies','strategy_id'),'variant_id':('factor_variants','factor_variant_id'),'factor_id':('factor_concepts','canonical_factor_id'),'backtest_result_id':('backtest_results','backtest_result_id')},
    'backtest_results':{'strategy_id':('strategies','strategy_id')},
    'relationships':{'from_id':('entities','entity_id'),'to_id':('entities','entity_id')},
    'id_map':{'factor_variant_id':('factor_variants','factor_variant_id'),'canonical_factor_id':('factor_concepts','canonical_factor_id')},
}


def encode(value):
    if isinstance(value,(dict,list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'), allow_nan=False)
    return value


def write_graph(path, tables):
    path=Path(path);path.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path/'quantgraph.sqlite')
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('CREATE TABLE entities (entity_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL)')
    order = ["licenses", "sources", "factor_concepts", "authors", "papers", "formulas", "datasets", "factor_variants", "source_records", "implementations", "strategies", "backtest_results", "strategy_factor", "aliases", "id_map", "relationships"]
    for name in order:
        rows = tables[name]
        columns=list(ENTITY_MODELS[name].model_fields) if name in ENTITY_MODELS else list(rows[0]) if rows else []
        pk=PRIMARY_KEYS.get(name)
        rows.sort(key=lambda r: r[pk] if pk else (r['strategy_id'],r['variant_id'],r['role']))
        fields={k:'TEXT' for k in columns}
        for k in columns:
            if k in {'confidence'}:fields[k]='REAL'
            if k in {'paper_year','year','attribution_required','executed','observations_ingested','backtest_ready'}:fields[k]='INTEGER'
        definitions=[f'"{k}" {fields[k]}'+(' PRIMARY KEY' if k==pk else '') for k in columns]
        definitions += ['payload TEXT NOT NULL CHECK(json_valid(payload))']
        if name=='strategy_factor':
            definitions+=['PRIMARY KEY(strategy_id,variant_id,role)', 'CHECK(confidence >= 0 AND confidence <= 1)',
                "CHECK(role IN ('signal','entry','exit','filter','weight','risk','exposure'))",
                "CHECK(length(evidence)>0 AND length(source)>0)",
                "CHECK(attribution_status != 'EMPIRICALLY_TESTED' OR backtest_result_id IS NOT NULL)"]
        for field,(target,key) in REFS.get(name,{}).items():
            definitions.append(f'FOREIGN KEY("{field}") REFERENCES "{target}"("{key}") DEFERRABLE INITIALLY DEFERRED')
        con.execute(f'CREATE TABLE "{name}" ('+','.join(definitions)+')')
        flat=[{k:encode(r.get(k)) for k in columns} for r in rows]
        for r,f in zip(rows,flat):
            con.execute(f'INSERT INTO "{name}" ('+','.join('"'+k+'"' for k in columns)+',payload) VALUES ('+','.join('?' for _ in range(len(columns)+1))+')', list(f.values())+[encode(r)])
            if name in TYPES:
                con.execute('INSERT INTO entities VALUES (?,?)',(r[pk],TYPES[name]))
        (path/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n' for r in rows))
        frame=pd.DataFrame(flat,columns=columns,dtype=object)
        frame.to_csv(path/(name+'.csv'),index=False)
        frame.to_parquet(path/(name+'.parquet'),index=False)
    con.executescript('''
    CREATE INDEX idx_variant_concept ON factor_variants(canonical_factor_id);
    CREATE INDEX idx_variant_category ON factor_variants(category,asset_class);
    CREATE INDEX idx_alias_name ON aliases(normalized_alias,namespace);
    CREATE INDEX idx_relation_from ON relationships(from_id);
    CREATE INDEX idx_relation_to ON relationships(to_id);
    CREATE INDEX idx_sf_factor ON strategy_factor(factor_id,variant_id);
    CREATE TRIGGER strategy_factor_concept_insert BEFORE INSERT ON strategy_factor
    WHEN NEW.factor_id != (SELECT canonical_factor_id FROM factor_variants WHERE factor_variant_id=NEW.variant_id)
    BEGIN SELECT RAISE(ABORT,'variant does not belong to factor concept'); END;
    CREATE TRIGGER strategy_factor_concept_update BEFORE UPDATE ON strategy_factor
    WHEN NEW.factor_id != (SELECT canonical_factor_id FROM factor_variants WHERE factor_variant_id=NEW.variant_id)
    BEGIN SELECT RAISE(ABORT,'variant does not belong to factor concept'); END;
    ''')
    if con.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('Dangling graph reference')
    wrong=con.execute('SELECT r.relationship_id FROM relationships r JOIN entities e ON r.from_id=e.entity_id WHERE r.from_type != e.entity_type UNION SELECT r.relationship_id FROM relationships r JOIN entities e ON r.to_id=e.entity_id WHERE r.to_type != e.entity_type').fetchall()
    if wrong:
        raise ValueError(f'Wrong relationship endpoint types: {wrong[:3]}')
    con.commit()
    (path/'schema.sql').write_text('\n'.join(row[0]+';' for row in con.execute('SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY rowid'))+'\n')
    con.close()
