-- Esquema de Mundo Gráfico.
--
-- Vive en su propio schema para no mezclarse con las tablas del checkpointer
-- de LangGraph (que quedan en `public`): así un `DROP SCHEMA mundografico`
-- de prueba nunca se lleva puesta la memoria de las conversaciones, y un
-- `pg_dump --schema=mundografico` alcanza para respaldar todo lo del negocio.

CREATE SCHEMA IF NOT EXISTS mundografico;

SET search_path TO mundografico;

-- ---------------------------------------------------------------------------
-- productos: el catálogo. Lo que el bot cotiza y lo que el panel edita.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS productos (
    id              SERIAL PRIMARY KEY,
    -- UNIQUE también sirve de ancla para el ON CONFLICT del seed
    -- (002_catalogo.sql), así correrlo dos veces no duplica el catálogo.
    nombre          TEXT NOT NULL UNIQUE,
    -- Otras formas de nombrarlo ("banner", "cartel" → lona). La búsqueda
    -- las usa además del nombre. Ver catalogo.py: el matching es en Python,
    -- no acá, así que esto es texto plano y no un array indexado.
    alias           TEXT[] NOT NULL DEFAULT '{}',
    categoria       TEXT NOT NULL DEFAULT 'general',
    unidad          TEXT NOT NULL DEFAULT 'unidad',  -- 'unidad' | 'm2' | 'ciento'
    precio_unitario NUMERIC(12, 2) NOT NULL,
    cantidad_minima NUMERIC(12, 2) NOT NULL DEFAULT 1,
    -- Escalas de precio por cantidad, la más específica gana:
    --   [{"desde": 100, "precio_unitario": 8.5}, {"desde": 500, "precio_unitario": 7}]
    -- Vacío ([]) si el producto no tiene descuento por volumen.
    escalas         JSONB NOT NULL DEFAULT '[]',
    minutos_preparacion INTEGER NOT NULL DEFAULT 0,  -- fijo, una vez por pedido
    minutos_por_unidad  NUMERIC(10, 4) NOT NULL DEFAULT 0,  -- por cada unidad/m2
    -- true = precio de ejemplo cargado por nosotros, todavía no confirmado
    -- por el dueño. El panel lo resalta para que sea fácil encontrar qué
    -- falta reemplazar por el precio real.
    precio_provisorio BOOLEAN NOT NULL DEFAULT TRUE,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_productos_activo ON productos (activo);

-- ---------------------------------------------------------------------------
-- clientes: quién habla. Se identifica por la conversación de Chatwoot.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clientes (
    id              SERIAL PRIMARY KEY,
    -- El thread_id del agente = el id de conversación de Chatwoot. Es la
    -- llave que une "con quién habla el bot" con "de quién es este pedido".
    conversacion_id TEXT NOT NULL UNIQUE,
    contacto_id     TEXT,             -- id de contacto en Chatwoot, si se pudo leer
    nombre          TEXT,
    telefono        TEXT,             -- vacío en canales sin teléfono (Telegram, web)
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- taller: una sola fila con la capacidad y los horarios. No hay UI para
-- crear "otro taller": es una tabla de configuración disfrazada de tabla.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS taller (
    id                  INTEGER PRIMARY KEY DEFAULT 1,
    minutos_por_dia     INTEGER NOT NULL DEFAULT 300,
    -- 1=lunes ... 7=domingo (ISO), para que coincida con date.isoweekday()
    -- de Python sin traducir nada en el medio.
    dias_habiles        INTEGER[] NOT NULL DEFAULT '{1,2,3,4,5,6}',
    -- Pasada esta hora, ya no se promete un trabajo para el día de hoy
    -- aunque sobren minutos: no queda tiempo real de producirlo y entregarlo.
    hora_corte_mismo_dia TIME NOT NULL DEFAULT '15:00',
    feriados            DATE[] NOT NULL DEFAULT '{}',
    CONSTRAINT un_solo_taller CHECK (id = 1)
);

INSERT INTO taller (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- pedidos
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pedidos (
    id              SERIAL PRIMARY KEY,
    -- El número que ve la gente: "MG-0001". El id de arriba es interno.
    numero          TEXT NOT NULL UNIQUE,
    cliente_id      INTEGER NOT NULL REFERENCES clientes (id),
    conversacion_id TEXT NOT NULL,
    -- Detalle de los items cotizados, congelado al momento de crear el
    -- pedido: [{"producto_id": 3, "nombre": "Lona 2x1m", "cantidad": 2,
    --           "precio_unitario": 4500, "subtotal": 9000}]
    -- Se guarda una copia y no solo el producto_id porque el catálogo
    -- puede cambiar de precio después, y el pedido ya cerrado no tiene
    -- que moverse con él.
    detalle         JSONB NOT NULL,
    total           NUMERIC(12, 2) NOT NULL,
    minutos_estimados INTEGER NOT NULL,
    fecha_promesa   DATE NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'pendiente',
    -- pendiente | en_proceso | listo | entregado | cancelado
    estado_pago     TEXT NOT NULL DEFAULT 'a_cobrar',
    -- a_cobrar | señado | pagado
    monto_cobrado   NUMERIC(12, 2),
    notas           TEXT NOT NULL DEFAULT '',
    avisado_listo_en TIMESTAMPTZ,
    -- Si Sheets falló al escribir este pedido, queda marcado para
    -- reintentar: perder la venta del taller nunca puede depender de que
    -- la API de Google esté arriba (ver sheets.py).
    pendiente_sheets BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    entregado_en    TIMESTAMPTZ,
    CONSTRAINT estado_valido CHECK (
        estado IN ('pendiente', 'en_proceso', 'listo', 'entregado', 'cancelado')
    ),
    CONSTRAINT estado_pago_valido CHECK (
        estado_pago IN ('a_cobrar', 'señado', 'pagado')
    )
);

CREATE INDEX IF NOT EXISTS ix_pedidos_estado ON pedidos (estado);
CREATE INDEX IF NOT EXISTS ix_pedidos_fecha_promesa ON pedidos (fecha_promesa);
CREATE INDEX IF NOT EXISTS ix_pedidos_conversacion ON pedidos (conversacion_id);
CREATE INDEX IF NOT EXISTS ix_pedidos_pendiente_sheets
    ON pedidos (pendiente_sheets) WHERE pendiente_sheets;

-- Secuencia propia para el número visible, independiente del id interno:
-- si algún día se borra un pedido de prueba, el número correlativo no
-- muestra un agujero que parezca un pedido perdido.
CREATE SEQUENCE IF NOT EXISTS numero_pedido_seq START 1;

-- ---------------------------------------------------------------------------
-- asignacion_agenda: en qué día(s) se cuentan los minutos de cada pedido.
--
-- Un pedido grande puede no entrar en un solo día: agenda.py lo reparte
-- entre varias fechas. Guardamos ese reparto (y no solo el total) porque es
-- lo que le permite al próximo cálculo de agenda saber, día por día, cuánto
-- hay ya comprometido — sin esto, un pedido de tres días de trabajo pesaría
-- entero sobre la fecha de entrega y dejaría los días anteriores libres en
-- el papel cuando en realidad están ocupados produciéndolo.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asignacion_agenda (
    pedido_id   INTEGER NOT NULL REFERENCES pedidos (id) ON DELETE CASCADE,
    fecha       DATE NOT NULL,
    minutos     INTEGER NOT NULL,
    PRIMARY KEY (pedido_id, fecha)
);

CREATE INDEX IF NOT EXISTS ix_asignacion_agenda_fecha ON asignacion_agenda (fecha);

-- ---------------------------------------------------------------------------
-- eventos_pedido: auditoría. Sirve para debuggear y para el historial que
-- se muestra en el panel ("quién marcó esto como listo y cuándo").
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eventos_pedido (
    id          SERIAL PRIMARY KEY,
    pedido_id   INTEGER NOT NULL REFERENCES pedidos (id) ON DELETE CASCADE,
    tipo        TEXT NOT NULL,  -- 'creado' | 'cambio_estado' | 'cambio_pago' | 'aviso_enviado'
    detalle     JSONB NOT NULL DEFAULT '{}',
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_eventos_pedido_pedido ON eventos_pedido (pedido_id);
