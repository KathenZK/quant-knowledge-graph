from quantgraph.collectors.formula_alphas import formula_alphas


def collect(catalog):
    """Pinned community transcription; never promoted as official paper verification."""
    formula_alphas(catalog, sources={'wq101'})
