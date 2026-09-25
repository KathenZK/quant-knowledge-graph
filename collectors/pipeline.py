from quantgraph.collectors.common import Catalog
from quantgraph.collectors.qlib.collector import qlib
from quantgraph.collectors.open_asset_pricing.collector import osap
from quantgraph.collectors.jkp.collector import jkp
from quantgraph.collectors.worldquant.collector import collect as worldquant
from quantgraph.collectors.gtja.collector import collect as gtja
from quantgraph.collectors.fama_french.collector import collect as french
from quantgraph.collectors.aqr.collector import collect as aqr

def all_collectors(root):
    c = Catalog(root)
    for collector in (qlib, osap, jkp, worldquant, gtja, french, aqr):
        collector(c)
    return c
