# app/domain/proyecto.py
# CAPA DOMINIO - HU-05 Gestión de Proyectos (MOD-02).
# Entidad Proyecto (tabla proyectos) y sus reglas de negocio.
# No importa FastAPI: las reglas lanzan excepciones de app.domain.excepciones.
#
# Reglas de la HU-05:
#   RN-016  Todo proyecto tiene un responsable activo. Además, según FUN-020 del parcial,
#           el responsable debe tener rol Coordinador o Director.
#   RN-017  La fecha de finalización estimada no puede ser anterior a la de inicio.
#   RN-018  El nombre del proyecto es único por cliente (lo consulta el servicio;
#           además hay restricción UNIQUE(cliente, nombre) en la BD).
#   RN-019  Un proyecto finalizado no admite modificaciones.
#   RN-024  Un proyecto finalizado no puede volver a otro estado (FUN-024).
#   RN-025  Un proyecto no puede finalizarse con órdenes de compra abiertas o pagos
#           pendientes (el número lo da el repositorio; hoy es 0 hasta la HU-21/HU-23).
#
# Reglas que usarán otras HU (no reimplementarlas, llamar a verificar_admite_solicitudes):
#   RN-041  Un proyecto suspendido o finalizado no puede generar solicitudes (HU-12).
#   RN-020  Todo proyecto debe registrar su ubicación antes de generar solicitudes (HU-12).
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.excepciones import ConflictoEstadoError, ReglaNegocioError
from app.domain.usuario import Usuario

ESTADO_ACTIVO = "activo"
ESTADO_SUSPENDIDO = "suspendido"
ESTADO_FINALIZADO = "finalizado"
ESTADOS = (ESTADO_ACTIVO, ESTADO_SUSPENDIDO, ESTADO_FINALIZADO)

# FUN-020: el responsable de un proyecto debe ser coordinador o director
ROLES_RESPONSABLE = ("coordinador", "director")


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class Proyecto(Base):
    __tablename__ = "proyectos"
    __table_args__ = (
        UniqueConstraint("cliente", "nombre", name="uq_proyecto_cliente_nombre"),  # RN-018
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    cliente: Mapped[str] = mapped_column(String(150))
    descripcion: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin_estimada: Mapped[date] = mapped_column(Date)
    responsable_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))       # RN-016
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_ACTIVO)
    # Ubicación de la obra (FUN-019). Queda en null hasta que se registre.
    direccion: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    ciudad: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    latitud: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitud: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)
    fecha_actualizacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=_ahora_utc
    )

    responsable: Mapped[Usuario] = relationship()

    # ── Reglas de negocio ─────────────────────────────────

    @staticmethod
    def validar_fechas(fecha_inicio: date, fecha_fin_estimada: date) -> None:
        """RN-017 (422, con el código y el mensaje general del ejemplo del issue)."""
        if fecha_fin_estimada < fecha_inicio:
            raise ReglaNegocioError(
                "RN-017",
                "La fecha de finalización no puede ser anterior a la fecha de inicio.",
                campo="fecha_fin_estimada",
                codigo="VAL_FORMATO_INVALIDO",
                mensaje_general="La información enviada contiene errores.",
            )

    @staticmethod
    def validar_responsable(usuario: Optional[Usuario], responsable_id: int) -> None:
        """RN-016 y FUN-020: el responsable existe, está activo y es coordinador o director."""
        if usuario is None:
            raise ReglaNegocioError(
                "RN-016", f"No existe un usuario con el identificador {responsable_id}.",
                campo="responsable_id")
        if not usuario.esta_activo():
            raise ReglaNegocioError(
                "RN-016", f"El usuario {usuario.nombre_completo} está inactivo y no puede ser "
                          f"responsable de un proyecto.", campo="responsable_id")
        if usuario.rol.nombre.lower() not in ROLES_RESPONSABLE:
            raise ReglaNegocioError(
                "RN-016", f"El responsable debe tener rol Coordinador o Director; "
                          f"{usuario.nombre_completo} tiene rol {usuario.rol.nombre}.",
                campo="responsable_id")

    @classmethod
    def registrar(cls, nombre: str, cliente: str, descripcion: Optional[str],
                  fecha_inicio: date, fecha_fin_estimada: date,
                  responsable: Usuario) -> "Proyecto":
        """Crea un proyecto nuevo. Siempre nace activo."""
        cls.validar_fechas(fecha_inicio, fecha_fin_estimada)                    # RN-017
        return cls(nombre=nombre, cliente=cliente, descripcion=descripcion,
                   fecha_inicio=fecha_inicio, fecha_fin_estimada=fecha_fin_estimada,
                   responsable=responsable, estado=ESTADO_ACTIVO)

    def verificar_editable(self) -> None:
        """RN-019: un proyecto finalizado no admite modificaciones (409)."""
        if self.estado == ESTADO_FINALIZADO:
            raise ConflictoEstadoError(
                "RN-019", f"El proyecto '{self.nombre}' está finalizado y no admite modificaciones.",
                campo="estado")

    def editar(self, nombre: str, cliente: str, descripcion: Optional[str],
               fecha_inicio: date, fecha_fin_estimada: date) -> None:
        """Edita los datos generales. La ubicación, el responsable y el estado tienen su endpoint."""
        self.verificar_editable()                                               # RN-019
        self.validar_fechas(fecha_inicio, fecha_fin_estimada)                   # RN-017
        self.nombre = nombre
        self.cliente = cliente
        self.descripcion = descripcion
        self.fecha_inicio = fecha_inicio
        self.fecha_fin_estimada = fecha_fin_estimada

    def registrar_ubicacion(self, direccion: str, ciudad: str,
                            latitud: Optional[float], longitud: Optional[float]) -> None:
        """FUN-019: guarda la dirección, la ciudad y las coordenadas de la obra."""
        self.verificar_editable()                                               # RN-019
        self.direccion = direccion
        self.ciudad = ciudad
        self.latitud = latitud
        self.longitud = longitud

    def tiene_ubicacion(self) -> bool:
        return bool(self.direccion and self.ciudad)

    def asignar_responsable(self, usuario: Optional[Usuario], responsable_id: int) -> None:
        """FUN-020: cambia el responsable del proyecto."""
        self.verificar_editable()                                               # RN-019
        self.validar_responsable(usuario, responsable_id)                       # RN-016
        self.responsable = usuario

    def cambiar_estado(self, nuevo_estado: str, compromisos_abiertos: int) -> None:
        """
        FUN-024: activo <-> suspendido, y de cualquiera de los dos a finalizado.
        RN-024: un proyecto finalizado no vuelve a otro estado.
        RN-025: no se finaliza con órdenes de compra abiertas o pagos pendientes.
        """
        if self.estado == nuevo_estado:
            raise ConflictoEstadoError(
                None, f"El proyecto ya se encuentra en estado '{nuevo_estado}'.", campo="estado")
        if self.estado == ESTADO_FINALIZADO:
            raise ConflictoEstadoError(
                "RN-024", "Un proyecto finalizado no puede cambiar de estado.", campo="estado")
        if nuevo_estado == ESTADO_FINALIZADO and compromisos_abiertos > 0:
            raise ConflictoEstadoError(
                "RN-025", f"El proyecto tiene {compromisos_abiertos} orden(es) de compra abierta(s) "
                          f"o pago(s) pendiente(s) y no puede finalizarse.", campo="estado")
        self.estado = nuevo_estado

    def verificar_admite_solicitudes(self) -> None:
        """
        Para la HU-12 (solicitudes de materiales). Llamarlo antes de crear una solicitud.
        RN-041: solo un proyecto activo admite solicitudes (422 NEG_PROYECTO_NO_ACTIVO).
        RN-020: el proyecto debe tener registrada su ubicación.
        """
        if self.estado != ESTADO_ACTIVO:
            raise ReglaNegocioError(
                "RN-041", f"El proyecto '{self.nombre}' está {self.estado} y no admite nuevas "
                          f"solicitudes.", campo="proyecto_id", codigo="NEG_PROYECTO_NO_ACTIVO")
        if not self.tiene_ubicacion():
            raise ReglaNegocioError(
                "RN-020", f"El proyecto '{self.nombre}' debe tener registrada su ubicación antes "
                          f"de generar solicitudes.", campo="proyecto_id")
