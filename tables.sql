-- public.users definition
CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL, -- Internal unique ID for the user in your system
    telegram_chat_id int8 UNIQUE NULL,          -- Telegram chat_id, if user originated from/linked to Telegram
    idp_user_id TEXT UNIQUE NULL,               -- Unique user identifier from the external Identity Provider (e.g., Logto's 'sub' claim)
    username TEXT NULL,                         -- Optional: A display name (e.g., from Telegram or Logto profile)
    created_at timestamp DEFAULT now() NULL,
    is_active BOOLEAN DEFAULT true,
    CONSTRAINT users_pkey PRIMARY KEY (id),
    CONSTRAINT chk_user_identifier CHECK (telegram_chat_id IS NOT NULL OR idp_user_id IS NOT NULL)
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS users_telegram_chat_id_idx ON public.users (telegram_chat_id) WHERE telegram_chat_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS users_idp_user_id_idx ON public.users (idp_user_id) WHERE idp_user_id IS NOT NULL;

-- public.alerts definition
CREATE TABLE public.alerts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    full_url text NOT NULL,
    clean_url text NOT NULL,
    target_price float8 NOT NULL,
    last_notified timestamp NULL,
    last_price float8 NULL,
    inserted_at timestamp DEFAULT now() NULL,
    CONSTRAINT alerts_pkey PRIMARY KEY (id),
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE
);

-- A user should only have one alert per clean_url
CREATE UNIQUE INDEX alerts_user_id_clean_url_idx ON public.alerts (user_id, clean_url);
-- Index for quickly finding all alerts for a specific user
CREATE INDEX alerts_user_id_idx ON public.alerts (user_id);

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

-- Índices adicionales para consultas rápidas
CREATE INDEX IF NOT EXISTS scraped_prices_clean_url_idx ON public.scraped_prices (clean_url);
CREATE INDEX IF NOT EXISTS scraped_prices_scraped_at_idx ON public.scraped_prices (scraped_at);
