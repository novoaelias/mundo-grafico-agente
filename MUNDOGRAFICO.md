# Mundo Gráfico

Bot de ventas por WhatsApp/Telegram + panel interno para una gráfica e
imprenta en Laferrere, construido sobre
[basdonax-ai-agentkit](https://github.com/fcori47/basdonax-ai-agentkit).

Este archivo es la puerta de entrada a **lo que agregamos sobre el kit**.
Para las convenciones del kit en sí (por qué el código está en castellano,
por qué el grafo de LangGraph es así, cómo se prueba) la referencia sigue
siendo [`AGENTS.md`](AGENTS.md) — no lo duplicamos acá.

## Estado de la demo en el VPS (25/09/2026)

La aplicación ya corre en Coolify con HTTPS y Postgres. Chatwoot tiene una
bandeja Telegram y otra de simulación interna; el webhook del agente está
activo. Se probó en la bandeja interna el recorrido de cotización, agenda,
pedido, aviso de retiro, entrega/cobro y pausa humana. Las credenciales y
las URLs de acceso están en el archivo local protegido
`<archivo local fuera del repo>`, fuera de Git.

Los precios del catálogo y la política de pago son de ejemplo. La salida del
bot advierte esto de forma obligatoria en la demo. Google Sheets todavía no
está conectado. Ver el estado preciso y los pendientes en
[`AUDITORIA-PLAN.md`](AUDITORIA-PLAN.md).

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

La capa propia vive en `src/mundografico`. Hay dos cambios deliberados en
el kit: `src/agente/herramientas.py` registra las herramientas de la
imprenta y `src/agente/prompts.py` incorpora `prompts/ejemplos.md` si tiene
contenido. Ambos cambios se releen al comparar con `upstream`.

```
src/mundografico/
├── config.py            Config propia (negocio, panel, Sheets) — no toca agente/config.py
├── base_datos.py         Pool de Postgres + runner de migraciones
├── migraciones/          001 esquema · 002 catálogo semilla · 003 demo
├── catalogo.py            Búsqueda de productos y cotización — lógica pura
├── agenda.py              Cuándo puede estar listo un trabajo — lógica pura
├── horario.py             La hora de Laferrere (America/Argentina/Buenos_Aires)
├── demo.py                Reposiciona los pedidos ficticios en días hábiles actuales
├── canal.py               Pide texto si llega un audio/foto/archivo
├── pedidos.py             Capa con Postgres: une catalogo.py + agenda.py
├── chatwoot_api.py        Cliente propio de la API de Chatwoot (contacto, etiquetas, notas)
├── sheets.py              Registro de ventas en Google Sheets
├── herramientas/          Las @tool que ve el modelo
└── panel/                 FastAPI + Jinja2 + HTMX: /panel/pedidos, /catalogo, /taller

servidor_mundografico.py  El entrypoint real (lo que corre el Dockerfile)
prompts/sistema.md        Identidad, circuito de venta, reglas duras
prompts/ejemplos.md       Vacío hasta transcribir los chats reales
preparar_demo.py          Recoloca pedidos ficticios antes de cada presentación
insumos/precios_pdf_para_validar.csv  Precios transcritos del PDF, aún sin unidad confirmada
AUDITORIA-PLAN.md         Cumplimiento punto por punto y bloqueos externos
GUION-DEMO.md              Guion de la demo para el cliente
```

## Poner esto a andar en local

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements-mundografico.txt

copy .env.example .env
# completá al menos: ANTHROPIC_API_KEY, POSTGRES_DSN, PANEL_CLAVE,
# CHATWOOT_URL, CHATWOOT_TOKEN y CHATWOOT_WEBHOOK_TOKEN
```

Necesitás Postgres y Chatwoot accesibles. `servidor_mundografico.py`
aplica el esquema y el catálogo inicial al arrancar. Los pedidos ficticios
solo se cargan con `MG_MODO_DEMO=true`:

```bash
python servidor_mundografico.py
```

Antes de cada presentación, con `MG_MODO_DEMO=true`, ejecutá
`python preparar_demo.py`. Reposiciona solo los pedidos `DEMO-*` en los
próximos tres días hábiles; si la app reinicia en modo demo también los
actualiza. Para atender clientes reales, fijá `MG_MODO_DEMO=false` y usá
solo precios confirmados. Nunca dejes los pedidos ficticios en la base
operativa: eliminá `DEMO-*` al pasar a producción.

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

Si el Postgres real está en el VPS, primero confirmá en Coolify la dirección
y el puerto alcanzables desde el host. Solo entonces abrí un túnel:

```bash
ssh -L 5433:HOST_INTERNO_POSTGRES:PUERTO_POSTGRES usuario@tu-vps
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
- **Pago**: con `POLITICA_PAGO=retiro` el bot crea pedidos `a_cobrar`.
  Con `sena_50` o `adelantado_100` deriva el cierre a una persona:
  hasta integrar una verificación de pago no marca señas ni pagos como
  recibidos. Si cambiás la política, actualizá también la sección 4 de
  `prompts/sistema.md`.
- **Las escalas de precio por cantidad no se editan desde el panel
  todavía** (se ven, no se tocan) — armar esa UI es una pantalla en sí
  misma. Se editan por ahora con una migración o a mano en la base.
- **Pausa del bot**: el panel consulta las etiquetas de Chatwoot al mostrar
  cada pedido. Si ve `humano`, muestra “Bot en pausa” y ofrece “Reanudar”;
  al hacerlo conserva las demás etiquetas. Si Chatwoot no contesta, muestra
  “Estado no disponible”, sin asumir que el bot está activo. Un operador
  debe aplicar la etiqueta `humano` en Chatwoot; contestar desde la bandeja
  por sí solo no activa la pausa.
- **Confirmación de precios**: el catálogo no convierte un precio de
  ejemplo en real por guardar tiempos u otros campos. Hay que marcar
  “Confirmé este precio” explícitamente en la fila.
- **Aviso de pedido listo**: `avisado_listo_en` se guarda únicamente
  después de un envío exitoso a Chatwoot. Si falla, el panel muestra
  “Aviso pendiente” y permite reintentar. Ante una respuesta perdida
  después de que Chatwoot haya aceptado el mensaje, un reintento manual
  podría duplicarlo; revisá la conversación antes de pulsarlo.

## Lo que falta para producción (no para la demo)

- Confirmar la unidad de facturación y si son precios finales en el PDF
  de lonas/vinilos. Hay 32 variantes transcritas (29 con importe y 3 sin
  importe) en `insumos/precios_pdf_para_validar.csv`; todavía no se cargaron como
  precios confirmados. Los demás productos siguen como ejemplo.
- Cargar las capturas de chat y transcribir sus ejemplos de venta en
  `prompts/ejemplos.md`. El agente los toma sin reiniciar.
- WhatsApp oficial (Cloud API de Meta): el aviso de "pedido listo" casi
  siempre cae fuera de la ventana gratuita de 24hs y necesita una
  plantilla de utilidad aprobada por Meta — pedirla con tiempo.
- Un cobro real (Mercado Pago) si se define cobrar seña de verdad, en vez
  de que el bot solo anote lo que la persona dice haber pagado.
