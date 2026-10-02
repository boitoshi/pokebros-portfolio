CREATE TABLE IF NOT EXISTS `latest_pnl` (
	`code` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`currency` text NOT NULL,
	`price_date` text NOT NULL,
	`current_price` real NOT NULL,
	`current_price_foreign` real,
	`exchange_rate` real,
	`month_start_price_native` real,
	`shares` real NOT NULL,
	`cost` real NOT NULL,
	`acquired_price` real NOT NULL,
	`acquired_price_foreign` real,
	`value` real NOT NULL,
	`profit` real NOT NULL,
	`profit_rate` real NOT NULL,
	`updated_at` text NOT NULL
);
