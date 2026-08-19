begin;

create table if not exists public.website_deals (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  lead_id uuid not null references public.tenant_records(id) on delete cascade,
  rep_user_id uuid not null,
  founder_user_id uuid not null,
  package_id text not null check (package_id in ('essential','growth','authority')),
  automation_ids text[] not null default '{}',
  currency text not null check (currency in ('CAD','USD')),
  setup_amount numeric(12,2) not null check (setup_amount >= 0),
  monthly_amount numeric(12,2) not null check (monthly_amount >= 0),
  proposal_status text not null default 'not_started' check (proposal_status in ('not_started','draft','sent','accepted','declined')),
  status text not null default 'open' check (status in ('open','won','lost','refunded')),
  payment_reference text,
  loss_reason text,
  closed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, lead_id),
  unique (tenant_id, id)
);

create table if not exists public.website_sales_commissions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  deal_id uuid not null,
  rep_user_id uuid not null,
  payment_reference text not null,
  entry_type text not null default 'accrual' check (entry_type in ('accrual','refund_offset','manual_adjustment')),
  collected_setup_amount numeric(12,2) not null,
  rate numeric(6,5) not null check (rate >= 0 and rate <= 1),
  amount numeric(12,2) not null,
  status text not null default 'accrued' check (status in ('accrued','approved','paid','offset','voided')),
  approved_by uuid,
  approved_at timestamptz,
  paid_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, payment_reference, entry_type),
  foreign key (tenant_id, deal_id) references public.website_deals(tenant_id, id) on delete cascade
);

create table if not exists public.website_onboarding (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  deal_id uuid not null,
  lead_id uuid not null references public.tenant_records(id) on delete cascade,
  fulfillment_owner_id uuid,
  status text not null default 'assets_needed' check (status in ('assets_needed','ready','in_build','client_review','launched','blocked')),
  target_launch_date date,
  intake jsonb not null default '{}'::jsonb,
  qa jsonb not null default '{}'::jsonb,
  client_approved_at timestamptz,
  launched_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, deal_id),
  foreign key (tenant_id, deal_id) references public.website_deals(tenant_id, id) on delete cascade
);

create index if not exists website_deals_pipeline_idx on public.website_deals (tenant_id, status, updated_at desc);
create index if not exists website_commissions_rep_idx on public.website_sales_commissions (tenant_id, rep_user_id, status, created_at desc);
create index if not exists website_onboarding_board_idx on public.website_onboarding (tenant_id, status, updated_at desc);
create unique index if not exists website_sales_interaction_request_uidx
  on public.lead_interactions (tenant_id, ((metadata->>'request_id')))
  where agent_source='website_sales_pipeline' and metadata->>'request_id' is not null;

alter table public.website_deals enable row level security;
alter table public.website_deals force row level security;
alter table public.website_sales_commissions enable row level security;
alter table public.website_sales_commissions force row level security;
alter table public.website_onboarding enable row level security;
alter table public.website_onboarding force row level security;
create policy website_deals_service_role on public.website_deals for all to service_role using (true) with check (true);
create policy website_commissions_service_role on public.website_sales_commissions for all to service_role using (true) with check (true);
create policy website_onboarding_service_role on public.website_onboarding for all to service_role using (true) with check (true);

create or replace function public.close_website_deal(
  p_tenant_id uuid, p_lead_id uuid, p_rep_user_id uuid, p_founder_user_id uuid,
  p_package_id text, p_automation_ids text[], p_currency text,
  p_setup_amount numeric, p_monthly_amount numeric, p_payment_reference text
) returns jsonb language plpgsql security definer set search_path = public as $$
declare v_deal website_deals; v_rate numeric; v_commission website_sales_commissions; v_lead_data jsonb; v_frozen_rep text;
begin
  if auth.role() is distinct from 'service_role' then
    raise exception 'service_role_required' using errcode='42501';
  end if;
  select data into v_lead_data from tenant_records where id=p_lead_id and tenant_id=p_tenant_id and entity_type='lead' for update;
  if v_lead_data is null then
    raise exception 'lead_not_found_or_wrong_tenant' using errcode='02000';
  end if;
  if not exists (select 1 from user_profiles where tenant_id=p_tenant_id and auth_user_id=p_founder_user_id and (is_owner=true or team_role in ('owner','admin'))) then
    raise exception 'founder_not_authorized_for_tenant' using errcode='42501';
  end if;
  if not exists (select 1 from user_profiles where tenant_id=p_tenant_id and auth_user_id=p_rep_user_id and team_role='agent') then
    raise exception 'rep_not_agent_for_tenant' using errcode='42501';
  end if;
  v_frozen_rep := coalesce(v_lead_data->>'attributed_rep_user_id', v_lead_data->>'assigned_to');
  if v_frozen_rep is null or v_frozen_rep <> p_rep_user_id::text then
    raise exception 'rep_does_not_match_frozen_attribution' using errcode='42501';
  end if;
  if p_setup_amount < 2000 then raise exception 'collected setup below commission floor' using errcode='22023'; end if;
  v_rate := case when p_setup_amount >= 5000 then .15 when p_setup_amount >= 3500 then .125 else .10 end;
  select * into v_deal from website_deals where tenant_id=p_tenant_id and lead_id=p_lead_id for update;
  if v_deal.id is not null then
    if v_deal.status <> 'won' or v_deal.rep_user_id <> p_rep_user_id or v_deal.founder_user_id <> p_founder_user_id or v_deal.package_id <> p_package_id or v_deal.automation_ids <> coalesce(p_automation_ids,'{}') or v_deal.currency <> p_currency or v_deal.setup_amount <> p_setup_amount or v_deal.monthly_amount <> p_monthly_amount or v_deal.payment_reference <> p_payment_reference then
      raise exception 'deal_already_closed_mismatch' using errcode='23505';
    end if;
  else
    insert into website_deals (tenant_id,lead_id,rep_user_id,founder_user_id,package_id,automation_ids,currency,setup_amount,monthly_amount,proposal_status,status,payment_reference,closed_at)
    values (p_tenant_id,p_lead_id,p_rep_user_id,p_founder_user_id,p_package_id,coalesce(p_automation_ids,'{}'),p_currency,p_setup_amount,p_monthly_amount,'accepted','won',p_payment_reference,now())
    returning * into v_deal;
  end if;
  insert into website_sales_commissions (tenant_id,deal_id,rep_user_id,payment_reference,collected_setup_amount,rate,amount)
  values (p_tenant_id,v_deal.id,v_deal.rep_user_id,p_payment_reference,p_setup_amount,v_rate,round(p_setup_amount*v_rate,2))
  on conflict (tenant_id,payment_reference,entry_type) do update set updated_at=website_sales_commissions.updated_at
  where website_sales_commissions.deal_id = excluded.deal_id
  returning * into v_commission;
  if v_commission.id is null then
    raise exception 'payment_reference_already_used_by_another_deal' using errcode='23505';
  end if;
  insert into website_onboarding (tenant_id,deal_id,lead_id) values (p_tenant_id,v_deal.id,p_lead_id)
  on conflict (tenant_id,deal_id) do nothing;
  perform patch_tenant_record_data(p_lead_id,p_tenant_id,jsonb_build_object('stage','onboarding','closed_by',p_founder_user_id,'collected_setup_amount',p_setup_amount,'quoted_monthly_amount',p_monthly_amount));
  return jsonb_build_object('deal_id',v_deal.id,'commission_id',v_commission.id,'commission_amount',v_commission.amount);
end $$;

commit;
