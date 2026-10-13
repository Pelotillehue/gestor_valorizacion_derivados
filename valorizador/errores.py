"""!
@package valorizador.errores
@brief Errores del dominio.

Las capas inferiores lanzan estas excepciones sin conocer HTTP; @ref valorizador.main las
traduce a códigos de respuesta (404, 409, 422).
"""


class ErrorValorizador(Exception):
    """!
    @brief Base de los errores propios. Se responde con código 400 si no tiene uno más específico.
    """


class OperacionNoEncontrada(ErrorValorizador):
    """!
    @brief No existe una operación con el folio pedido. HTTP 404.
    """


class OperacionDuplicada(ErrorValorizador):
    """!
    @brief Ya existe una operación con ese folio. HTTP 409.
    """


class OperacionNoValorizable(ErrorValorizador):
    """!
    @brief La operación existe pero su estado (por ejemplo, anulada) impide valorizarla. HTTP 409.
    """


class DatoMercadoFaltante(ErrorValorizador):
    """!
    @brief Falta una curva, un tipo de cambio o el valor de un índice para la fecha de proceso. HTTP 422.
    """


class DatoInvalido(ErrorValorizador):
    """!
    @brief Los datos tienen forma correcta pero no permiten construir o modificar la operación. HTTP 422.
    """


class ContraparteNoEncontrada(ErrorValorizador):
    """!
    @brief No existe una contraparte con el RUT pedido. HTTP 404.
    """


class ContraparteDuplicada(ErrorValorizador):
    """!
    @brief Ya existe una contraparte con ese RUT o ese nombre. HTTP 409.
    """
