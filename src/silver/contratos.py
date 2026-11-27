"""Contratos de las tablas Silver (WP 1.1, hallazgo C5, base B5 del Plan de Corrección).

Un YAML por tabla en `contracts/`. De ahí salen el esquema que escribe la Lambda,
las columnas que se leen de cada hoja y el DDL de Athena: una sola fuente de verdad.

Uso:  python -m src.silver.contratos --ddl     # genera sql/athena/ddl/silver_<tabla>.sql
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pyarrow as pa
import yaml

from src.common import config

DIR_CONTRATOS = config.RAIZ_REPO / "contracts"
_PA = {"string": pa.string(), "double": pa.float64(), "int": pa.int64(), "bool": pa.bool_(), "date": pa.date32()}
_ATHENA = {"string": "string", "double": "double", "int": "bigint", "bool": "boolean", "date": "date"}


def normalizar_encabezado(texto) -> str:
    """'GLP-E (Kilogramos)' → 'GLP E KILOGRAMOS' · 'N° FACT' → 'N FACT' · 'AÑO' → 'ANO'."""
    s = unicodedata.normalize("NFKD", str(texto or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9#]+", " ", s)).strip()


def indice_de_columna(letra: str) -> int:
    """'A' → 0, 'G' → 6, 'AA' → 26. Es la posición de la columna en la hoja.

    Lo usan las fuentes de hojas que empiezan en datos: ahí no hay encabezado que
    emparejar, así que la única referencia estable es en qué columna está el dato.
    """
    s = str(letra).strip().upper()
    if not s or not s.isalpha():
        raise ValueError(f"«{letra}» no es una letra de columna de Excel")
    n = 0
    for c in s:
        n = n * 26 + (ord(c) - ord("A") + 1)
    return n - 1


@dataclass(frozen=True)
class Fuente:
    """Una hoja de la entrega y cómo se leen sus columnas.

    Dos formas, excluyentes entre sí:

    * **por nombre**, lo habitual: `fila_encabezado` y `columnas`, que empareja el
      encabezado normalizado con el nombre estándar;
    * **por posición**, para las hojas que empiezan en datos: `primera_fila` y
      `posiciones`, que empareja la letra de la columna con el nombre estándar.
    """

    id: str
    familia: str
    archivo: re.Pattern
    hojas: re.Pattern
    fila_encabezado: int = 0
    columnas: dict[str, str] = field(default_factory=dict)   # encabezado normalizado → estándar
    primera_fila: int = 0
    posiciones: dict[str, int] = field(default_factory=dict)  # nombre estándar → índice de columna
    exigir: tuple[str, ...] = ()
    anio: int | None = None

    @property
    def por_posicion(self) -> bool:
        return bool(self.posiciones)

    def destinos(self) -> set[str]:
        """Nombres estándar que esta fuente produce, se lea como se lea."""
        return set(self.posiciones) or set(self.columnas.values())


@dataclass(frozen=True)
class Columna:
    nombre: str
    tipo: str
    rol: str = "atributo"
    regla: str = ""
    personal: bool = False


@dataclass(frozen=True)
class Contrato:
    tabla: str
    dominio: str
    descripcion: str
    grano: str
    llave: tuple[str, ...]
    fuentes: tuple[Fuente, ...]
    columnas: tuple[Columna, ...]
    pendiente: tuple[str, ...] = field(default_factory=tuple)
    filas_esperadas: int | None = None

    def nombres(self) -> list[str]:
        return [c.nombre for c in self.columnas]

    def esquema(self) -> pa.Schema:
        return pa.schema([(c.nombre, _PA[c.tipo]) for c in self.columnas])

    def personales(self) -> list[str]:
        return [c.nombre for c in self.columnas if c.personal]

    def ddl(self, lake: str = "${LAKE}") -> str:
        cols = ",\n".join(f"  {c.nombre} {_ATHENA[c.tipo]}" + (f" COMMENT '{c.regla[:200]}'" if c.regla else "")
                          for c in self.columnas)
        return (f"-- Generado desde contracts/{self.tabla}.yaml. No editar a mano: python -m src.silver.contratos --ddl\n"
                f"CREATE EXTERNAL TABLE IF NOT EXISTS costagas_silver.{self.tabla} (\n{cols})\n"
                f"COMMENT '{self.descripcion[:250]}'\n"
                f"STORED AS PARQUET\n"
                f"LOCATION '{lake}/silver/{self.dominio}/{self.tabla}/';\n")


def _fuente(ruta: Path, f: dict) -> Fuente:
    """Una fuente del YAML. Declara sus columnas por nombre o por posición, nunca las dos."""
    tiene_nombres = bool(f.get("columnas"))
    tiene_posiciones = bool(f.get("posiciones"))
    if tiene_nombres == tiene_posiciones:
        raise ValueError(f"{ruta.name}: la fuente «{f['id']}» declara sus columnas "
                         f"por nombre o por posicion, y tiene que ser una de las dos")

    posiciones = {}
    if tiene_posiciones:
        for letra, destino in f["posiciones"].items():
            try:
                posiciones[destino] = indice_de_columna(letra)
            except ValueError as e:
                raise ValueError(f"{ruta.name}, fuente «{f['id']}»: {e}") from None

    return Fuente(
        id=f["id"], familia=f.get("familia", ""), archivo=re.compile(f["archivo"], re.IGNORECASE),
        hojas=re.compile(f["hojas"], re.IGNORECASE),
        fila_encabezado=int(f.get("fila_encabezado", 0)),
        columnas={normalizar_encabezado(k): v for k, v in (f.get("columnas") or {}).items()},
        primera_fila=int(f.get("primera_fila", 0)), posiciones=posiciones,
        exigir=tuple(f.get("exigir", ())), anio=f.get("anio"))


def _leer(ruta: Path) -> Contrato:
    d = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    fuentes = tuple(_fuente(ruta, f) for f in d["fuentes"])
    columnas = tuple(Columna(**c) for c in d["columnas"])
    tipos = {c.tipo for c in columnas} - set(_PA)
    if tipos:
        raise ValueError(f"{ruta.name}: tipos no admitidos {tipos}")
    faltan = [k for k in d["llave"] if k not in {c.nombre for c in columnas}]
    if faltan:
        raise ValueError(f"{ruta.name}: la llave usa columnas que no están en el contrato: {faltan}")
    return Contrato(tabla=d["tabla"], dominio=d["dominio"], descripcion=d.get("descripcion", ""),
                    grano=d.get("grano", ""), llave=tuple(d["llave"]), fuentes=fuentes, columnas=columnas,
                    pendiente=tuple(d.get("pendiente", ())),
                    filas_esperadas=(d.get("valor_esperado") or {}).get("filas"))


@lru_cache(maxsize=1)
def cargar() -> dict[str, Contrato]:
    return {c.tabla: c for c in (_leer(p) for p in sorted(DIR_CONTRATOS.glob("*.yaml")) if not p.name.startswith("_"))}


def fuentes_para(nombre_archivo: str) -> list[tuple[Contrato, Fuente]]:
    """Contratos y fuentes cuyo patrón coincide con el nombre del archivo de Bronze."""
    return [(c, f) for c in cargar().values() for f in c.fuentes if f.archivo.search(nombre_archivo)]


def escribir_ddl(destino: Path | None = None) -> list[Path]:
    destino = destino or config.RAIZ_REPO / "sql" / "athena" / "ddl"
    destino.mkdir(parents=True, exist_ok=True)
    salidas = []
    for c in cargar().values():
        p = destino / f"silver_{c.tabla}.sql"
        p.write_text(c.ddl(), encoding="utf-8", newline="\n")
        salidas.append(p)
    return salidas


def validar() -> list[str]:
    """Problemas que impiden desplegar los contratos. Lista vacia = todo en orden.

    Lo comprueba la integracion continua antes de aceptar un cambio: un contrato sin
    llave, con un tipo que Athena no entiende o cuyo DDL versionado quedo viejo rompe
    el despliegue de Silver, y conviene saberlo en el pull request y no en la corrida.
    """
    problemas: list[str] = []
    try:
        todos = cargar()
    except Exception as exc:                                   # noqa: BLE001
        return [f"no se pueden cargar los contratos: {exc}"]

    if not todos:
        return ["no hay ningun contrato en contracts/"]

    # cargar() devuelve un dict indexado por tabla, asi que dos archivos con la misma
    # tabla se pisarian sin avisar. Por eso el duplicado se busca sobre los archivos.
    vistos: dict[str, str] = {}
    for ruta in sorted(DIR_CONTRATOS.glob("*.yaml")):
        if ruta.name.startswith("_"):
            continue
        nombre = (yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}).get("tabla")
        if nombre in vistos:
            problemas.append(f"{ruta.name}: declara la tabla «{nombre}», ya declarada en {vistos[nombre]}")
        vistos[nombre] = ruta.name

    for tabla, c in sorted(todos.items()):
        if not c.tabla:
            problemas.append(f"{tabla}: sin nombre de tabla")
        if not c.dominio:
            problemas.append(f"{tabla}: sin dominio, no se sabe donde escribirla")
        if not c.llave:
            problemas.append(f"{tabla}: sin llave natural")
        if not c.columnas:
            problemas.append(f"{tabla}: sin columnas")
        if not c.fuentes:
            problemas.append(f"{tabla}: sin ninguna fuente declarada")

        nombres = c.nombres()
        repetidas = sorted({n for n in nombres if nombres.count(n) > 1})
        if repetidas:
            problemas.append(f"{tabla}: columnas repetidas {repetidas}")
        for col in c.columnas:
            if col.tipo not in _PA:
                problemas.append(f"{tabla}.{col.nombre}: tipo «{col.tipo}» no admitido")

        for f in c.fuentes:
            if not f.destinos():            # por nombre o por posición, pero alguna
                problemas.append(f"{tabla}/{f.id}: no declara ninguna columna")

        versionado = config.RAIZ_REPO / "sql" / "athena" / "ddl" / f"silver_{c.tabla}.sql"
        if not versionado.exists():
            problemas.append(f"{tabla}: falta {versionado.name}; generelo con --ddl")
        elif versionado.read_text(encoding="utf-8") != c.ddl():
            problemas.append(f"{tabla}: {versionado.name} no coincide con el contrato; "
                             f"regenerelo con: python -m src.silver.contratos --ddl")
    return problemas


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ddl", action="store_true", help="genera los DDL de Athena desde los contratos")
    ap.add_argument("--validar", action="store_true",
                    help="revisa los contratos y sus DDL; sale con 1 si algo falla")
    a = ap.parse_args()
    if a.validar:
        fallos = validar()
        for f in fallos:
            print(f"ERROR {f}")
        print(f"{len(cargar())} contratos revisados, {len(fallos)} problemas")
        raise SystemExit(1 if fallos else 0)
    if a.ddl:
        for p in escribir_ddl():
            print(p.relative_to(config.RAIZ_REPO))
    else:
        for c in cargar().values():
            print(f"{c.tabla}: {len(c.columnas)} columnas, {len(c.fuentes)} fuentes, llave {list(c.llave)}")
