alter table selected_elements
  add column if not exists kind text not null default 'element',
  add column if not exists note text,
  add column if not exists component_hint text;
