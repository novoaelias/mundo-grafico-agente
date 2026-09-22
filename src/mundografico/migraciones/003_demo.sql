-- Datos de demostración: clientes y pedidos ficticios, repartidos en los
-- próximos días hábiles.
--
-- Sin esto la demo no tiene gracia. Es lo que hace que cuando el dueño le
-- pregunte al bot "¿me lo tenés para hoy?" con un pedido nuevo, el bot le
-- conteste que no puede — porque HOY YA ESTÁ LLENO de verdad (300/300
-- minutos, ver el pedido DEMO-002 más abajo) — y ofrezca la primera fecha
-- real. Ese "no" es lo que se vende: es el dolor de cabeza que hoy el
-- dueño resuelve a mano y de memoria.
--
-- Los números de minutos y precios están calculados con el mismo motor
-- que usa el bot (mundografico.catalogo.cotizar), no puestos a mano: así
-- el catálogo de 002_catalogo.sql y esta demo nunca quedan
-- desincronizados. Si cambiás un precio o un tiempo de armado en el
-- catálogo, estos totales dejan de reflejar la realidad — no rompen nada
-- técnicamente, pero conviene recalcularlos antes de mostrarle esto a un
-- cliente.
--
-- Las fechas se calculan relativas a CURRENT_DATE, así que este archivo
-- sigue teniendo sentido corriera cuando corriera.
--
-- Es la única migración pensada para BORRARSE en producción: ejecutá
-- `DELETE FROM mundografico.pedidos WHERE numero LIKE 'DEMO-%'` (y los
-- clientes de demo si hace falta) el día que el negocio arranca de verdad.

SET search_path TO mundografico;

INSERT INTO clientes (conversacion_id, nombre, telefono) VALUES
    ('demo-1', 'Marisa (kiosco)', ''),
    ('demo-2', 'Escuela N°24', ''),
    ('demo-3', 'Ferretería Don Beto', ''),
    ('demo-4', 'Ruta 3 Motos', '')
ON CONFLICT (conversacion_id) DO NOTHING;

INSERT INTO pedidos
    (numero, cliente_id, conversacion_id, detalle, total, minutos_estimados,
     fecha_promesa, estado, estado_pago, pendiente_sheets)
SELECT
    'DEMO-' || nro,
    c.id,
    c.conversacion_id,
    detalle::jsonb,
    total,
    minutos,
    fecha,
    estado,
    estado_pago,
    FALSE  -- los pedidos de demo no tienen que intentar escribir en Sheets
FROM (VALUES
    -- HOY: una lona de 35 m2 (escala "desde 15" = $3.600/m2) son
    -- exactamente 20 + 8*35 = 300 minutos — el taller entero. Es a
    -- propósito: es el pedido que deja a "hoy" sin lugar para nada más.
    ('002', 'demo-2',
     '[{"nombre": "Lona banner", "cantidad": 35, "precio_unitario": 3600, "subtotal": 126000}]',
     126000, 300, CURRENT_DATE, 'en_proceso', 'a_cobrar'),

    -- MAÑANA: dos pedidos chicos, todavía queda de sobra (85 de 300).
    ('001', 'demo-1',
     '[{"nombre": "Volantes A6", "cantidad": 1000, "precio_unitario": 15, "subtotal": 15000}]',
     15000, 50, CURRENT_DATE + 1, 'pendiente', 'a_cobrar'),

    ('003', 'demo-3',
     '[{"nombre": "Sello automático", "cantidad": 1, "precio_unitario": 6500, "subtotal": 6500}]',
     6500, 35, CURRENT_DATE + 1, 'pendiente', 'a_cobrar'),

    -- PASADO MAÑANA: dos más, la agenda se va aliviando.
    ('004', 'demo-4',
     '[{"nombre": "Stickers troquelados", "cantidad": 300, "precio_unitario": 45, "subtotal": 13500}]',
     13500, 75, CURRENT_DATE + 2, 'pendiente', 'a_cobrar'),

    ('005', 'demo-1',
     '[{"nombre": "Tarjetas personales", "cantidad": 200, "precio_unitario": 35, "subtotal": 7000}]',
     7000, 40, CURRENT_DATE + 2, 'pendiente', 'a_cobrar')
) AS datos(nro, conv, detalle, total, minutos, fecha, estado, estado_pago)
JOIN clientes c ON c.conversacion_id = datos.conv
ON CONFLICT (numero) DO NOTHING;

-- El reparto por día de cada pedido de demo. Ninguno pasa los 300 minutos
-- por día por defecto, así que entran enteros en un solo día: la fila de
-- asignacion_agenda es una copia de fecha_promesa/minutos.
INSERT INTO asignacion_agenda (pedido_id, fecha, minutos)
SELECT id, fecha_promesa, minutos_estimados
FROM pedidos
WHERE numero LIKE 'DEMO-%'
ON CONFLICT (pedido_id, fecha) DO NOTHING;
