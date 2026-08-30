CREATE OR REPLACE FUNCTION public.get_enhanced_dashboard_stats(p_company_id uuid, p_user_id uuid DEFAULT NULL::uuid, p_is_landlord boolean DEFAULT false)
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  SELECT jsonb_build_object(
    'totalProperties', (SELECT count(*) FROM public.properties p WHERE p.company_id = p_company_id AND (NOT p_is_landlord OR p.owner_id = p_user_id)),
    'availableProperties', (SELECT count(*) FROM public.properties p WHERE p.company_id = p_company_id AND p.status = 'available' AND (NOT p_is_landlord OR p.owner_id = p_user_id)),
    'rentedProperties', (SELECT count(*) FROM public.properties p WHERE p.company_id = p_company_id AND p.status = 'rented' AND (NOT p_is_landlord OR p.owner_id = p_user_id)),
    'totalApplications', (SELECT count(*) FROM public.applications a WHERE a.company_id = p_company_id),
    'pendingApplications', (SELECT count(*) FROM public.applications a WHERE a.company_id = p_company_id AND a.status IN ('new', 'pending', 'submitted', 'screening')),
    'totalMonthlyRevenue', (SELECT COALESCE(sum(i.total), 0) FROM public.invoices i WHERE i.company_id = p_company_id AND i.status = 'paid' AND COALESCE(i.paid_at, i.updated_at) >= date_trunc('month', now())),
    'totalLifetimeRevenue', (SELECT COALESCE(sum(i.total), 0) FROM public.invoices i WHERE i.company_id = p_company_id AND i.status = 'paid'),
    'totalMonthlyRent', (SELECT COALESCE(sum(l.rent_amount), 0) FROM public.leases l WHERE l.company_id = p_company_id AND lower(l.status) = 'active'),
    'teamMembers', (SELECT count(*) FROM public.profiles p WHERE p.company_id = p_company_id AND p.is_active),
    'totalAreas', (SELECT count(*) FROM public.areas a WHERE a.company_id = p_company_id),
    'totalBuildings', (SELECT count(*) FROM public.buildings b WHERE b.company_id = p_company_id),
    'openMaintenance', (SELECT count(*) FROM public.maintenance_requests m WHERE m.company_id = p_company_id AND m.status NOT IN ('completed', 'cancelled')),
    'upcomingShowings', (SELECT count(*) FROM public.showings s WHERE s.company_id = p_company_id AND s.scheduled_date >= current_date),
    'occupancyRate', (SELECT CASE WHEN count(*) = 0 THEN 0 ELSE round(100.0 * count(*) FILTER (WHERE p.status = 'rented') / count(*)) END FROM public.properties p WHERE p.company_id = p_company_id),
    'recentActivity', COALESCE((SELECT jsonb_agg(row_to_json(recent)) FROM (SELECT a.id, a.action, a.entity_type, a.details, a.created_at FROM public.activity_log a WHERE a.company_id = p_company_id ORDER BY a.created_at DESC LIMIT 20) recent), '[]'::jsonb)
  )
  WHERE p_company_id = public.get_user_company_id()
     OR auth.role() = 'service_role';
$function$
