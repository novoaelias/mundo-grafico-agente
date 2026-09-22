-- Catálogo inicial de Mundo Gráfico.
--
-- TODO ESTO ES PROVISORIO (precio_provisorio = TRUE en todas las filas).
-- Son precios plausibles de una gráfica de barrio en 2026, puestos para que
-- la demo tenga algo con qué cotizar. En cuanto llegue la lista real del
-- dueño, se reemplazan desde el panel (pestaña Catálogo) o volviendo a
-- correr un UPDATE — no hace falta tocar código ni reiniciar nada.
--
-- Convención importante, la misma que usa catalogo.py: `cantidad` es
-- SIEMPRE la unidad física real que dice la persona (tarjetas sueltas,
-- hojas, metros cuadrados) — nunca "cientos" ni ningún otro múltiplo. Por
-- eso `precio_unitario` de las tarjetas es el precio de UNA tarjeta, y las
-- escalas de cantidad están en unidades sueltas (`desde: 500` = 500
-- tarjetas, no 5 cientos). Mezclar esa convención sería la forma más común
-- de que el bot cotice diez veces mal sin que se note en una lectura
-- rápida del código.

SET search_path TO mundografico;

INSERT INTO productos
    (nombre, alias, categoria, unidad, precio_unitario, cantidad_minima,
     escalas, minutos_preparacion, minutos_por_unidad, precio_provisorio)
VALUES
    -- --- Lonas (unidad = m2) -------------------------------------------------
    ('Lona banner', ARRAY['lona', 'banner', 'cartel', 'gigantografia', 'gigantografía'],
     'lonas', 'm2', 4500, 1,
     '[{"desde": 5, "precio_unitario": 4000}, {"desde": 15, "precio_unitario": 3600}]',
     20, 8, TRUE),

    ('Lona con ojales', ARRAY['lona con ojales', 'banner con ojales'],
     'lonas', 'm2', 5200, 1,
     '[{"desde": 5, "precio_unitario": 4700}]',
     25, 9, TRUE),

    -- --- Tarjetería y volantes (unidad = unidad suelta) -----------------------
    -- Mínimo 100: no tiene sentido de producción imprimir menos que eso.
    ('Tarjetas personales', ARRAY['tarjetas', 'tarjetas personales', 'business cards'],
     'tarjeteria', 'unidad', 35, 100,
     '[{"desde": 500, "precio_unitario": 30}, {"desde": 1000, "precio_unitario": 26}]',
     30, 0.05, TRUE),

    ('Volantes A6', ARRAY['volantes', 'flyers', 'volante'],
     'volantes', 'unidad', 18, 100,
     '[{"desde": 500, "precio_unitario": 15}, {"desde": 2000, "precio_unitario": 12}]',
     20, 0.03, TRUE),

    ('Folletos A5 dípticos', ARRAY['folletos', 'dipticos', 'dípticos', 'triptico', 'tríptico'],
     'volantes', 'unidad', 42, 100,
     '[{"desde": 500, "precio_unitario": 38}]',
     25, 0.08, TRUE),

    -- --- Sellos ---------------------------------------------------------------
    ('Sello automático', ARRAY['sello', 'sellos', 'sello automatico', 'sello automático'],
     'sellos', 'unidad', 6500, 1, '[]', 15, 20, TRUE),

    -- --- Stickers ---------------------------------------------------------------
    ('Stickers troquelados', ARRAY['stickers', 'calcomanias', 'calcomanías', 'adhesivos'],
     'stickers', 'unidad', 50, 100,
     '[{"desde": 300, "precio_unitario": 45}, {"desde": 1000, "precio_unitario": 39}]',
     30, 0.15, TRUE),

    -- --- Impresiones sueltas (sin mínimo: se pide de a una) -------------------
    ('Impresión B/N A4', ARRAY['impresion blanco y negro', 'fotocopia', 'copia', 'impresion'],
     'impresiones', 'unidad', 80, 1, '[]', 2, 0.15, TRUE),

    ('Impresión color A4', ARRAY['impresion color', 'copia color'],
     'impresiones', 'unidad', 250, 1, '[]', 2, 0.2, TRUE),

    -- --- Plotteo / vinilo (unidad = m2) ---------------------------------------
    ('Plotteo de corte (vinilo)', ARRAY['plotteo', 'vinilo', 'calado', 'letras en vinilo'],
     'plotteo', 'm2', 6000, 1,
     '[{"desde": 3, "precio_unitario": 5400}]',
     30, 15, TRUE),

    -- --- Terminaciones ---------------------------------------------------------
    ('Anillado', ARRAY['anillado', 'espiralado'],
     'terminaciones', 'unidad', 1200, 1, '[]', 5, 4, TRUE),

    ('Plastificado A4', ARRAY['plastificado', 'laminado'],
     'terminaciones', 'unidad', 900, 1, '[]', 3, 2, TRUE)
ON CONFLICT (nombre) DO NOTHING;
