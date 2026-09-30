CREATE TABLE `qg_batches` (
	`batch_id` text PRIMARY KEY NOT NULL,
	`parent_id` text,
	`manifest_sha` text NOT NULL,
	`manifest_json` text NOT NULL,
	`status` text NOT NULL,
	`created_at` text NOT NULL,
	`activated_at` text
);
--> statement-breakpoint
CREATE TABLE `qg_consumers` (
	`consumer_id` text PRIMARY KEY NOT NULL,
	`cursor` integer NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `qg_feedback` (
	`seq` integer PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`target_key` text NOT NULL,
	`record_revision` integer NOT NULL,
	`mutation_id` text NOT NULL,
	`request_sha` text NOT NULL,
	`payload_sha` text NOT NULL,
	`target_json` text NOT NULL,
	`payload_json` text NOT NULL,
	`body_json` text NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `qg_feedback_mutation` ON `qg_feedback` (`owner_id`,`mutation_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `qg_feedback_version` ON `qg_feedback` (`owner_id`,`target_key`,`record_revision`);--> statement-breakpoint
CREATE TABLE `qg_files` (
	`batch_id` text NOT NULL,
	`path` text NOT NULL,
	`sha256` text NOT NULL,
	`bytes` integer NOT NULL,
	PRIMARY KEY(`batch_id`, `path`)
);
--> statement-breakpoint
CREATE TABLE `qg_notes` (
	`owner_id` text NOT NULL,
	`target_key` text NOT NULL,
	`record_revision` integer NOT NULL,
	`body_json` text NOT NULL,
	`updated_at` text NOT NULL,
	PRIMARY KEY(`owner_id`, `target_key`)
);
--> statement-breakpoint
CREATE TABLE `qg_objects` (
	`sha256` text PRIMARY KEY NOT NULL,
	`bytes` integer NOT NULL,
	`object_key` text NOT NULL,
	`metadata_json` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `qg_refs` (
	`ref_key` text PRIMARY KEY NOT NULL,
	`entity_id` text NOT NULL,
	`definition_revision` text NOT NULL,
	`body_json` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `qg_refs_entity_revision` ON `qg_refs` (`entity_id`,`definition_revision`);--> statement-breakpoint
CREATE TABLE `qg_result_refs` (
	`ref_key` text PRIMARY KEY NOT NULL,
	`body_json` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `qg_settings` (
	`key` text PRIMARY KEY NOT NULL,
	`value` text NOT NULL
);
