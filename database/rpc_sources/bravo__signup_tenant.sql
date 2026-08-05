CREATE OR REPLACE FUNCTION public.signup_tenant(p_auth_user_id uuid, p_email text, p_full_name text, p_brand text DEFAULT 'OASIS AI'::text, p_slug text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_tenant_id  uuid;
    v_profile_id uuid;
    v_slug       text;
BEGIN
    -- Slug: prefer caller-provided, else derive from email local-part
    v_slug := COALESCE(
        NULLIF(trim(p_slug), ''),
        regexp_replace(lower(split_part(p_email, '@', 1)), '[^a-z0-9-]+', '-', 'g')
    );
    -- Ensure uniqueness
    IF EXISTS (SELECT 1 FROM public.tenants WHERE slug = v_slug) THEN
        v_slug := v_slug || '-' || substr(p_auth_user_id::text, 1, 8);
    END IF;

    INSERT INTO public.tenants (slug, name, plan_tier, purchase_status)
    VALUES (v_slug, p_brand, 'starter', 'pending')
    RETURNING id INTO v_tenant_id;

    INSERT INTO public.user_profiles (
        auth_user_id, email, full_name, display_name, brand, role,
        tenant_id, agents_enabled, primary_agent
    )
    VALUES (
        p_auth_user_id, p_email, p_full_name, split_part(p_full_name, ' ', 1),
        p_brand, 'operator', v_tenant_id,
        ARRAY['bravo']::text[], 'bravo'
    )
    RETURNING id INTO v_profile_id;

    RETURN jsonb_build_object(
        'tenant_id', v_tenant_id,
        'profile_id', v_profile_id,
        'slug', v_slug
    );
END;
$function$
