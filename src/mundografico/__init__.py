"""Mundo Gráfico: todo lo que no viene con el AgentKit.

Este paquete vive al lado de `agente/` y no lo toca. Todo lo específico del
negocio (catálogo, agenda del taller, pedidos, panel, Sheets) está acá para
que actualizar el kit de arriba (`git pull upstream master`) no choque nunca
con nuestro código.

La única puerta de entrada entre los dos mundos es
`src/agente/herramientas.py`, que importa `HERRAMIENTAS` desde
`mundografico.herramientas` en vez de definir las suyas.
"""
