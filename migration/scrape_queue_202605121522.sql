INSERT INTO public.scrape_queue (id,area_name,priority,status,requested_at,started_at,completed_at,retry_count,last_error,request_metadata,total_requested) VALUES
	 ('9d1c3e35-1ae7-4eaa-bc58-bf7e64687e67'::uuid,'cihapit',5,'pending','2026-04-17 14:39:43.89659+07','2026-04-17 16:23:27.644463+07',NULL,0,'NoneType' object has no attribute 'goto',NULL,1),
	 ('060097ec-992e-48ad-b48c-3328bf5af63d'::uuid,'Blokm',5,'pending','2026-04-17 15:38:04.654474+07','2026-04-17 16:23:27.843134+07',NULL,0,'NoneType' object has no attribute 'goto',NULL,1),
	 ('238b80cc-b732-45b2-ae37-9a4cfec0984e'::uuid,'bandung',60,'completed','2026-04-17 14:32:43.737953+07','2026-04-17 16:27:02.434374+07','2026-04-17 16:28:16.021019+07',0,'NoneType' object has no attribute 'goto',NULL,6),
	 ('f2f54125-9a73-4ea4-b3e7-d4dc34980808'::uuid,'blokm',30,'completed','2026-04-20 16:52:58.360307+07','2026-04-20 16:53:29.64467+07','2026-04-20 16:54:14.687967+07',0,'upsert_shop_profile() missing 1 required positional argument: ''location''',NULL,3),
	 ('4e4eb791-3b4c-43d4-ae53-a5a2094a5937'::uuid,'blok m',20,'completed','2026-04-20 17:01:26.236106+07','2026-04-20 17:01:38.854867+07','2026-04-20 17:03:17.162915+07',0,NULL,NULL,2),
	 ('4435e852-2053-4ed6-9104-df23f05a5aa2'::uuid,'ciumbuleuit',20,'pending','2026-05-08 14:01:21.778803+07',NULL,NULL,0,NULL,NULL,2),
	 ('391fee4d-f259-45ef-8cdd-25fba851a946'::uuid,'tes',5,'pending','2026-05-08 17:28:00.115442+07',NULL,NULL,0,NULL,NULL,1);
