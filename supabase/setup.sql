-- Meal Planner cloud-sync schema.
-- Run this once in the SQL editor of a DEDICATED Supabase project
-- (Dashboard -> SQL Editor -> paste -> Run). Do not run it in a database
-- that holds anything sensitive: these tables are readable/writable by
-- anyone holding the project's anon key (that's what makes shareable
-- family vote links work without accounts).

create table if not exists meal_recipes (
  slug        text primary key,
  name        text not null,
  data        jsonb not null,
  updated_at  timestamptz not null default now()
);

create table if not exists meal_votes (
  id          bigint generated always as identity primary key,
  recipe_slug text not null,
  voter       text not null,
  vote        smallint not null check (vote in (-1, 1)),
  created_at  timestamptz not null default now(),
  unique (recipe_slug, voter)
);

create table if not exists meal_pantry (
  key         text primary key,  -- UPC when known, else slugified item name
  data        jsonb not null,
  updated_at  timestamptz not null default now()
);

alter table meal_recipes enable row level security;
alter table meal_votes   enable row level security;
alter table meal_pantry  enable row level security;

-- Anyone with the anon key may read and write. Household-scoped by
-- obscurity of the project URL + key, which is the deliberate tradeoff
-- for account-free family voting.
drop policy if exists meal_recipes_all on meal_recipes;
create policy meal_recipes_all on meal_recipes
  for all to anon using (true) with check (true);

drop policy if exists meal_votes_all on meal_votes;
create policy meal_votes_all on meal_votes
  for all to anon using (true) with check (true);

drop policy if exists meal_pantry_all on meal_pantry;
create policy meal_pantry_all on meal_pantry
  for all to anon using (true) with check (true);
