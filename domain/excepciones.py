class ConstruProError(Exception):
    """Base de los errores de negocio de ConstruPro."""


class ReglaNegocioError(ConstruProError):
    """Se rompió una regla de negocio (RN-xxx). La API la responde como 422."""
    def __init__(self, regla: str, mensaje: str):
        self.regla = regla
        self.mensaje = mensaje
        super().__init__(mensaje)


class RecursoNoEncontradoError(ConstruProError):
    """No existe el recurso pedido. La API la responde como 404."""
    def __init__(self, mensaje: str):
        self.mensaje = mensaje
        super().__init__(mensaje)


class RecursoDuplicadoError(ConstruProError):
    """Registro repetido (RN-031). La API la responde como 409, REC_DUPLICADO."""
    def __init__(self, regla: str, mensaje: str):
        self.regla = regla
        self.mensaje = mensaje
        super().__init__(mensaje)