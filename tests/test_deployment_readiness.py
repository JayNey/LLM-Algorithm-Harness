"""Exercise the shipped nginx config against a controlled HTTP upstream."""

import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import requests

REPO = Path(__file__).resolve().parents[1]
NGINX = shutil.which("nginx") or "/opt/homebrew/bin/nginx"


@pytest.fixture
def proxy(tmp_path):
    if not Path(NGINX).exists():
        pytest.skip("nginx executable required for proxy integration")
    state = {"ready": 200, "calls": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["calls"].append((self.command, self.path, dict(self.headers)))
            if self.path == "/api/v1/health/ready":
                if state["ready"] == "timeout":
                    time.sleep(3)
                    return
                status = state["ready"]
            elif self.path == "/api/v1/health":
                status = 200
            elif self.path == "/api/v1/system/health":
                status = 401
            elif self.headers.get("Upgrade", "").lower() == "websocket":
                status = 101
            elif self.path.startswith("/status/"):
                status = int(self.path.rsplit("/", 1)[1])
            else:
                status = 201
            self.send_response(status)
            if status == 101:
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
            self.end_headers()

        do_POST = do_GET

        def log_message(self, *args):
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    (tmp_path / "logs").mkdir()
    (tmp_path / "temp").mkdir()
    conf = (REPO / "deploy/nginx/nginx.conf").read_text(encoding="utf-8")
    # Packaged nginx uses absolute system paths even with -p. Override all
    # runtime files so the real proxy runs as an unprivileged CI user.
    conf = "pid logs/nginx.pid;\nerror_log stderr;\nlock_file logs/nginx.lock;\n" + conf
    conf = conf.replace(
        "http {",
        """http {
    access_log off;
    client_body_temp_path temp/client_body;
    proxy_temp_path temp/proxy;
    fastcgi_temp_path temp/fastcgi;
    uwsgi_temp_path temp/uwsgi;
    scgi_temp_path temp/scgi;
""",
        1,
    )
    conf = conf.replace("include /etc/nginx/mime.types;", "")
    conf = conf.replace("server api:8000;", f"server 127.0.0.1:{upstream.server_port};")
    conf = conf.replace("listen 80;", f"listen 127.0.0.1:{port};")
    config = tmp_path / "nginx.conf"
    config.write_text(conf, encoding="utf-8")
    process = subprocess.Popen(
        [NGINX, "-p", str(tmp_path), "-c", str(config), "-e", "stderr", "-g", "daemon off;"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    state["runtime"] = tmp_path
    state["pid"] = process.pid
    session = requests.Session()
    session.trust_env = False
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if process.poll() is not None:
                pytest.fail(process.communicate()[1].decode())
            try:
                session.get(url + "/api/v1/health", timeout=0.2)
                break
            except requests.ConnectionError:
                time.sleep(0.02)
        else:
            pytest.fail("nginx did not start")
        state["calls"].clear()
        yield state, session, url
    finally:
        session.close()
        process.terminate()
        process.communicate(timeout=5)
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=5)


def test_nginx_runtime_pid_is_isolated(proxy):
    state, _, _ = proxy
    pid_file = state["runtime"] / "logs/nginx.pid"
    assert pid_file.is_file(), "nginx must use the writable test prefix for runtime files"
    assert int(pid_file.read_text(encoding="utf-8")) == state["pid"]


@pytest.mark.parametrize(
    "path", ["/api/v1/evaluations", "/api/v1/auth/login", "/api/v1/ws/progress"]
)
def test_unready_blocks_business_and_recovers(proxy, path):
    state, session, url = proxy
    state["ready"] = 503
    response = session.post(url + path, data="payload", timeout=5)
    assert response.status_code == 503
    assert response.headers["Cache-Control"] == "no-store"
    assert all(call[1] == "/api/v1/health/ready" for call in state["calls"])
    assert session.get(url + "/api/v1/health", timeout=5).status_code == 200
    assert session.get(url + "/api/v1/health/ready", timeout=5).status_code == 503
    assert session.get(url + "/api/v1/system/health", timeout=5).status_code == 401
    state["ready"] = 200
    assert session.post(url + path, timeout=5).status_code == 201


@pytest.mark.parametrize("status", [401, 403, 500, "timeout"])
def test_probe_error_and_timeout_fail_closed(proxy, status):
    state, session, url = proxy
    state["ready"] = status
    start = time.monotonic()
    assert session.get(url + "/business", timeout=5).status_code == 503
    assert time.monotonic() - start < 4
    assert all(call[1] == "/api/v1/health/ready" for call in state["calls"])


def test_probe_is_get_without_client_credentials_body_or_query(proxy):
    state, session, url = proxy
    assert (
        session.post(
            url + "/business?secret=query",
            data="secret body",
            headers={"Authorization": "Bearer client", "Cookie": "session=client"},
            timeout=5,
        ).status_code
        == 201
    )
    probe = state["calls"][0]
    assert probe[:2] == ("GET", "/api/v1/health/ready")
    assert not {key.lower() for key in probe[2]} & {"authorization", "cookie", "content-length"}


@pytest.mark.parametrize("status", [401, 403, 500])
def test_business_errors_are_preserved(proxy, status):
    _, session, url = proxy
    assert session.get(url + f"/status/{status}", timeout=5).status_code == status


def test_probe_requests_do_not_hit_business_rate_limit(proxy):
    _, session, url = proxy
    for _ in range(70):
        assert session.get(url + "/api/v1/health", timeout=5).status_code == 200
        assert session.get(url + "/api/v1/health/ready", timeout=5).status_code == 200


def test_websocket_upgrade_headers_survive_admission(proxy):
    state, session, url = proxy
    response = session.get(
        url + "/api/v1/ws/progress",
        headers={"Upgrade": "websocket", "Connection": "Upgrade"},
        timeout=5,
    )
    assert response.status_code == 101
    assert response.headers["Upgrade"] == "websocket"
    assert state["calls"][0][:2] == ("GET", "/api/v1/health/ready")
    assert state["calls"][1][1] == "/api/v1/ws/progress"
