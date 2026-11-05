"""Copy every row from another metadata database into the one DATABASE_URL
points at. For moving a deploy off its SQLite file onto Postgres:

    fly ssh console -a insightiq-api -C "python -m app.copy_db sqlite:////data/uploads/insightiq.db"

The target has to be migrated already (start.sh does that on boot). Rows whose
primary key is already there are skipped, so running it twice is harmless.
"""
import sys
from sqlalchemy import Integer, create_engine, select, text
from sqlalchemy.engine import Engine
from app.db import Base, engine as target, _database_url

BATCH = 500

def copy(source_url: str, dest: Engine = target) -> dict[str, int]:
    source = create_engine(source_url)
    copied = {}
    try:
        with source.connect() as src, dest.begin() as dst:
            for table in Base.metadata.sorted_tables:        # parents before children
                (pk,) = table.primary_key.columns
                have = set(dst.scalars(select(pk)))
                rows = [dict(r._mapping) for r in src.execute(select(table))]
                rows = [r for r in rows if r[pk.name] not in have]
                for i in range(0, len(rows), BATCH):
                    dst.execute(table.insert(), rows[i:i + BATCH])
                copied[table.name] = len(rows)
                # ids were inserted explicitly, so move the sequence past them
                if rows and dest.dialect.name == "postgresql" and isinstance(pk.type, Integer):
                    dst.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{table.name}', '{pk.name}'), "
                        f"(SELECT MAX({pk.name}) FROM {table.name}))"
                    ))
    finally:
        source.dispose()
    return copied

def main(argv: list[str]):
    if len(argv) != 1:
        raise SystemExit("usage: python -m app.copy_db SOURCE_DATABASE_URL")
    source_url = argv[0]
    if source_url == _database_url() or source_url == str(target.url):
        raise SystemExit("source and target are the same database")
    print(f"copying into {target.url.render_as_string(hide_password=True)}")
    for table, n in copy(source_url).items():
        print(f"  {table}: {n} rows")

if __name__ == "__main__":
    main(sys.argv[1:])
