import pytest

from desktop_py.core.fetcher_runtime import close_all_group_runtimes


@pytest.fixture(autouse=True)
def cleanup_runtimes():
    """每个测试后自动清理浏览器运行时。"""
    yield
    close_all_group_runtimes()


@pytest.fixture
def tmp_accounts_file(tmp_path):
    """提供临时的 accounts.json 路径。"""
    path = tmp_path / "accounts.json"
    path.write_text("[]\n", encoding="utf-8")
    return path


@pytest.fixture
def tmp_settings_file(tmp_path):
    """提供临时的 settings.json 路径。"""
    import json

    from desktop_py.core.models import AppSettings

    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(AppSettings().to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
