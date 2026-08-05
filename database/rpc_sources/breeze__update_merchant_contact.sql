CREATE OR REPLACE FUNCTION public.update_merchant_contact(p_tenant_id uuid, p_merchant_id uuid, p_name text, p_email text, p_phone text, p_set_name boolean, p_set_email boolean, p_set_phone boolean)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare
  v_cur_name text;
  v_old_email text;
  v_cur_phone text;
  v_new_email text;
  v_final_name text;
  v_final_phone text;
begin
  select primary_contact_name, primary_contact_email, primary_contact_phone
    into v_cur_name, v_old_email, v_cur_phone
  from public.merchants
  where id = p_merchant_id and tenant_id = p_tenant_id
  for update;

  if not found then
    raise exception 'merchant not found' using errcode = 'P0002';
  end if;

  -- Merge under the lock: only set fields the caller actually provided.
  v_final_name  := case when p_set_name  then nullif(btrim(coalesce(p_name, '')), '')  else v_cur_name  end;
  v_final_phone := case when p_set_phone then nullif(btrim(coalesce(p_phone, '')), '') else v_cur_phone end;
  v_new_email   := case when p_set_email then nullif(btrim(coalesce(p_email, '')), '') else v_old_email end;

  -- Duplicate email guard (case/whitespace-insensitive, same tenant).
  if p_set_email and v_new_email is not null and exists (
    select 1 from public.merchants
    where tenant_id = p_tenant_id
      and id <> p_merchant_id
      and lower(btrim(primary_contact_email)) = lower(v_new_email)
  ) then
    raise exception 'email_in_use' using errcode = '23505';
  end if;

  update public.merchants
  set primary_contact_name = v_final_name,
      primary_contact_email = lower(v_new_email),
      primary_contact_phone = v_final_phone,
      updated_at = now()
  where id = p_merchant_id and tenant_id = p_tenant_id;

  -- Revoke the OLD email's portal binding only when the email actually changed.
  if p_set_email
     and v_old_email is not null
     and lower(btrim(v_old_email)) is distinct from lower(v_new_email) then
    delete from public.merchant_users
    where merchant_id = p_merchant_id
      and tenant_id = p_tenant_id
      and lower(btrim(email)) = lower(btrim(v_old_email));
  end if;
end;
$function$
