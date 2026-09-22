# Mundo Gráfico

Bot de ventas por WhatsApp/Telegram + panel interno para una gráfica e
imprenta en Laferrere, construido sobre
[basdonax-ai-agentkit](https://github.com/fcori47/basdonax-ai-agentkit).

Este archivo es la puerta de entrada a **lo que agregamos sobre el kit**.
Para las convenciones del kit en sí (por qué el código está en castellano,
por qué el grafo de LangGraph es así, cómo se prueba) la referencia sigue
siendo [`AGENTS.md`](AGENTS.md) — no lo duplicamos acá.

## Qué es esto, en una imagen

```
Telegram / WhatsApp / widget web
              │
              ▼
          Chatwoot  ──────────────────┐
              │                       │ mensajes salientes,
              │ webhook                 aviso "pedido listo",
              ▼                        nota privada, etiqueta
   POST /chatwoot/<token>              │
              │                       │
              ▼                       │
      Agente (LangGraph)  ────────────┘
              │ HERRAMIENTAS
              ▼
   buscar_producto · cotizar · calcular_entrega
   crear_pedido · estado_pedido · pasar_a_humano
              │
              ▼
   Postgres (schema mundografico) ──────► Google Sheets
              ▲
              │
       Panel interno (/panel)
   pedidos · catálogo · taller
```

Un solo proceso, un solo puerto: `servidor_mundografico.py` levanta el
webhook del kit y le suma el panel encima. Un solo Postgres: el kit
guarda la memoria de conversaciones en `public`, todo lo del negocio vive
en el schema `mundografico`.

**Regla de diseño central: el modelo no calcula nada.** No inventa
precios, no suma, no decide una fecha de entrega de memoria. Cotizar y
calcular la entrega son herramientas que leen la base y devuelven números
ya calculados — es lo único que hace que un catálogo de precios real sea
seguro de usar con un LLM.

## Mapa del repo

Todo lo que agregamos vive en archivos nuevos, no se toca el kit — con
**una sola excepción**: `src/agente/herramientas.py`, que ahora importa
`HERRAMIENTAS` desde `mundografico` en vez de definir la del clima. Es
intencional: mantiene el diff contra `upstream` chiquito y estable.

```
src/mundografico/
├── config.py            Config propia (negocio, panel, Sheets) — no toca agente/config.py
├── base_datos.py         Pool de Postgres + runner de migraciones
├── migraciones/          001 esquema · 002 catálogo semilla · 003 demo
├── catalogo.py            Búsqueda de productos y cotización — lógica pura
├── agenda.py              Cuándo puede estar listo un trabajo — lógica pura
├── horario.py             La hora de Laferrere (America/Argentina/Buenos_Aires)
├── pedidos.py             Capa con Postgres: une catalogo.py + agenda.py
├── chatwoot_api.py        Cliente propio de la API de Chatwoot (contacto, etiquetas, notas)
├── sheets.py              Registro de ventas en Google Sheets
├── herramientas/          Las @tool que ve el modelo
└── panel/                 FastAPI + Jinja2 + HTMX: /panel/pedidos, /catalogo, /taller

servidor_mundografico.py  El entrypoint real (lo que corre el Dockerfile)
prompts/sistema.md        Identidad, circuito de venta, reglas duras
GUION-DEMO.md              Guion de la demo para el cliente
```

## Poner esto a andar en local

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements-mundografico.txt

copy .env.example .env
# completá al menos: ANTHROPIC_API_KEY, POSTGRES_DSN, PANEL_CLAVE
```

Necesitás una Postgres a mano (local, Docker, o un túnel SSH al del VPS —
ver más abajo). `servidor_mundografico.py` aplica las migraciones solo al
arrancar, no hace falta correr nada a mano:

```bash
python servidor_mundografico.py
```

Vas a ver en la consola qué migraciones se aplicaron. Con eso arriba:

- `GET /salud` — que el kit conteste.
- `GET /panel/pedidos` — pedís el usuario/clave de `PANEL_USUARIO`/`PANEL_CLAVE`.
- `POST /chatwoot/<CHATWOOT_WEBHOOK_TOKEN>` — a esto le pega Chatwoot.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Todo lo que puede probarse sin una base real, se prueba sin una base
real: `catalogo.py` y `agenda.py` son funciones puras (listas y fechas de
Python, nada de SQL), y las herramientas/el panel se prueban
monkeypatcheando `mundografico.pedidos` a nivel de función — la misma
filosofía de tests del kit (`GenericFakeChatModel`, sin red ni costo).

La única excepción es `test_mundografico_pedidos_integracion.py`, que
prueba SQL y transacciones de verdad (el candado de agenda, el reparto
entre días) y por eso necesita Postgres. Está apagado por defecto:

```bash
# apuntá a una base de DESARROLLO, no a la de producción: el primer paso
# de estos tests borra el schema `mundografico` entero.
MUNDOGRAFICO_TEST_DSN=postgresql://usuario:clave@localhost:5432/mundografico_dev pytest tests/test_mundografico_pedidos_integracion.py
```

Si el Postgres real está en el VPS, un túnel alcanza:

```bash
ssh -L 5433:localhost:5432 usuario@tu-vps
# y en el DSN de arriba: localhost:5433
```

## Deploy en Coolify

1. Conectá este repo como aplicación con Dockerfile (ya apunta a
   `servidor_mundografico.py`).
2. Cargá las variables de entorno de `.env.example` en la configuración
   de la app en Coolify — el `.env` nunca se sube al repo.
3. En Chatwoot: creá el inbox de Telegram (o WhatsApp cuando corresponda)
   y, en Integraciones, un webhook a
   `https://tu-dominio/chatwoot/<CHATWOOT_WEBHOOK_TOKEN>` suscripto solo a
   `message_created`.
4. Con `MODO=produccion` (kit) y `POSTGRES_DSN` (nuestro), las dos partes
   apuntan al mismo Postgres — el kit guarda ahí la memoria de
   conversaciones, `mundografico` su propio schema.

## Decisiones que vale la pena tener presentes

- **Canal de la demo: Telegram *a través de* Chatwoot**, no el bot de
  Telegram directo del kit (`bot_telegram.py`). Así se prueba el mismo
  camino (`Chatwoot → webhook → agente → Chatwoot`) que va a usar
  WhatsApp en producción — migrar es agregar un inbox, no tocar código.
- **Las unidades del catálogo son siempre la unidad física real**
  (tarjetas sueltas, m², hojas), nunca "cientos" ni otro múltiplo:
  `precio_unitario` y los umbrales de `escalas` ya lo tienen incorporado.
  Ver el comentario al principio de `migraciones/002_catalogo.sql`.
- **`POLITICA_PAGO` decide con qué `estado_pago` nace un pedido**
  (`retiro` → a cobrar, `sena_50` → señado, `adelantado_100` → pagado),
  pero no hay una pasarela de pago real detrás todavía: es una foto de lo
  que se acordó en la charla. Cambiarla en el `.env` requiere también
  actualizar la sección 4 de `prompts/sistema.md` a mano — el prompt es
  texto plano, no lee variables de entorno.
- **Las escalas de precio por cantidad no se editan desde el panel
  todavía** (se ven, no se tocan) — armar esa UI es una pantalla en sí
  misma. Se editan por ahora con una migración o a mano en la base.
- **El panel no muestra qué conversaciones están en pausa** (con la
  etiqueta `humano`): eso ya lo resuelve la bandeja del propio Chatwoot,
  filtrando por esa etiqueta — no se duplicó la función acá.

## Lo que falta para producción (no para la demo)

- Cargar el catálogo real (hoy son precios de ejemplo,
  `precio_provisorio = true`) y las capturas de chat para afinar
  `prompts/sistema.md`.
- WhatsApp oficial (Cloud API de Meta): el aviso de "pedido listo" casi
  siempre cae fuera de la ventana gratuita de 24hs y necesita una
  plantilla de utilidad aprobada por Meta — pedirla con tiempo.
- Un cobro real (Mercado Pago) si se define cobrar seña de verdad, en vez
  de que el bot solo anote lo que la persona dice haber pagado.
