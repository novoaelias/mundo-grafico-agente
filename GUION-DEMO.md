# Guion para la demo con el cliente

Cinco minutos, siete pasos. La idea es que el dueño de Mundo Gráfico lo
viva como cliente primero y como dueño después — ahí es donde se vende el
proyecto, no en la explicación técnica.

## Antes de arrancar (una sola vez)

- [ ] El servidor está levantado y `/salud` contesta.
- [ ] El inbox de Telegram está conectado en Chatwoot y el webhook apunta
      bien (mandate un mensaje de prueba vos mismo).
- [ ] Entraste al panel (`/panel/pedidos`) y ves los pedidos de demo.
- [ ] Tenés a mano el usuario y clave del panel para no estar buscándolo
      delante del cliente.
- [ ] Ojeaste `prompts/sistema.md`: si ya tenés datos reales del local
      (horario, dirección), están cargados ahí y en el .env.
- [ ] Si conseguiste la lista de precios real, cargala en el catálogo
      antes de la demo — cotizar con un precio inventado en frente del
      dueño de la imprenta es lo único que puede jugar en contra.

## Los siete pasos

**1. Que te escriba él, no vos.**
Pedile al dueño que le escriba al bot desde su propio celular, como si
fuera un cliente cualquiera. Que sea él quien escribe hace que la demo se
sienta real y no una presentación armada.

**2. Que pregunte un precio.**
Algo de lo que él vende todos los días — una lona, unas tarjetas. El bot
cotiza con los números reales (o los de ejemplo, aclarando que se
reemplazan en un minuto desde el panel).

**3. Que pida algo para hoy mismo, con un pedido grande.**
Acá está el momento fuerte de la demo: la agenda de hoy ya tiene un
pedido que ocupa el taller entero (viene precargado). El bot le va a
decir que no llega para hoy y le va a ofrecer la primera fecha real.
**Esto es lo que se vende**: hoy esa cuenta la hace él, de memoria, bajo
presión, con el cliente esperando.

**4. Que cierre el pedido.**
Confirma cantidad y forma de pago, el bot lo anota y le da un número de
pedido.

**5. Mostrale el panel mientras tanto.**
El pedido que acaba de hacer ya está en `/panel/pedidos`, con el total y
la fecha de entrega. Filtrá por "pendiente" para que lo vea entre los
demás.

**6. Marcá "Listo".**
Apretás el botón delante suyo y a los segundos le suena el celular con
el aviso de que puede pasar a retirar. Ese es el otro dolor de cabeza que
se resuelve solo: hoy ese aviso lo manda él a mano, si se acuerda.

**7. Abrí la hoja de Google.**
La venta ya está ahí, con cliente, total y estado. Es el control de plata
que pidió — mostrarlo cierra el combo completo: vende, organiza y deja
constancia.

## Un par de pruebas extra si da el tiempo

- Escribí vos mismo en el chat de Chatwoot: el bot se calla al instante.
  Es la garantía de que nunca va a hablar por encima de una persona.
- Mandale al bot un pedido de algo que no está en el catálogo: tiene que
  decir que no lo encuentra, no inventar un precio.
- Cambiá un precio desde el panel (pestaña Catálogo) y volvé a cotizar
  ese mismo producto en el chat: el bot ya usa el precio nuevo, sin
  reiniciar nada.

## Después de la demo

Ahí es cuando se habla de precio. Lo que acaba de ver son tres
automatizaciones funcionando juntas (ventas, agenda del taller, control
de plata) sobre una base que ya está armada — lo que falta para
producción es cargar los datos reales (precios, tiempos de producción,
las capturas de chats para afinar el tono de venta) y migrar de Telegram
a WhatsApp de verdad, que es un cambio de configuración en Chatwoot, no
de código.
