-- Catálogo inicial de Mundo Gráfico.
--
-- TODO ESTO ES PROVISORIO (precio_provisorio = TRUE en todas las filas).
-- Son precios plausibles de una gráfica de barrio en 2026, puestos para que
-- la demo tenga algo con qué cotizar. En cuanto llegue la lista real del
-- dueño, se reemplazan desde el panel (pestaña Catálogo) o volviendo a
-- correr un UPDATE — no hace falta tocar código ni reiniciar nada.
--
-- Las escalas de precio son un ejemplo de la forma, no el descuento real:
-- ese también lo define el dueño.

SET search_path TO mundografico;

INSERT INTO productos
    (nombre, alias, categoria, unidad, precio_unitario, cantidad_minima,
     escalas, minutos_preparacion, minutos_por_unidad, precio_provisorio)
VALUES
    -- --- Lonas -------------------------------------------------------------
    ('Lona banner', ARRAY['lona', 'banner', 'cartel', 'gigantografia', 'gigantografía'],
     'lonas', 'm2', 4500, 1,
     '[{"desde": 5, "precio_unitario": 4000}, {"desde": 15, "precio_unitario": 3600}]',
     20, 8, TRUE),

    ('Lona con ojales', ARRAY['lona con ojales', 'banner con ojales'],
     'lonas', 'm2', 5200, 1,
     '[{"desde": 5, "precio_unitario": 4700}]',
     25, 9, TRUE),

    -- --- Tarjetería ----------------------------------------------------------
    ('Tarjetas personales', ARRAY['tarjetas', 'tarjetas personales', 'business cards'],
     'tarjeteria', 'ciento', 3500, 1,
     '[{"desde": 5, "precio_unitario": 3000}, {"desde": 10, "precio_unitario": 2600}]',
     30, 2, TRUE),

    -- --- Volantes y folletos --------------------------------------------------
    ('Volantes A6', ARRAY['volantes', 'flyers', 'volante'],
     'volantes', 'ciento', 1800, 1,
     '[{"desde": 5, "precio_unitario": 1500}, {"desde": 20, "precio_unitario": 1200}]',
     20, 0.6, TRUE),

    ('Folletos A5 dípticos', ARRAY['folletos', 'dipticos', 'dípticos', 'triptico', 'tríptico'],
     'volantes', 'ciento', 4200, 1,
     '[{"desde": 5, "precio_unitario": 3800}]',
     25, 1.2, TRUE),

    -- --- Sellos ---------------------------------------------------------------
    ('Sello automático', ARRAY['sello', 'sellos', 'sello automatico', 'sello automático'],
     'sellos', 'unidad', 6500, 1, '[]', 15, 20, TRUE),

    -- --- Stickers ---------------------------------------------------------------
    ('Stickers troquelados', ARRAY['stickers', 'calcomanias', 'calcomanías', 'adhesivos'],
     'stickers', 'ciento', 5000, 1,
     '[{"desde": 3, "precio_unitario": 4500}, {"desde": 10, "precio_unitario": 3900}]',
     30, 3, TRUE),

    -- --- Impresiones sueltas ------------------------------------------------
    ('Impresión B/N A4', ARRAY['impresion blanco y negro', 'fotocopia', 'copia', 'impresion'],
     'impresiones', 'unidad', 80, 1, '[]', 2, 0.15, TRUE),

    ('Impresión color A4', ARRAY['impresion color', 'copia color'],
     'impresiones', 'unidad', 250, 1, '[]', 2, 0.2, TRUE),

    -- --- Plotteo / vinilo ----------------------------------------------------
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
