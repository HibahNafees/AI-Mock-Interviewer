from pathlib import Path

from flask_migrate import upgrade
from sqlalchemy import create_engine, inspect

from app import create_app
from app.config import TestConfig
from tests.test_schema import EXPECTED_TABLES

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def test_migrations_build_full_schema(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"

    class MigrateConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = url

    app = create_app(MigrateConfig)
    with app.app_context():
        upgrade(directory=str(MIGRATIONS_DIR))

    tables = set(inspect(create_engine(url)).get_table_names())
    assert tables - {"alembic_version"} == EXPECTED_TABLES
