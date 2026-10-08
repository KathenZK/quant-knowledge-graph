CREATE TRIGGER qg_feedback_no_update BEFORE UPDATE ON qg_feedback BEGIN SELECT RAISE(ABORT,'Immutable feedback event'); END;
--> statement-breakpoint
CREATE TRIGGER qg_feedback_no_delete BEFORE DELETE ON qg_feedback BEGIN SELECT RAISE(ABORT,'Immutable feedback event'); END;
--> statement-breakpoint
CREATE TRIGGER qg_batch_manifest_immutable BEFORE UPDATE OF batch_id,parent_id,manifest_sha,manifest_json,created_at ON qg_batches BEGIN SELECT RAISE(ABORT,'Immutable data manifest'); END;
