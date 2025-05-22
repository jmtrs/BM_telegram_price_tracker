-- public.scraped_prices definition
CREATE TABLE public.scraped_prices (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clean_url text NOT NULL,
    price float8 NULL,
    scraped_at timestamp DEFAULT now() NULL,
    product_condition text NULL,
    product_name TEXT NULL,
    description TEXT NULL,
    image_url TEXT NULL,
    color TEXT NULL,
    storage TEXT NULL,
    brand_name TEXT NULL,
    availability TEXT NULL,
    CONSTRAINT scraped_prices_pkey PRIMARY KEY (id),
    CONSTRAINT scraped_prices_clean_url_key UNIQUE (clean_url)
);
CREATE INDEX scraped_prices_scraped_at_idx ON public.scraped_prices USING btree (scraped_at);

-- public.alerts definition
CREATE TABLE public.alerts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    chat_id int8 NOT NULL,
    full_url text NOT NULL,
    clean_url text NOT NULL,
    target_price float8 NOT NULL,
    last_notified timestamp NULL,
    last_price float8 NULL,
    inserted_at timestamp DEFAULT now() NULL,
    CONSTRAINT alerts_pkey PRIMARY KEY (id)
);
CREATE UNIQUE INDEX alerts_chat_id_clean_url_idx ON public.alerts USING btree (chat_id, clean_url);
CREATE INDEX alerts_chat_id_idx ON public.alerts USING btree (chat_id);
