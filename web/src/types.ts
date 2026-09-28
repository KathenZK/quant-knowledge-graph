export type Kind = "variant" | "concept" | "strategy";
export interface EntityRef {
  entity_type: "FactorVariant" | "FactorConcept" | "Strategy";
  entity_id: string;
  definition_revision: string;
}
export interface Item extends EntityRef {
  kind: Kind;
  name: string;
  aliases: string[];
  description: string | null;
  economic_logic: string | null;
  category: string | null;
  category_label: string;
  family: string | null;
  family_label: string | null;
  formula: string | null;
  parameters: Record<string, unknown>;
  required_fields: string[];
  markets: string[];
  frequency: string | null;
  axis: string;
  source_name: string | null;
  source_url: string | null;
  source_revision: string | null;
  source_sha256: string | null;
  source_native_ids: string[];
  statuses: {
    catalog: string;
    implementation: string;
    readiness: string;
    result: string;
    display: string;
  };
  result_status: string;
  variant_count: number;
}
export interface Results {
  items: FactorStudyResult[];
  total: number;
  status: string;
  reason: string;
  contract: string;
  contract_status: string;
  levels: string[];
}
export interface Detail extends Item {
  implementations: {
    implementation_id: string;
    language: string;
    status: string;
    executed: boolean;
    revision: string | null;
    sha256: string;
    license: string;
    source_locator: string;
    code_url: string | null;
  }[];
  papers: {
    paper_id: string;
    title: string | null;
    year: number | null;
    authors: string[];
    metadata_status: string;
    url: string | null;
  }[];
  authors: string[];
  concept: Item | null;
  related: Item[];
  relations: {
    relationship_id: string;
    relation: string;
    from_id: string;
    to_id: string;
    from_type: string;
    to_type: string;
    confidence: number;
    evidence: string;
    source_label: string | null;
    source: string | null;
    status: string;
  }[];
  related_strategies: { strategy_id: string; canonical_name: string }[];
  source_locator: string | null;
  lookback: { value: number; unit: string; status: string } | null;
  required_fields_status: string | null;
  license: string;
  terms_url: string | null;
  rights: Record<string, string>;
  results: Results;
}
export interface Facet {
  value: string;
  label: string;
}
export interface Meta {
  mode: "PUBLIC" | "PRIVATE";
  release: string;
  graph_api: string;
  graph_version: string;
  adapter_version: string;
  counts: Record<Kind, number>;
  result_count: number;
  facets: {
    categories: Facet[];
    families: Facet[];
    fields: Facet[];
    markets: Facet[];
  };
  contracts: {
    request: string;
    result: string;
    status: string;
    export_enabled: boolean;
  };
}
export interface SearchResult {
  items: Item[];
  total: number;
  page: number;
  page_size: number;
}
export interface SavedItem extends EntityRef {
  name: string;
  kind: Kind;
  note: string;
  group: string;
}
export interface Notebook {
  schema_version: "quantgraph-list/v1";
  mode: "PUBLIC" | "PRIVATE";
  items: SavedItem[];
}

// Display projection of A's factor-study-result/v1; no second export contract.
export interface FactorStudyResult {
  schema_version: "factor-study-result/v1";
  run_id: string;
  request_id: string;
  research_status: string;
  status: string;
  mapping: {
    identity: { factor_variant_id: string; definition_revision: string };
    implementation: { implementation_id: string; version: string };
  };
  sample: Record<string, unknown>;
  methods: Record<string, unknown>;
  results: Record<string, unknown>;
  limitations: string[];
  trial_registry: {
    assessment?: {
      permitted_conclusion_level: string;
      holdout_evidence_status: string;
    };
  };
}
