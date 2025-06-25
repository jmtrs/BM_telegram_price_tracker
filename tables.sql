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

-- public.recommendation_requests: histórico de llamadas al endpoint de recomendaciones
CREATE TABLE public.recommendation_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    recommendation_request_id text NOT NULL,
    widget_id text NOT NULL,
    requested_at timestamp DEFAULT now() NOT NULL,
    response jsonb NOT NULL,
    CONSTRAINT recommendation_requests_pkey PRIMARY KEY (id),
    CONSTRAINT recommendation_requests_request_id_key UNIQUE (recommendation_request_id)
);
CREATE INDEX recommendation_requests_widget_idx ON public.recommendation_requests USING btree (widget_id);

-- public.recommended_products: productos devueltos en cada petición de recomendación
CREATE TABLE public.recommended_products (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    request_id uuid NOT NULL REFERENCES public.recommendation_requests(id) ON DELETE CASCADE,
    product_id text NOT NULL,
    listing_id text,
    title text,
    name text,
    price_amount float8,
    price_currency text,
    raw_data jsonb NOT NULL,
    CONSTRAINT recommended_products_pkey PRIMARY KEY (id)
);
CREATE INDEX recommended_products_request_idx ON public.recommended_products USING btree (request_id);
