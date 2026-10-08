import {
  sqliteTable,
  text,
  integer,
  primaryKey,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";
export const batches = sqliteTable("qg_batches", {
  batchId: text("batch_id").primaryKey(),
  parentId: text("parent_id"),
  manifestSha: text("manifest_sha").notNull(),
  manifestJson: text("manifest_json").notNull(),
  status: text("status").notNull(),
  createdAt: text("created_at").notNull(),
  activatedAt: text("activated_at"),
});
export const settings = sqliteTable("qg_settings", {
  key: text("key").primaryKey(),
  value: text("value").notNull(),
});
export const objects = sqliteTable("qg_objects", {
  sha256: text("sha256").primaryKey(),
  bytes: integer("bytes").notNull(),
  objectKey: text("object_key").notNull(),
  metadataJson: text("metadata_json").notNull(),
});
export const files = sqliteTable(
  "qg_files",
  {
    batchId: text("batch_id").notNull(),
    path: text("path").notNull(),
    sha256: text("sha256").notNull(),
    bytes: integer("bytes").notNull(),
  },
  (t) => [primaryKey({ columns: [t.batchId, t.path] })],
);
export const notes = sqliteTable(
  "qg_notes",
  {
    ownerId: text("owner_id").notNull(),
    targetKey: text("target_key").notNull(),
    recordRevision: integer("record_revision").notNull(),
    bodyJson: text("body_json").notNull(),
    updatedAt: text("updated_at").notNull(),
  },
  (t) => [primaryKey({ columns: [t.ownerId, t.targetKey] })],
);
export const feedback = sqliteTable(
  "qg_feedback",
  {
    seq: integer("seq").primaryKey(),
    ownerId: text("owner_id").notNull(),
    targetKey: text("target_key").notNull(),
    recordRevision: integer("record_revision").notNull(),
    mutationId: text("mutation_id").notNull(),
    requestSha: text("request_sha").notNull(),
    payloadSha: text("payload_sha").notNull(),
    targetJson: text("target_json").notNull(),
    payloadJson: text("payload_json").notNull(),
    bodyJson: text("body_json").notNull(),
    createdAt: text("created_at").notNull(),
  },
  (t) => [
    uniqueIndex("qg_feedback_mutation").on(t.ownerId, t.mutationId),
    uniqueIndex("qg_feedback_version").on(
      t.ownerId,
      t.targetKey,
      t.recordRevision,
    ),
  ],
);
export const consumer = sqliteTable("qg_consumers", {
  consumerId: text("consumer_id").primaryKey(),
  cursor: integer("cursor").notNull(),
  updatedAt: text("updated_at").notNull(),
});
export const refs = sqliteTable(
  "qg_refs",
  {
    refKey: text("ref_key").primaryKey(),
    entityId: text("entity_id").notNull(),
    definitionRevision: text("definition_revision").notNull(),
    bodyJson: text("body_json").notNull(),
  },
  (t) => [
    uniqueIndex("qg_refs_entity_revision").on(t.entityId, t.definitionRevision),
  ],
);
export const resultRefs = sqliteTable("qg_result_refs", {
  refKey: text("ref_key").primaryKey(),
  bodyJson: text("body_json").notNull(),
});
