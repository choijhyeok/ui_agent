create table if not exists sessions (
  id text primary key,
  provider jsonb not null,
  design_intent jsonb,
  project_manifest jsonb not null,
  summary text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists messages (
  id text primary key,
  session_id text not null references sessions(id) on delete cascade,
  role text not null,
  body jsonb not null,
  selected_element jsonb,
  created_at timestamptz not null default now()
);

create table if not exists patch_records (
  id text primary key,
  session_id text not null references sessions(id) on delete cascade,
  patch_plan jsonb not null,
  status text not null,
  files jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists runtime_health (
  project_id text primary key,
  status jsonb not null,
  recorded_at timestamptz not null default now()
);
