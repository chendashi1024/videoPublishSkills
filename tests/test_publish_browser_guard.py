"""发布浏览器身份门禁：仅模拟进程与 HTTP，不操作真实网页。"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import chrome_launcher as launcher
import publish_browser_guard as guard
from core.cdp_client import CDPClient


@pytest.fixture
def dedicated(monkeypatch):
    monkeypatch.delenv(launcher.EDGE_USER_DATA_DIR_ENV, raising=False)
    process = MagicMock(pid=42)
    process.exe.return_value = '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'
    process.cmdline.return_value = [process.exe(), '--remote-debugging-port=9222', '--user-data-dir='+launcher.EDGE_PROFILE_DIR]
    version = MagicMock()
    version.json.return_value = {'webSocketDebuggerUrl':'ws://127.0.0.1:9222/devtools/browser/example'}
    targets = MagicMock()
    targets.json.return_value = []
    session = MagicMock()
    session.get.side_effect = [version, targets]
    with patch.object(guard.subprocess, 'run', return_value=MagicMock(returncode=0, stdout='42\n')), patch.object(guard.psutil, 'Process', return_value=process), patch.object(guard.requests, 'Session', return_value=session):
        yield process, version, targets


def test_dedicated_edge_passes(dedicated):
    assert guard.validate_publish_browser()['status'] == 'PUBLISH_BROWSER_VERIFIED'


@pytest.mark.parametrize('kind', ['daily', 'profile', 'chrome', 'http404', 'bad_list', 'remote_ws', 'port', 'host'])
def test_wrong_browser_or_endpoint_fails(dedicated, kind):
    process, version, targets = dedicated
    if kind == 'daily': process.cmdline.return_value = [process.exe()]
    if kind == 'profile': process.cmdline.return_value[-1] = '--user-data-dir=/tmp/daily'
    if kind == 'chrome': process.exe.return_value = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if kind == 'http404': version.raise_for_status.side_effect = RuntimeError('404')
    if kind == 'bad_list': targets.json.return_value = {}
    if kind == 'remote_ws': version.json.return_value['webSocketDebuggerUrl'] = 'ws://example.com:9222/devtools/browser/example'
    with pytest.raises(guard.PublishBrowserError, match='PUBLISH_BROWSER_MISMATCH'):
        guard.validate_publish_browser(host='localhost' if kind == 'host' else '127.0.0.1', port=9223 if kind == 'port' else 9222)


def test_launcher_rejects_occupied_daily_edge_without_launch(dedicated):
    dedicated[0].cmdline.return_value = [dedicated[0].exe()]
    with patch.object(launcher, 'is_port_open', return_value=True), patch.object(launcher.subprocess, 'Popen') as launch:
        with pytest.raises(guard.PublishBrowserError): launcher.ensure_chrome(account='edge')
        launch.assert_not_called()


def test_cdp_stops_before_reading_page_or_retrying(dedicated):
    dedicated[0].cmdline.return_value = [dedicated[0].exe()]
    with patch('core.cdp_client.requests.get') as page_request:
        with pytest.raises(guard.PublishBrowserError): CDPClient().get_targets()
        page_request.assert_not_called()


def test_cannot_override_profile(monkeypatch):
    monkeypatch.setenv(launcher.EDGE_USER_DATA_DIR_ENV, '/tmp/daily')
    with pytest.raises(guard.PublishBrowserError): guard.validate_publish_browser()
