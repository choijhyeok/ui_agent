create table if not exists session_memory (
  session_id text primary key references sessions(id) on delete cascade,
  summary text not null default '',
  structured_memory jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists selected_elements (
  id text primary key,
  session_id text not null references sessions(id) on delete cascade,
  selector text not null,
  dom_path jsonb not null,
  text_snippet text,
  bounds jsonb not null,
  source_hint jsonb,
  captured_at timestamptz not null
);

alter table messages
  add column if not exists selected_element_id text references selected_elements(id) on delete set null;

alter table patch_records
  add column if not exists plan_id text,
  add column if not exists summary text not null default '',
  add column if not exists files_changed jsonb;

update patch_records
set files_changed = files
where files_changed is null;

create index if not exists idx_messages_session_created_at on messages (session_id, created_at);
create index if not exists idx_selected_elements_session_captured_at on selected_elements (session_id, captured_at);
create index if not exists idx_patch_records_session_created_at on patch_records (session_id, created_at);
