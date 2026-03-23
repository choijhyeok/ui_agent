-- LFG-8: Snapshot / version labeling support
create table if not exists snapshots (
  id text primary key,
  session_id text not null references sessions(id) on delete cascade,
  label text not null default '',
  workspace_archive bytea not null,
  file_list jsonb not null default '[]'::jsonb,
  patch_record_id text references patch_records(id) on delete set null,
  created_at timestamptz not null default now()
);

create index if not exists idx_snapshots_session_created_at
  on snapshots (session_id, created_at desc);
