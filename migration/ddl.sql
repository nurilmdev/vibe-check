-- public.coffeeshops definition

-- Drop table

-- DROP TABLE public.coffeeshops;

CREATE TABLE public.coffeeshops (
	id uuid DEFAULT gen_random_uuid() NOT NULL,
	"name" varchar(255) NOT NULL,
	address text NULL,
	rating numeric(3, 1) NULL,
	review_count int4 NULL,
	google_maps_url text NOT NULL,
	image_url text NULL,
	latitude numeric(10, 8) NULL,
	longitude numeric(11, 8) NULL,
	vibe_tags _text NULL,
	is_active bool DEFAULT true NULL,
	last_scraped_at timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	created_at timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	sentiment_analytics numeric(3, 2) NULL,
	"location" varchar(50) NULL,
	CONSTRAINT coffeeshops_google_maps_url_key UNIQUE (google_maps_url),
	CONSTRAINT coffeeshops_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_coffeeshops_rating ON public.coffeeshops USING btree (rating DESC);
CREATE INDEX idx_coffeeshops_vibe ON public.coffeeshops USING gin (vibe_tags);


-- public.scrape_queue definition

-- Drop table

-- DROP TABLE public.scrape_queue;

CREATE TABLE public.scrape_queue (
	id uuid DEFAULT gen_random_uuid() NOT NULL,
	area_name text NOT NULL,
	priority int4 DEFAULT 1 NULL,
	status varchar(50) NULL,
	requested_at timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	started_at timestamptz NULL,
	completed_at timestamptz NULL,
	retry_count int4 DEFAULT 0 NULL,
	last_error varchar(100) NULL,
	request_metadata jsonb NULL,
	total_requested int4 DEFAULT 1 NULL,
	CONSTRAINT location_unique UNIQUE (area_name),
	CONSTRAINT scrape_queue_pkey PRIMARY KEY (id)
);


-- public.coffeeshop_reviews definition

-- Drop table

-- DROP TABLE public.coffeeshop_reviews;

CREATE TABLE public.coffeeshop_reviews (
	id uuid DEFAULT gen_random_uuid() NOT NULL,
	coffeeshop_id uuid NOT NULL,
	reviewer_name varchar(255) NULL,
	review_text text NULL,
	reviewer_rating int4 NULL,
	review_time_raw varchar(100) NULL,
	sentiment_label varchar(50) NULL,
	sentiment_score numeric(5, 4) NULL,
	detected_keywords _text NULL,
	created_at timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	review_id varchar(255) NULL,
	ai_sentiment_score numeric(3, 2) NULL,
	ai_vibe_tags _text NULL,
	ai_aspects jsonb NULL,
	ai_summary text NULL,
	is_analyzed bool DEFAULT false NULL,
	CONSTRAINT coffeeshop_reviews_pkey PRIMARY KEY (id),
	CONSTRAINT coffeeshop_reviews_unique UNIQUE (review_id),
	CONSTRAINT coffeeshop_reviews_coffeeshop_id_fkey FOREIGN KEY (coffeeshop_id) REFERENCES public.coffeeshops(id) ON DELETE CASCADE
);
CREATE INDEX idx_reviews_coffeeshop_id ON public.coffeeshop_reviews USING btree (coffeeshop_id);