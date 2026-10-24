CREATE TABLE `bots` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`label` text NOT NULL,
	`kind` text DEFAULT 'general' NOT NULL,
	`token_hash` text,
	`token_hint` text,
	`created_at` text NOT NULL,
	`last_seen_at` text,
	`last_error` text
);
--> statement-breakpoint
CREATE UNIQUE INDEX `bots_name_unique` ON `bots` (`name`);
--> statement-breakpoint
CREATE UNIQUE INDEX `bots_token_hash_unique` ON `bots` (`token_hash`);
--> statement-breakpoint
CREATE TABLE `bot_records` (
	`id` text PRIMARY KEY NOT NULL,
	`bot` text NOT NULL,
	`external_id` text NOT NULL,
	`kind` text NOT NULL,
	`title` text NOT NULL,
	`amount` integer,
	`status` text DEFAULT '' NOT NULL,
	`data` text DEFAULT '{}' NOT NULL,
	`occurred_at` text NOT NULL,
	`received_at` text NOT NULL,
	`entry_id` text
);
--> statement-breakpoint
CREATE UNIQUE INDEX `bot_records_bot_ext_unique` ON `bot_records` (`bot`,`external_id`);
--> statement-breakpoint
CREATE INDEX `bot_records_time_idx` ON `bot_records` (`occurred_at`);
--> statement-breakpoint
CREATE INDEX `bot_records_bot_time_idx` ON `bot_records` (`bot`,`occurred_at`);
