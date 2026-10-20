"""Deployment asset consistency tests (issue #159).

These checks parse the compose files, Dockerfiles, nginx config and
.env.example directly so the deployment surface stays coherent without
requiring a Docker daemon in CI.
"""

import re
from pathlib import Path

import pytest
import yaml

from api.auth.config import AuthSettings
from api.config import Settings
from api.files.config import FileSettings

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dev_compose() -> dict:
    return yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def prod_compose() -> dict:
    return yaml.safe_load((REPO / "docker-compose.prod.yml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dockerfile_api() -> str:
    return (REPO / "Dockerfile.api").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dockerfile_worker() -> str:
    return (REPO / "Dockerfile.worker").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def nginx_conf() -> str:
    return (REPO / "deploy" / "nginx" / "nginx.conf").read_text(encoding="utf-8")


class TestDevCompose:
    def test_redis_service_kept_for_integration_tests(self, dev_compose):
        """`docker compose up -d redis` 用法与端口、健康检查保持不变。"""
        redis = dev_compose["services"]["redis"]
        assert redis["image"] == "redis:7-alpine"
        assert redis["ports"] == ["6379:6379"]
        assert redis["healthcheck"]["test"] == ["CMD", "redis-cli", "ping"]

    def test_full_dev_stack_present(self, dev_compose):
        assert {"postgres", "redis", "api", "worker", "beat"} <= set(dev_compose["services"])

    def test_api_waits_for_healthy_dependencies(self, dev_compose):
        depends_on = dev_compose["services"]["api"]["depends_on"]
        assert depends_on["postgres"]["condition"] == "service_healthy"
        assert depends_on["redis"]["condition"] == "service_healthy"

    def test_worker_builds_from_worker_dockerfile(self, dev_compose):
        assert dev_compose["services"]["worker"]["build"]["dockerfile"] == "Dockerfile.worker"

    def test_build_services_have_distinct_image_tags(self, dev_compose, prod_compose):
        """带 build 的服务共用 image 标签会让 `docker compose build` 报 already exists。"""
        for compose in (dev_compose, prod_compose):
            built_tags = [
                service["image"] for service in compose["services"].values() if "build" in service
            ]
            assert len(built_tags) == len(set(built_tags)), built_tags

    def test_beat_schedule_file_in_writable_volume(self, dev_compose, prod_compose):
        """非 root 容器里 beat 必须把调度文件写到 /app/data，否则崩溃循环。"""
        for compose in (dev_compose, prod_compose):
            beat = compose["services"]["beat"]
            command = " ".join(beat["command"])
            assert "-s /app/data/celerybeat-schedule" in command
            assert "task_data:/app/data" in beat.get("volumes", [])


class TestProdCompose:
    def test_prod_stack_includes_nginx(self, prod_compose):
        assert {"postgres", "redis", "api", "worker", "beat", "nginx"} <= set(
            prod_compose["services"]
        )

    def test_all_services_restart_unless_stopped(self, prod_compose):
        for name, service in prod_compose["services"].items():
            assert service.get("restart") == "unless-stopped", name

    def test_no_source_bind_mounts(self, prod_compose):
        """生产编排不得把源码目录绑定进容器。"""
        for name, service in prod_compose["services"].items():
            for volume in service.get("volumes", []):
                host_path = volume.split(":")[0]
                assert not host_path.startswith(("./api", "./src")), (name, volume)

    def test_database_password_is_required(self, prod_compose):
        password = prod_compose["services"]["postgres"]["environment"]["POSTGRES_PASSWORD"]
        assert ":?" in password, "prod must fail fast when DATABASE_PASSWORD is unset"

    def test_log_rotation_on_every_service(self, prod_compose):
        for name, service in prod_compose["services"].items():
            logging_config = service.get("logging", {})
            assert logging_config.get("driver") == "json-file", name
            assert "max-size" in logging_config.get("options", {}), name

    def test_api_not_published_only_exposed(self, prod_compose):
        """生产流量走 nginx，api 不直接发布端口。"""
        api = prod_compose["services"]["api"]
        assert "ports" not in api
        assert "8000" in [str(p) for p in api["expose"]]

    def test_env_file_required_for_secrets(self, prod_compose):
        assert prod_compose["services"]["api"]["env_file"] == [".env"]

    def test_all_services_have_healthchecks(self, prod_compose, dockerfile_api):
        for name, service in prod_compose["services"].items():
            if name == "api":
                # api 的健康检查由镜像内置 HEALTHCHECK 提供
                assert "HEALTHCHECK" in dockerfile_api
            else:
                assert "healthcheck" in service, f"{name} 缺少健康检查"

    def test_worker_socket_access_requires_docker_gid(self, prod_compose, dev_compose):
        """非 root worker 访问宿主 socket 需要补 docker 组；生产未设置 GID 必须拒绝启动。"""
        prod_gid = prod_compose["services"]["worker"]["group_add"][0]
        assert "${DOCKER_GID:?" in prod_gid
        assert "${DOCKER_GID" in dev_compose["services"]["worker"]["group_add"][0]

    def test_api_trusts_proxy_headers(self, prod_compose, dev_compose):
        """反代后应用层限流/审计需要 FORWARDED_ALLOW_IPS 保留真实客户端 IP。"""
        assert prod_compose["services"]["api"]["environment"]["FORWARDED_ALLOW_IPS"] == "*"
        assert dev_compose["services"]["api"]["environment"]["FORWARDED_ALLOW_IPS"] == "*"

    def test_worker_starts_after_migrations(self, prod_compose):
        """api 健康即迁移完成，worker 不得在缺表窗口消费任务。"""
        depends_on = prod_compose["services"]["worker"]["depends_on"]
        assert depends_on["api"]["condition"] == "service_healthy"


class TestDockerfiles:
    def test_api_is_multistage(self, dockerfile_api):
        assert "FROM python:3.11-slim AS builder" in dockerfile_api
        assert "AS runtime" in dockerfile_api

    def test_api_runs_as_non_root(self, dockerfile_api):
        assert re.search(r"^USER harness$", dockerfile_api, re.MULTILINE)

    def test_api_healthcheck_hits_health_endpoint(self, dockerfile_api):
        assert "HEALTHCHECK" in dockerfile_api
        assert "/api/v1/health" in dockerfile_api

    def test_worker_carries_docker_cli(self, dockerfile_worker):
        assert "COPY --from=docker:cli" in dockerfile_worker

    def test_worker_runs_as_non_root(self, dockerfile_worker):
        assert re.search(r"^USER harness$", dockerfile_worker, re.MULTILINE)

    def test_build_context_ignores_secrets(self):
        dockerignore = (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
        assert ".env" in dockerignore
        assert ".git" in dockerignore


class TestNginx:
    def test_websocket_upgrade_for_progress_stream(self, nginx_conf):
        assert "location /api/v1/ws" in nginx_conf
        assert "proxy_set_header Upgrade $http_upgrade;" in nginx_conf
        assert 'proxy_set_header Connection "upgrade";' in nginx_conf

    def test_rate_limits_defined_and_used(self, nginx_conf):
        assert "limit_req_zone" in nginx_conf
        assert nginx_conf.count("limit_req zone=") >= 2

    def test_gzip_enabled(self, nginx_conf):
        assert re.search(r"^\s+gzip on;", nginx_conf, re.MULTILINE)

    def test_body_size_matches_upload_limit(self, nginx_conf):
        """FILE_UPLOAD_MAX_BYTES 默认 100 MiB，client_max_body_size 需对齐。"""
        assert re.search(r"^\s+client_max_body_size 100m;", nginx_conf, re.MULTILINE)

    def test_https_template_present(self, nginx_conf):
        assert "ssl_certificate" in nginx_conf
        assert "301 https://" in nginx_conf


class TestEnvExample:
    @pytest.fixture(scope="class")
    def env_example(self) -> str:
        return (REPO / ".env.example").read_text(encoding="utf-8")

    @pytest.fixture(scope="class")
    def env_keys(self, env_example) -> set[str]:
        return set(re.findall(r"^([A-Z][A-Z0-9_]+)=", env_example, re.MULTILINE))

    def test_covers_settings_fields(self, env_keys):
        """样例须覆盖三个 Settings 类的全部字段（防漂移）。"""
        required = (
            set(Settings.model_fields)
            | set(AuthSettings.model_fields)
            | set(FileSettings.model_fields)
        )
        missing = required - env_keys
        assert not missing, f".env.example 缺少字段: {sorted(missing)}"

    def test_secret_placeholders_not_real(self, env_example):
        """密钥位必须是占位符，不得出现真实凭据。"""
        assert "change-me" in re.search(r"^SECRET_KEY=(.+)$", env_example, re.MULTILINE).group(1)
        assert "change-me" in re.search(r"^ENCRYPTION_KEY=(.+)$", env_example, re.MULTILINE).group(
            1
        )

    def test_documented_database_fallback(self, env_example):
        """DATABASE_URL 留空回退 SQLite 的行为需在样例中说明。"""
        assert "SQLite" in env_example
