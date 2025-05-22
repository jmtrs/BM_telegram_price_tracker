-- public.scraped_prices definition
-- Drop table
-- DROP TABLE IF EXISTS public.scraped_prices;

CREATE TABLE public.scraped_prices (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clean_url text NOT NULL,
    price float8 NOT NULL,
    scraped_at timestamp DEFAULT now() NULL,
    product_condition text NULL, -- Added to store product condition
    CONSTRAINT scraped_prices_pkey PRIMARY KEY (id),
    CONSTRAINT scraped_prices_clean_url_key UNIQUE (clean_url)
);

-- public.alerts definition
-- Drop table
-- DROP TABLE IF EXISTS public.alerts;

CREATE TABLE public.alerts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    chat_id int8 NOT NULL,
    full_url text NOT NULL,
    clean_url text NOT NULL,
    target_price float8 NOT NULL,
    last_notified timestamp NULL,
    last_price float8 NULL,
    inserted_at timestamp DEFAULT now() NULL, -- Note: This is updated on price checks too
    CONSTRAINT alerts_pkey PRIMARY KEY (id)
);

CREATE UNIQUE INDEX alerts_chat_id_clean_url_idx ON public.alerts USING btree (chat_id, clean_url);
CREATE INDEX alerts_chat_id_idx ON public.alerts USING btree (chat_id);

-- Optional: Add an index on scraped_at for efficient cleanup
CREATE INDEX scraped_prices_scraped_at_idx ON public.scraped_prices USING btree (scraped_at);

ALTER TABLE public.scraped_prices
ADD COLUMN product_name TEXT NULL,
ADD COLUMN description TEXT NULL,
ADD COLUMN image_url TEXT NULL,
ADD COLUMN color TEXT NULL,
ADD COLUMN storage TEXT NULL,
ADD COLUMN brand_name TEXT NULL;
