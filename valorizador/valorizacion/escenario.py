"""!
@package valorizador.valorizacion.escenario
@brief Escenario de mercado: todo lo que el motor necesita para valorizar en una fecha.

Es un objeto inmutable y sin acceso a la base de datos. Cada dato que puede moverse es un
factor con una clave única:
- `FX:USDCLP`: tipo de cambio de un par.
- `IR:Curva CLP:365`: tasa del vértice de 365 días de una curva.

@ref valorizador.valorizacion.escenario.EscenarioMercado.desplazar devuelve un escenario nuevo con un solo factor movido. Sobre
eso se construyen las sensibilidades de esta etapa y el VaR de la siguiente.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from valorizador.enums import FactorCapitalizacion, FraccionAnio
from valorizador.errores import DatoInvalido, DatoMercadoFaltante

## Monedas por las que se triangula un tipo de cambio que no está cargado directamente.
MONEDAS_PIVOTE = ("CLP", "USD")

## Máximo de días corridos sin publicación de un índice: un fin de semana largo con feriados.
DIAS_SIN_PUBLICACION = 7


@dataclass(frozen=True)
class CurvaDatos:
    """!
    @brief Datos de una curva cero, sin objetos de QC Financial.
    """

    ## Código de la curva.
    codigo: str
    ## Plazos de los vértices en días, ordenados.
    plazos: tuple[int, ...]
    ## Tasa cero de cada vértice, en tanto por uno.
    tasas: tuple[float, ...]
    ## Convención de conteo de días de las tasas.
    fraccion_anio: FraccionAnio = FraccionAnio.ACT365
    ## Forma de capitalización de las tasas.
    factor_capitalizacion: FactorCapitalizacion = FactorCapitalizacion.COMPUESTO


@dataclass(frozen=True)
class EscenarioMercado:
    """!
    @brief Datos de mercado de una fecha de proceso, inmutable.
    """

    ## Fecha de proceso.
    fecha: date
    ## Tipos de cambio por par.
    fx: Mapping[str, float] = field(default_factory=dict)
    ## Curvas por código.
    curvas: Mapping[str, CurvaDatos] = field(default_factory=dict)
    ## Valores publicados de cada índice, por fecha.
    indices: Mapping[str, Mapping[date, float]] = field(default_factory=dict)
    ## Feriados de cada calendario.
    feriados: Mapping[str, tuple[date, ...]] = field(default_factory=dict)

    # ---------------------------------------------------------------- tipos de cambio

    def _tramo(self, de: str, a: str) -> tuple[str, bool] | None:
        """!
        @brief Par disponible para pasar de una moneda a otra y si hay que invertirlo.
        @param de Moneda de origen.
        @param a Moneda de destino.
        @return Tupla (par, invertir) o nada si el par no está cargado en ningún sentido.
        """
        if de + a in self.fx:
            return de + a, False
        if a + de in self.fx:
            return a + de, True
        return None

    def ruta_fx(self, de: str, a: str) -> list[tuple[str, bool]]:
        """!
        @brief Pares que se usan para convertir, directos o triangulando por CLP o USD.
        @param de Moneda de origen.
        @param a Moneda de destino.
        @return Lista de tuplas (par, invertir); vacía si las monedas son iguales.
        @throws DatoMercadoFaltante Si no hay forma de convertir.
        """
        if de == a:
            return []
        directo = self._tramo(de, a)
        if directo:
            return [directo]
        for pivote in MONEDAS_PIVOTE:
            if pivote in (de, a):
                continue
            primero, segundo = self._tramo(de, pivote), self._tramo(pivote, a)
            if primero and segundo:
                return [primero, segundo]
        raise DatoMercadoFaltante(
            f"No hay tipo de cambio para convertir {de} a {a} en la fecha {self.fecha.isoformat()}"
        )

    def tipo_cambio(self, de: str, a: str) -> float:
        """!
        @brief Tipo de cambio entre dos monedas.
        @param de Moneda de origen.
        @param a Moneda de destino.
        @return Unidades de la moneda `a` por una de la moneda `de`.
        @throws DatoMercadoFaltante Si no hay forma de convertir.
        """
        valor = 1.0
        for par, invertido in self.ruta_fx(de, a):
            valor *= 1.0 / self.fx[par] if invertido else self.fx[par]
        return valor

    # ------------------------------------------------------------------------ curvas

    def curva(self, codigo: str) -> CurvaDatos:
        """!
        @brief Curva por código.
        @param codigo Código de la curva.
        @return @ref valorizador.valorizacion.escenario.CurvaDatos.
        @throws DatoMercadoFaltante Si la curva no está en el escenario.
        """
        try:
            return self.curvas[codigo]
        except KeyError:
            raise DatoMercadoFaltante(
                f"No hay curva {codigo} para la fecha {self.fecha.isoformat()}"
            ) from None

    # --------------------------------------------------------------------- índices

    def valor_indice(self, indice: str, fecha: date) -> float:
        """!
        @brief Valor publicado del índice en una fecha.

        Si esa fecha no tiene publicación, por ser fin de semana o feriado, se usa el primer valor
        publicado dentro de los @ref valorizador.valorizacion.escenario.DIAS_SIN_PUBLICACION días siguientes, sin pasar de la fecha de
        proceso. Equivale a ajustar la fecha al día hábil siguiente.
        @param indice Nombre del índice.
        @param fecha Fecha del valor.
        @return Valor del índice.
        @throws DatoMercadoFaltante Si no hay publicación aplicable.
        """
        valores = self.indices.get(indice, {})
        if fecha in valores:
            return valores[fecha]
        if fecha < self.fecha:
            limite = min(self.fecha, fecha + timedelta(days=DIAS_SIN_PUBLICACION))
            siguientes = [f for f in valores if fecha < f <= limite]
            if siguientes:
                return valores[min(siguientes)]
        raise DatoMercadoFaltante(f"No hay valor del índice {indice} para la fecha {fecha.isoformat()}")

    # --------------------------------------------------------------------- factores

    def factores_curva(self, codigo: str) -> list[str]:
        """!
        @brief Claves de factor de cada vértice de una curva.
        @param codigo Código de la curva.
        @return Lista `IR:codigo:plazo`.
        """
        return [f"IR:{codigo}:{plazo}" for plazo in self.curva(codigo).plazos]

    def desplazar(self, factor: str, delta: float) -> "EscenarioMercado":
        """!
        @brief Escenario nuevo con un factor movido.

        En un factor FX el desplazamiento es relativo: 0,01 sube el tipo de cambio 1%. En un factor IR
        es absoluto: 0,0001 sube la tasa del vértice un punto base.
        @param factor Clave del factor.
        @param delta Tamaño del desplazamiento.
        @return Escenario nuevo; el original no cambia.
        @throws DatoInvalido Si el factor no existe en el escenario.
        """
        clase, _, resto = factor.partition(":")
        if clase == "FX":
            if resto not in self.fx:
                raise DatoInvalido(f"El factor {factor} no existe en el escenario")
            return replace(self, fx={**self.fx, resto: self.fx[resto] * (1.0 + delta)})
        if clase == "IR":
            codigo, _, plazo_txt = resto.rpartition(":")
            curva = self.curvas.get(codigo)
            if curva is None or not plazo_txt.isdigit() or int(plazo_txt) not in curva.plazos:
                raise DatoInvalido(f"El factor {factor} no existe en el escenario")
            i = curva.plazos.index(int(plazo_txt))
            tasas = curva.tasas[:i] + (curva.tasas[i] + delta,) + curva.tasas[i + 1 :]
            return replace(self, curvas={**self.curvas, codigo: replace(curva, tasas=tasas)})
        raise DatoInvalido(f"Factor desconocido: {factor}")
