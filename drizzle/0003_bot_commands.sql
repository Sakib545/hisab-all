ALTER TABLE `bot_records` ADD COLUMN `content_hash` text DEFAULT '' NOT NULL;
--> statement-breakpoint
CREATE INDEX `bot_records_kind_idx` ON `bot_records` (`bot`,`kind`);
--> statement-breakpoint
CREATE TABLE `bot_commands` (
	`id` text PRIMARY KEY NOT NULL,
	`bot` text NOT NULL,
	`action` text NOT NULL,
	`payload` text DEFAULT '{}' NOT NULL,
	`file_name` text,
	`file_data` text,
	`status` text DEFAULT 'pending' NOT NULL,
	`result` text DEFAULT '' NOT NULL,
	`created_at` text NOT NULL,
	`picked_at` text,
	`done_at` text
);
--> statement-breakpoint
CREATE INDEX `bot_commands_queue_idx` ON `bot_commands` (`bot`,`status`,`created_at`);
