# Guion para la demo con el cliente

Cinco minutos, siete pasos. La idea es que el dueño de Mundo Gráfico lo
viva como cliente primero y como dueño después — ahí es donde se vende el
proyecto, no en la explicación técnica.

## Antes de arrancar (una sola vez)

- [x] El servidor está levantado y `/salud` contesta por HTTPS.
- [x] El inbox de Telegram está conectado en Chatwoot y el webhook apunta
      al agente. El recorrido interno Chatwoot → agente → Chatwoot ya se probó.
- [ ] Mandate un mensaje desde tu propio Telegram para verificar también
      la entrega al celular antes de mostrárselo al cliente.
- [x] El panel (`/panel/pedidos`) muestra los pedidos de demo.
- [ ] Antes de la presentación, con `MG_MODO_DEMO=true`, ejecutá
      `python preparar_demo.py` desde la terminal de la aplicación en Coolify
      (o reiniciá la aplicación). `DEMO-002` debe ocupar el primer día hábil.
- [ ] Tenés a mano el usuario y clave del panel para no estar buscándolo
      delante del cliente.
- [ ] Ojeaste `prompts/sistema.md`: si ya tenés datos reales del local
      (horario, dirección), están cargados ahí y en el .env.
- [ ] Los precios del PDF tienen unidad y condición comercial confirmadas.
      Si todavía no, usá los precios de demostración y decí claramente que
      el dueño debe validarlos antes de atender clientes reales.
- [x] Sheets está conectado a la hoja «Mundo Gráfico — DEMO» y la cuenta de
      servicio tiene permiso de editor. `MG-0001` y `MG-0002` ya se verificaron
      sin filas duplicadas.

## Los siete pasos

**1. Que te escriba él, no vos.**
Pedile al dueño que le escriba al bot desde su propio celular, como si
fuera un cliente cualquiera. Que sea él quien escribe hace que la demo se
sienta real y no una presentación armada.

**2. Que pregunte un precio.**
Algo de lo que él vende todos los días — una lona, unas tarjetas. El bot
cotiza con números confirmados, o con los de ejemplo señalados como
demostración. No presentes el importe provisorio como precio de venta.

**3. Que pida algo para hoy mismo, con un pedido grande.**
Acá está el momento fuerte de la demo: la agenda de hoy ya tiene un
pedido que ocupa el taller entero (viene precargado). El bot le va a
decir que no llega para hoy y le va a ofrecer la primera fecha real.
Si hoy es feriado, domingo o ya pasó la hora de corte, la explicación será
distinta; hacé este paso en horario hábil para mostrar la carga del taller.
**Esto es lo que se vende**: hoy esa cuenta la hace él, de memoria, bajo
presión, con el cliente esperando.

**4. Que cierre el pedido.**
Confirma cantidad y forma de pago, el bot lo anota y le da un número de
pedido. Con `MG_MODO_DEMO=true` queda rotulado como pedido de demostración.

**5. Mostrale el panel mientras tanto.**
El pedido que acaba de hacer ya está en `/panel/pedidos`, con el total y
la fecha de entrega. Filtrá por "pendiente" para que lo vea entre los
demás.

**6. Marcá "Listo".**
Apretás el botón delante suyo y a los segundos le suena el celular con
el aviso de que puede pasar a retirar. Ese es el otro dolor de cabeza que
se resuelve solo: hoy ese aviso lo manda él a mano, si se acuerda.

**7. Abrí la hoja de Google.**
En la pestaña `Ventas` de «Mundo Gráfico — DEMO», buscá el número del pedido:
debe haber una sola fila con cliente, total y estado. Marcá «Entregado» en el
panel, registrá el monto cobrado y volvé a la hoja: esa misma fila debe decir
`entregado` y `pagado`, con el importe en «Monto cobrado». Esta hoja contiene
ventas ficticias; creá una hoja separada antes de registrar ventas reales.

## Un par de pruebas extra si da el tiempo

- Agregá la etiqueta `humano` a la conversación en Chatwoot y escribí
  desde la bandeja: el bot debe callarse ante los siguientes mensajes del
  cliente. Verificá en el panel “Bot en pausa” y probá “Reanudar” después
  de que termines tu intervención. Escribir como operador, sin poner la
  etiqueta, no pausa automáticamente al bot.
- Mandale al bot un pedido de algo que no está en el catálogo: tiene que
  decir que no lo encuentra, no inventar un precio.
- Cambiá un precio desde el panel (pestaña Catálogo) y volvé a cotizar
  ese mismo producto en el chat: el bot ya usa el precio nuevo, sin
  reiniciar nada. Si era un precio de ejemplo, confirmalo con el checkbox.

## Después de la demo

Ahí es cuando se habla de precio. Lo que acaba de ver es la venta, la agenda
del taller, el aviso de retiro y el registro en Sheets funcionando juntos.
Para producción faltan los datos reales (precios, tiempos de producción,
dirección y horarios, política de pago y capturas de chats), una hoja separada
para ventas reales y conectar WhatsApp en Chatwoot.
