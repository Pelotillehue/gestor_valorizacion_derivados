"""!
@package crear_usuario
@brief Crea un usuario de la app o le cambia la clave, directamente en la base de datos.

Usa la `DATABASE_URL` del archivo `.env`. Si no se indica `--clave`, la pide sin mostrarla en
pantalla. Si el usuario ya existe, actualiza su clave y su nombre y lo deja activo.

Uso, desde la carpeta del proyecto:
@code
python scripts/crear_usuario.py usuario@empresa.cl --nombre "Nombre Apellido"
python scripts/crear_usuario.py usuario@empresa.cl --desactivar
@endcode
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from valorizador.db import modelos  # noqa: E402
from valorizador.db.base import SesionLocal  # noqa: E402
from valorizador.seguridad import hash_clave  # noqa: E402


def main() -> None:
    """!
    @brief Lee los argumentos y crea, actualiza o desactiva el usuario.
    """
    parser = argparse.ArgumentParser(description="Crea un usuario de la app o le cambia la clave.")
    parser.add_argument("email", help="Correo del usuario; se guarda en minúsculas")
    parser.add_argument("--nombre", help="Nombre para mostrar")
    parser.add_argument("--clave", help="Clave; si se omite, se pide sin mostrarla")
    parser.add_argument("--desactivar", action="store_true", help="Desactiva el usuario en vez de cambiar la clave")
    args = parser.parse_args()
    email = args.email.strip().lower()

    with SesionLocal() as db:
        usuario = db.get(modelos.Usuario, email)
        if args.desactivar:
            if usuario is None:
                sys.exit(f"No existe el usuario {email}")
            usuario.activo = False
            db.commit()
            print(f"Usuario {email} desactivado")
            return

        clave = args.clave or getpass.getpass("Clave: ")
        if not args.clave and clave != getpass.getpass("Repita la clave: "):
            sys.exit("Las claves no coinciden")
        if not clave:
            sys.exit("La clave no puede estar vacía")

        if usuario is None:
            usuario = modelos.Usuario(email=email)
            db.add(usuario)
            accion = "creado"
        else:
            accion = "actualizado"
        usuario.hash_clave = hash_clave(clave)
        usuario.activo = True
        if args.nombre:
            usuario.nombre = args.nombre
        db.commit()
        print(f"Usuario {email} {accion}")


if __name__ == "__main__":
    main()
