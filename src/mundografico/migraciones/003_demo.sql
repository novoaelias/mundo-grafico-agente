-- Datos de demostración: clientes y pedidos ficticios, repartidos en los
-- próximos días hábiles.
--
-- Sin esto la demo no tiene gracia. Es lo que hace que cuando el dueño le
-- pregunte al bot "¿me lo tenés para hoy?" con un pedido grande, el bot le
-- conteste que no puede — porque hay carga de verdad ocupando el taller — y
-- ofrezca una fecha real. Eso es lo que se vende.
--
-- Las fechas se calculan relativas a CURRENT_DATE, así que este archivo
-- sigue teniendo sentido corriera cuando corriera (no hay fechas fijas que
-- envejezcan y queden en el pasado a los tres días de armada la demo).
--
-- Es la única migración pensada para BORRARSE en producción: ejecuta
-- `DELETE FROM mundografico.pedidos WHERE numero LIKE 'DEMO-%'` (y los
-- clientes de demo si hace falta) el día que el negocio arranca de verdad.

SET search_path TO mundografico;

INSERT INTO clientes (conversacion_id, nombre, telefono) VALUES
    ('demo-1', 'Marisa (kiosco)', ''),
    ('demo-2', 'Escuela N°24', ''),
    ('demo-3', 'Ferretería Don Beto', ''),
    ('demo-4', 'Ruta 3 Motos', '')
ON CONFLICT (conversacion_id) DO NOTHING;

-- Pedidos grandes que ya ocupan buena parte de los próximos días hábiles.
-- Los minutos están a mano (no salen de agenda.py) porque son el insumo de
-- prueba, no el resultado: represento "esto ya está comprometido" tal como
-- va a estar comprometido de verdad cuando entren pedidos reales.
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
    ('001', 'demo-1',
     '[{"nombre": "Volantes A6", "cantidad": 1000, "precio_unitario": 12, "subtotal": 12000}]',
     12000, 90, CURRENT_DATE, 'en_proceso', 'a_cobrar'),

    ('002', 'demo-2',
     '[{"nombre": "Lona banner", "cantidad": 8, "precio_unitario": 4000, "subtotal": 32000}]',
     32000, 200, CURRENT_DATE, 'pendiente', 'a_cobrar'),

    ('003', 'demo-3',
     '[{"nombre": "Sello automático", "cantidad": 1, "precio_unitario": 6500, "subtotal": 6500}]',
     6500, 35, CURRENT_DATE + 1, 'pendiente', 'a_cobrar'),

    ('004', 'demo-4',
     '[{"nombre": "Stickers troquelados", "cantidad": 300, "precio_unitario": 39, "subtotal": 11700}]',
     11700, 150, CURRENT_DATE + 1, 'pendiente', 'a_cobrar'),

    ('005', 'demo-1',
     '[{"nombre": "Tarjetas personales", "cantidad": 200, "precio_unitario": 26, "subtotal": 5200}]',
     5200, 90, CURRENT_DATE + 2, 'pendiente', 'a_cobrar')
) AS datos(nro, conv, detalle, total, minutos, fecha, estado, estado_pago)
JOIN clientes c ON c.conversacion_id = datos.conv
ON CONFLICT (numero) DO NOTHING;

-- El reparto por día de cada pedido de demo. Ninguno de estos pedidos pasa
-- los 300 minutos por día por defecto, así que entran enteros en un solo
-- día: la fila de asignacion_agenda es una copia de fecha_promesa/minutos.
INSERT INTO asignacion_agenda (pedido_id, fecha, minutos)
SELECT id, fecha_promesa, minutos_estimados
FROM pedidos
WHERE numero LIKE 'DEMO-%'
ON CONFLICT (pedido_id, fecha) DO NOTHING;
