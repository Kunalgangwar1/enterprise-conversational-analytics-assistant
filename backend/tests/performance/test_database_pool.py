from app.core.config import Settings
from app.db.session import database_engine_options


def test_database_pool_has_recycle_and_bounded_capacity() -> None:
    options = database_engine_options(
        Settings(
            app_env="test",
            database_pool_size=4,
            database_max_overflow=2,
            database_pool_timeout_seconds=3,
            database_pool_recycle_seconds=900,
        )
    )
    assert options["pool_pre_ping"] is True
    assert options["pool_size"] == 4
    assert options["max_overflow"] == 2
    assert options["pool_timeout"] == 3
    assert options["pool_recycle"] == 900
