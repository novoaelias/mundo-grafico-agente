"""Buscar productos y cotizar. Funciones puras: no tocan la base de datos.

Por qué separado así: el catálogo de una gráfica de barrio tiene unas
pocas decenas de productos, así que no hace falta —ni conviene— resolver la
búsqueda con `unaccent` + `pg_trgm` del lado de Postgres (dos extensiones
más para instalar y mantener en el servidor). Alcanza con traer los
productos activos a Python una vez y buscar ahí con `difflib`, sacando antes
los acentos. Así además esta lógica se prueba con listas de diccionarios
comunes, sin levantar Postgres — que es exactamente lo que pide `AGENTS.md`
del proyecto: nada de tests que salgan a la red o a una base para probar una
cuenta.

Quien haga de puente con la base (`pedidos.py`) le pasa a estas funciones
los productos ya leídos de la tabla `productos`, y estas funciones nunca
inventan un precio que no venga en esa lista — es la regla central de todo
el proyecto: el modelo (y el código) no calculan de memoria, calculan con
los datos de verdad.
"""

from __future__ import annotations

import unicodedata
import math
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# Por debajo de esto, una coincidencia de nombre es más ruido que ayuda:
# mejor decir "no lo encontré" que ofrecer un producto que no tiene nada
# que ver con lo que pidieron.
UMBRAL_DE_PARECIDO = 0.55


def formato_dinero(monto: float) -> str:
    """"$12.500", con punto de miles y sin decimales — así se habla la
    plata en una charla de WhatsApp, no como la devuelve Python."""
    return f"${monto:,.0f}".replace(",", ".")


@dataclass
class ItemCotizado:
    producto_id: int
    nombre: str
    cantidad: float
    unidad: str
    precio_unitario: float
    subtotal: float
    minutos: int
    # Si la cantidad no llegó a la mínima del producto, se avisa: no se
    # cobra de más en silencio, se explica por qué el total no es el que
    # esperaba quien pregunta.
    aviso: str = ""
    precio_provisorio: bool = False


@dataclass
class Cotizacion:
    items: list[ItemCotizado] = field(default_factory=list)
    total: float = 0.0
    minutos_totales: int = 0
    no_encontrados: list[str] = field(default_factory=list)
    ambiguos: list[str] = field(default_factory=list)
    invalidos: list[str] = field(default_factory=list)

    @property
    def completa(self) -> bool:
        return bool(self.items) and not (self.no_encontrados or self.ambiguos or self.invalidos)

    def texto(self) -> str:
        """La cotización redactada para que el modelo se la pase a la persona."""
        if not self.items and not (self.no_encontrados or self.ambiguos or self.invalidos):
            return "No hay nada para cotizar."

        lineas = []
        for item in self.items:
            lineas.append(
                f"- {item.cantidad:g} {item.unidad} de {item.nombre}: "
                f"{formato_dinero(item.subtotal)}"
                + (f" ({item.aviso})" if item.aviso else "")
            )

        for nombre in self.no_encontrados:
            lineas.append(f"- No encontré '{nombre}' en el catálogo.")

        for nombre in self.ambiguos:
            lineas.append(f"- '{nombre}' puede referirse a varios productos; pedí una aclaración.")

        for nombre in self.invalidos:
            lineas.append(f"- Falta un producto o una cantidad válida en '{nombre}'.")

        if self.items:
            lineas.append(f"Total: {formato_dinero(self.total)}")
            if any(item.precio_provisorio for item in self.items):
                lineas.append("ATENCIÓN: hay precios de demostración sin confirmar con el local.")

        if not self.completa:
            lineas.append("Esta cotización está incompleta; no confirmes un pedido todavía.")

        return "\n".join(lineas)


def normalizar(texto: str) -> str:
    """Minúsculas y sin acentos, para que "señalización" y "senalizacion"
    empaten igual. `NFKD` separa la tilde de la letra y la descomposición
    se descarta quedándonos solo con los caracteres ASCII."""
    sin_acentos = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in sin_acentos if not unicodedata.combining(c)).lower().strip()


def buscar_producto(
    productos: list[dict], consulta: str, maximo: int = 3
) -> list[dict]:
    """Los productos activos que más se parecen a `consulta`.

    Compara contra el nombre y contra cada alias, y se queda con el mejor
    puntaje de los dos. Devuelve como mucho `maximo` resultados, del más
    parecido al menos, y ninguno por debajo del umbral.
    """
    consulta_norm = normalizar(consulta)
    if not consulta_norm:
        return []

    puntuados = []
    for producto in productos:
        if not producto.get("activo", True):
            continue

        puntaje = _puntaje_producto(consulta_norm, producto)
        if puntaje >= UMBRAL_DE_PARECIDO:
            puntuados.append((puntaje, producto))

    puntuados.sort(key=lambda par: par[0], reverse=True)
    return [producto for _, producto in puntuados[:maximo]]


def _puntaje_producto(consulta_norm: str, producto: dict) -> float:
    candidatos = [producto["nombre"], *(producto.get("alias") or [])]
    return max(_parecido(consulta_norm, normalizar(c)) for c in candidatos)


def _parecido(a: str, b: str) -> float:
    """Qué tan parecidas son dos cadenas ya normalizadas, entre 0 y 1.

    Además del ratio completo, premiamos que una esté CONTENIDA en la otra
    ("lona" adentro de "lona banner"): es el caso más común —piden con una
    sola palabra— y con el ratio solo, una palabra corta contra un nombre
    largo puntúa bajo aunque sea exactamente lo que están buscando.
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 2.0
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def cotizar(productos: list[dict], items: list[dict]) -> Cotizacion:
    """Arma la cotización a partir de una lista de pedidos crudos.

    `items` es lo que pide quien cotiza, ya sea la persona por el chat o el
    modelo armando los argumentos de la herramienta:
        [{"producto": "lona banner", "cantidad": 3}, ...]

    Por cada uno se busca el producto más parecido (si no hay ninguno por
    encima del umbral, se informa como no encontrado en vez de adivinar) y
    se aplica la escala de precio que corresponda a la cantidad pedida.
    """
    resultado = Cotizacion()

    for pedido in items:
        nombre_pedido = str(pedido.get("producto") or "").strip()
        try:
            cantidad = float(pedido.get("cantidad") or 0)
        except (TypeError, ValueError):
            cantidad = 0

        if not nombre_pedido or not math.isfinite(cantidad) or cantidad <= 0:
            resultado.invalidos.append(nombre_pedido or "producto sin nombre")
            continue

        encontrados = buscar_producto(productos, nombre_pedido, maximo=2)
        if not encontrados:
            resultado.no_encontrados.append(nombre_pedido)
            continue

        if len(encontrados) > 1:
            consulta_norm = normalizar(nombre_pedido)
            primero = _puntaje_producto(consulta_norm, encontrados[0])
            segundo = _puntaje_producto(consulta_norm, encontrados[1])
            if primero == segundo:
                resultado.ambiguos.append(nombre_pedido)
                continue

        producto = encontrados[0]
        item = _cotizar_item(producto, cantidad)
        resultado.items.append(item)
        resultado.total += item.subtotal
        resultado.minutos_totales += item.minutos

    return resultado


def _cotizar_item(producto: dict, cantidad: float) -> ItemCotizado:
    precio = _precio_por_escala(producto, cantidad)

    minima = float(producto.get("cantidad_minima") or 1)
    aviso = ""
    cantidad_a_cobrar = cantidad
    if cantidad < minima:
        cantidad_a_cobrar = minima
        aviso = f"cantidad mínima {minima:g} {producto['unidad']}"

    minutos = max(1, math.ceil(
        float(producto.get("minutos_preparacion") or 0)
        + float(producto.get("minutos_por_unidad") or 0) * cantidad_a_cobrar
    ))

    return ItemCotizado(
        producto_id=producto["id"],
        nombre=producto["nombre"],
        cantidad=cantidad_a_cobrar,
        unidad=producto["unidad"],
        precio_unitario=precio,
        subtotal=round(precio * cantidad_a_cobrar, 2),
        minutos=minutos,
        aviso=aviso,
        precio_provisorio=bool(producto.get("precio_provisorio", False)),
    )


def _precio_por_escala(producto: dict, cantidad: float) -> float:
    """El precio unitario que corresponde a esta cantidad.

    Las escalas son crecientes por cantidad ("desde 100 unidades, más
    barato"): se recorren de la más exigente a la menos exigente y se usa
    la primera que la cantidad alcanza a cubrir. Sin escalas, o si no llega
    a ninguna, se cobra el precio de lista.
    """
    escalas = sorted(
        producto.get("escalas") or [], key=lambda e: e["desde"], reverse=True
    )
    for escala in escalas:
        if cantidad >= escala["desde"]:
            return float(escala["precio_unitario"])

    return float(producto["precio_unitario"])
