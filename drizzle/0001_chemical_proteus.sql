CREATE TABLE `parcels` (
	`id` text PRIMARY KEY NOT NULL,
	`order_id` text NOT NULL,
	`date` text NOT NULL,
	`product_id` text NOT NULL,
	`quantity` integer NOT NULL,
	`unit_cost` integer NOT NULL,
	`sale_price` integer NOT NULL,
	`customer` text NOT NULL,
	`phone` text NOT NULL,
	`courier` text NOT NULL,
	`tracking` text NOT NULL,
	`status` text NOT NULL,
	`packaging` integer NOT NULL,
	`courier_fee` integer NOT NULL,
	`return_fee` integer NOT NULL,
	`delivery_charge` integer NOT NULL,
	`other_cost` integer NOT NULL,
	`collected` integer DEFAULT 0 NOT NULL,
	`note` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`product_id`) REFERENCES `products`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `parcels_order_id_unique` ON `parcels` (`order_id`);--> statement-breakpoint
CREATE TABLE `products` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`sku` text NOT NULL,
	`unit_cost` integer NOT NULL,
	`sale_price` integer NOT NULL,
	`stock` integer NOT NULL,
	`archived` integer DEFAULT 0 NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `products_sku_unique` ON `products` (`sku`);--> statement-breakpoint
CREATE TRIGGER parcel_stock_insert BEFORE INSERT ON parcels WHEN NEW.status IN ('sent','delivered') BEGIN SELECT CASE WHEN NEW.quantity + COALESCE((SELECT SUM(quantity) FROM parcels WHERE product_id=NEW.product_id AND status IN ('sent','delivered')),0) > COALESCE((SELECT stock FROM products WHERE id=NEW.product_id),0) THEN RAISE(ABORT,'insufficient_stock') END; END;
--> statement-breakpoint
CREATE TRIGGER parcel_stock_update BEFORE UPDATE ON parcels WHEN NEW.status IN ('sent','delivered') BEGIN SELECT CASE WHEN NEW.quantity + COALESCE((SELECT SUM(quantity) FROM parcels WHERE product_id=NEW.product_id AND status IN ('sent','delivered') AND id<>NEW.id),0) > COALESCE((SELECT stock FROM products WHERE id=NEW.product_id),0) THEN RAISE(ABORT,'insufficient_stock') END; END;
--> statement-breakpoint
CREATE TRIGGER product_stock_update BEFORE UPDATE OF stock ON products BEGIN SELECT CASE WHEN NEW.stock < COALESCE((SELECT SUM(quantity) FROM parcels WHERE product_id=NEW.id AND status IN ('sent','delivered')),0) THEN RAISE(ABORT,'stock_below_allocated') END; END;
