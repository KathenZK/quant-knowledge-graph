export type Kind =
  "variant" | "concept" | "strategy" | "family" | "template" | "source";
export interface EntityRef {
  entity_type:
    | "FactorVariant"
    | "FactorConcept"
    | "Strategy"
    | "StrategyVariant"
    | "StrategyConcept"
    | "StrategyTemplate"
    | "SourceRecord";
  entity_id: string;
  definition_revision: string;
}
export interface Item extends EntityRef {
  kind: Kind;
  visibility?: "PUBLIC" | "HIDDEN";
  test_record?: boolean;
  source_type?: string;
  record_level?: string;
  strategy?: StrategyKnowledge;
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
  items: (FactorStudyResult | StudySummary)[];
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
    from_name?: string;
    to_name?: string;
    from_kind?: Kind;
    to_kind?: Kind;
    review_status?: string;
    version?: string;
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
    frequencies?: Facet[];
    source_types?: Facet[];
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

export interface StrategyKnowledge {
  facts: Record<string, unknown>;
  structured_rule: Record<string, unknown> | null;
  original_rule: string | null;
  original_rule_notice: string;
  source_author: string | null;
  variant_author: string | null;
  source_support: string;
  provenance_type: string;
  provenance_evidence: string;
  variation_axes: string[];
  parse_status: string;
  parse_reason: string;
  family_id: string | null;
  template_id: string | null;
  research_hypotheses: string[];
  unknowns: string[];
}
export interface RelationGraph {
  items: Detail["relations"];
  nodes: { entity_id: string; name: string; kind: Kind; entity_type: string }[];
  total: number;
  offset: number;
  limit: number;
  types: string[];
}
export interface StudySummary {
  classification?: string;
  execution_status?: string;
  failure_reason?: string;
  source_reproduction?: string;
  conclusion_reason?: string;
  numerical_display?: "ALLOWED" | "RESTRICTED";
  evolution?: {
    parent_experiment_id?: string;
    reason?: string;
    change?: string;
    outcome?: string;
    interpretation?: string;
  };
  job_id: string;
  run_id: string;
  study_type: string;
  study_kind: string;
  conclusion_level: string;
  limitations: string[];
  lineage: EntityRef[];
  metrics: Record<string, number | boolean | null>;
  sample: Record<string, unknown>;
  status: string;
  entity_refs: EntityRef[];
  promotion_allowed: false;
}
