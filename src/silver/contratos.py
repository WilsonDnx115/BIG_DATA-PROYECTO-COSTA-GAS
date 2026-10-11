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


@dataclass(frozen=True)
class Fuente:
    id: str
    familia: str
    archivo: re.Pattern
    hojas: re.Pattern
    fila_encabezado: int
    columnas: dict[str, str]              # encabezado normalizado → nombre estándar
    exigir: tuple[str, ...] = ()
    anio: int | None = None


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


def _leer(ruta: Path) -> Contrato:
    d = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    fuentes = tuple(Fuente(
        id=f["id"], familia=f.get("familia", ""), archivo=re.compile(f["archivo"], re.IGNORECASE),
        hojas=re.compile(f["hojas"], re.IGNORECASE), fila_encabezado=int(f["fila_encabezado"]),
        columnas={normalizar_encabezado(k): v for k, v in f["columnas"].items()},
        exigir=tuple(f.get("exigir", ())), anio=f.get("anio")) for f in d["fuentes"])
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ddl", action="store_true", help="genera los DDL de Athena desde los contratos")
    a = ap.parse_args()
    if a.ddl:
        for p in escribir_ddl():
            print(p.relative_to(config.RAIZ_REPO))
    else:
        for c in cargar().values():
            print(f"{c.tabla}: {len(c.columnas)} columnas, {len(c.fuentes)} fuentes, llave {list(c.llave)}")
