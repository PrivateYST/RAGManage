"""公司 API Key 的凭据安全、额度原子性、结算幂等和接口权限测试。"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.api_keys import (
    ApiKeyQuotaExceededError,
    authenticate_api_key,
    decrypt_api_key,
    encrypt_api_key,
    generate_api_key,
    hash_api_key,
    recover_stale_api_key_reservations,
    reserve_api_key_tokens,
    settle_api_key_usage,
)
from app.core.auth import SESSION_COOKIE
from app.core.config import Settings
from app.main import _knowledge_base_access, create_app
from app.rag.chat import _combined_usage


class FakeTransaction:
    """为结算函数提供最小异步事务边界。"""

    async def __aenter__(self) -> None:
        """进入无副作用的测试事务。"""
        return None

    async def __aexit__(self, *args: object) -> None:
        """退出测试事务，不吞掉异常。"""
        return None


class FakeApiKeyConnection:
    """记录额度 SQL 参数，并允许测试控制原子更新结果。"""

    def __init__(
        self,
        *,
        row: dict[str, object] | None = None,
        inserted: int | None = 1,
        reserved_tokens: int | None = None,
        recovery_rows: list[dict[str, object]] | None = None,
        candidate_id: int | None = None,
    ) -> None:
        """配置鉴权、结算和崩溃恢复各 SQL 分支的返回值。"""
        self.row = row
        self.inserted = inserted
        self.reserved_tokens = reserved_tokens
        self.recovery_rows = recovery_rows or []
        self.candidate_id = candidate_id
        self.execute_calls: list[tuple[Any, ...]] = []
        self.fetch_calls: list[tuple[Any, ...]] = []
        self.fetchrow_calls: list[tuple[Any, ...]] = []
        self.fetchval_calls: list[tuple[Any, ...]] = []

    def transaction(self) -> FakeTransaction:
        """返回不访问数据库的异步事务上下文。"""
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        """记录单行查询并返回预设鉴权或额度结果。"""
        self.fetchrow_calls.append((query, *args))
        return self.row

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        """返回待恢复预留，让鉴权和恢复测试共用最小数据库替身。"""
        self.fetch_calls.append((query, *args))
        return self.recovery_rows

    async def fetchval(self, query: str, *args: object) -> int | None:
        """按候选鉴权、预留删除或流水插入查询返回对应结果。"""
        self.fetchval_calls.append((query, *args))
        if "SELECT id FROM api_keys" in query:
            if self.candidate_id is not None:
                return self.candidate_id
            return int(self.row["api_key_id"]) if self.row is not None else None
        if "DELETE FROM api_key_reservations" in query:
            return self.reserved_tokens
        if "INSERT INTO api_key_usage" not in query:
            raise AssertionError(f"未处理的 fetchval 查询：{query}")
        return self.inserted

    async def execute(self, query: str, *args: object) -> None:
        """记录额度与恢复状态写入，供断言事务副作用。"""
        self.execute_calls.append((query, *args))


class FakeManagementConnection:
    """模拟管理员创建 Key 所需的租户查询、插入和审计写入。"""

    def __init__(self) -> None:
        """初始化按调用顺序记录的管理接口替身。"""
        self.calls: list[tuple[Any, ...]] = []
        self.closed = False

    def transaction(self) -> FakeTransaction:
        """让管理接口测试覆盖凭据变更与审计的同一事务边界。"""
        return FakeTransaction()

    async def fetchval(self, query: str, *args: object) -> object:
        """返回启用租户名称，并拒绝测试未声明的标量查询。"""
        self.calls.append((query, *args))
        if "SELECT EXISTS" in query:
            return True
        if "SELECT name FROM tenants" in query:
            return "客户 A"
        raise AssertionError(f"未处理的 fetchval 查询：{query}")

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        """模拟只保存哈希后的 Key 插入响应。"""
        self.calls.append((query, *args))
        return {
            "id": "9",
            "tenant_id": "3",
            "name": "生产 Key",
            "key_prefix": "sk-masked",
            "token_limit": 1000,
            "token_used": 0,
            "token_reserved": 0,
            "expires_at": None,
            "created_at": "2026-09-20T00:00:00Z",
        }

    async def execute(self, query: str, *args: object) -> None:
        """记录审计写入参数以检查明文不会落库。"""
        self.calls.append((query, *args))

    async def close(self) -> None:
        """标记接口 finally 已关闭连接。"""
        self.closed = True


class FakeUsageConnection:
    """返回完整汇总和一条最近流水，验证两者不会被混为同一统计口径。"""

    def __init__(self) -> None:
        """初始化可观察关闭状态的用量查询替身。"""
        self.closed = False

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        """返回超过最近列表上限的全量聚合。"""
        assert "count(usage.id)" in query
        assert args == (9,)
        return {
            "request_count": 350,
            "prompt_tokens": 2600,
            "completion_tokens": 900,
            "total_tokens": 3500,
        }

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        """返回最近一条流水并验证服务端固定限制。"""
        assert "LIMIT 200" in query
        assert args == (9,)
        return [
            {
                "request_id": "11111111-1111-4111-8111-111111111111",
                "model_name": "embed + chat",
                "prompt_tokens": 26,
                "completion_tokens": 8,
                "total_tokens": 34,
                "usage_source": "gateway",
                "model_usage": {},
                "status": "completed",
                "created_at": "2026-09-20T00:00:00Z",
                "completed_at": "2026-09-20T00:00:01Z",
            }
        ]

    async def close(self) -> None:
        """标记用量接口已释放连接。"""
        self.closed = True


class FakeRevealConnection:
    """模拟管理员查询加密密文并记录复制审计。"""

    def __init__(self, encrypted_key: str | None) -> None:
        self.encrypted_key = encrypted_key
        self.closed = False
        self.execute_calls: list[tuple[Any, ...]] = []

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert args == (9,)
        if self.encrypted_key is None:
            return None
        return {"id": "9", "tenant_id": 3, "name": "生产 Key", "encrypted_key": self.encrypted_key}

    async def execute(self, query: str, *args: object) -> None:
        self.execute_calls.append((query, *args))

    async def close(self) -> None:
        self.closed = True


class FakeLifecycleConnection:
    """模拟 API Key 状态切换和软删除接口，并保留审计写入记录。"""

    def __init__(
        self,
        *,
        status: str = "disabled",
        provider: str = "local",
        provider_user_email: str | None = None,
        provider_user_password: str | None = None,
    ) -> None:
        """配置状态更新接口的返回状态。"""
        self.status = status
        self.provider = provider
        self.provider_user_email = provider_user_email
        self.provider_user_password = provider_user_password
        self.execute_calls: list[tuple[Any, ...]] = []
        self.closed = False

    def transaction(self) -> FakeTransaction:
        """返回管理接口使用的异步事务上下文。"""
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        """按接口 SQL 返回状态变更或软删除后的 Key。"""
        assert args == (9, "disabled") if "SET status" in query else args == (9,)
        if "SET status" in query:
            return {
                "id": "9",
                "tenant_id": "3",
                "name": "生产 Key",
                "status": self.status,
                "revoked_at": None,
            }
        return {
            "id": "9",
            "tenant_id": "3",
            "name": "生产 Key",
            "status": "revoked",
            "deleted_at": "2026-09-21T00:00:00Z",
            "provider": self.provider,
            "provider_user_email": self.provider_user_email,
            "provider_user_password": self.provider_user_password,
        }

    async def execute(self, query: str, *args: object) -> None:
        """记录 API Key 生命周期审计调用。"""
        self.execute_calls.append((query, *args))

    async def close(self) -> None:
        """标记管理接口已释放数据库连接。"""
        self.closed = True


def test_generated_key_only_persists_hash_and_masked_prefix() -> None:
    """随机明文仅返回给创建者，哈希和脱敏前缀不能还原可调用凭据。"""
    raw_key, prefix, key_hash = generate_api_key()

    assert raw_key.startswith("sk-")
    assert prefix != raw_key
    assert raw_key not in prefix
    assert key_hash == hash_api_key(raw_key)
    assert len(key_hash) == 64


def test_api_key_encryption_round_trip_does_not_store_plaintext() -> None:
    """复制密文可跨请求解密，但密文本身不能直接暴露可调用 Key。"""
    raw_key = "sk-test-secret"
    ciphertext = encrypt_api_key(raw_key, "stable-test-secret")

    assert raw_key not in ciphertext
    assert decrypt_api_key(ciphertext, "stable-test-secret") == raw_key


def test_platform_admin_can_reveal_encrypted_api_key(monkeypatch: Any) -> None:
    """管理员复制接口返回完整 Key，并记录脱敏审计，不允许匿名调用。"""
    raw_key = "sk-copyable-secret"
    connection = FakeRevealConnection(
        encrypt_api_key(raw_key, Settings().api_key_encryption_secret_value)
    )
    monkeypatch.setattr(
        "app.main._authenticated_user",
        AsyncMock(return_value={"user": {"id": "7", "platform_role": "platform_admin"}}),
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/v1/api-keys/9/key")

    assert response.status_code == 200
    assert response.json()["raw_key"] == raw_key
    assert any("api_key.reveal" in str(call) for call in connection.execute_calls)
    assert connection.closed


def test_platform_admin_can_toggle_api_key_status_and_audit(monkeypatch: Any) -> None:
    """状态切换只允许管理员执行，并记录新的启用状态而不暴露凭据。"""
    connection = FakeLifecycleConnection()
    monkeypatch.setattr(
        "app.main._authenticated_user",
        AsyncMock(return_value={"user": {"id": "7", "platform_role": "platform_admin"}}),
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.patch("/api/v1/api-keys/9/status", json={"status": "disabled"})

    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    assert any("api_key.status.update" in str(call) for call in connection.execute_calls)
    assert connection.closed


def test_platform_admin_soft_deletes_api_key_and_preserves_history(monkeypatch: Any) -> None:
    """删除接口只隐藏并失效 Key，历史用量和外键记录仍可继续查询。"""
    connection = FakeLifecycleConnection()
    monkeypatch.setattr(
        "app.main._authenticated_user",
        AsyncMock(return_value={"user": {"id": "7", "platform_role": "platform_admin"}}),
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.delete("/api/v1/api-keys/9")

    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
    assert any("api_key.delete" in str(call) for call in connection.execute_calls)
    assert connection.closed


def test_open_webui_key_is_revoked_before_local_soft_delete(monkeypatch: Any) -> None:
    """医院 Key 删除必须先撤销远端原生 Key，再完成本地生命周期变更。"""
    settings = Settings()
    connection = FakeLifecycleConnection(
        provider="open_webui",
        provider_user_email="ragmanage-tenant-3@service.ragmanage.local",
        provider_user_password=encrypt_api_key(
            "service-password",
            settings.api_key_encryption_secret_value,
        ),
    )
    revoke = AsyncMock()
    monkeypatch.setattr(
        "app.main._authenticated_user",
        AsyncMock(return_value={"user": {"id": "7", "platform_role": "platform_admin"}}),
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.main.OpenWebUIAdminClient.revoke_service_key", revoke)

    with TestClient(create_app(settings)) as client:
        response = client.delete("/api/v1/api-keys/9")

    assert response.status_code == 200
    revoke.assert_awaited_once_with(
        user_email="ragmanage-tenant-3@service.ragmanage.local",
        user_password="service-password",
    )
    assert any("api_key.delete" in str(call) for call in connection.execute_calls)


def test_authentication_rejects_missing_revoked_or_exhausted_key() -> None:
    """数据库原子查询未返回身份时，任何无效状态都统一鉴权失败。"""
    connection = FakeApiKeyConnection(row=None)

    result = asyncio.run(authenticate_api_key(connection, "rmk_invalid"))  # type: ignore[arg-type]

    assert result is None
    assert "SELECT id FROM api_keys WHERE key_hash = $1" in connection.fetchval_calls[0][0]
    assert connection.fetchrow_calls == []
    assert connection.fetch_calls == []
    assert connection.execute_calls == []


def test_authentication_recovers_only_the_matching_valid_key() -> None:
    """有效凭据只恢复自身预留，签发管理员状态不参与公司 Key 生命周期。"""
    connection = FakeApiKeyConnection(
        row={
            "api_key_id": "9",
            "api_key_tenant_id": "3",
            "api_key_name": "生产 Key",
            "id": 7,
            "login": "admin",
            "display_name": "管理员",
            "platform_role": "platform_admin",
        }
    )

    result = asyncio.run(authenticate_api_key(connection, "rmk_valid"))  # type: ignore[arg-type]

    assert result is not None
    assert result["api_key_id"] == "9"
    assert connection.fetch_calls[0][2] == 9
    assert "token_used + ak.token_reserved < ak.token_limit" in connection.fetchrow_calls[0][0]
    assert "u.status = 'active'" not in connection.fetchrow_calls[0][0]


def test_revoked_key_recovers_stale_usage_before_authentication_is_rejected() -> None:
    """真实但已撤销的 Key 仍要结算遗留消费，随后保持鉴权失败。"""
    connection = FakeApiKeyConnection(
        candidate_id=9,
        row=None,
        inserted=73,
        recovery_rows=[
            {
                "run_id": 41,
                "api_key_id": 9,
                "reserved_tokens": 80,
                "tenant_id": 3,
                "assistant_message_id": 22,
                "state": "completed",
                "request_id": "11111111-1111-4111-8111-111111111111",
                "reservation_usage": {},
                "message_usage": {
                    "prompt_tokens": 30,
                    "completion_tokens": 12,
                    "total_tokens": 42,
                    "usage_source": "gateway",
                },
            }
        ],
    )

    result = asyncio.run(authenticate_api_key(connection, "rmk_revoked"))  # type: ignore[arg-type]

    assert result is None
    assert connection.fetch_calls[0][2] == 9
    assert any("INSERT INTO api_key_usage" in call[0] for call in connection.fetchval_calls)
    assert any("token_used = token_used + $2" in call[0] for call in connection.execute_calls)


def test_reservation_rejects_insufficient_remaining_quota() -> None:
    """原子 UPDATE 未命中代表额度不足，模型调用必须在此处终止。"""
    connection = FakeApiKeyConnection(row=None)

    with pytest.raises(ApiKeyQuotaExceededError):
        asyncio.run(
            reserve_api_key_tokens(  # type: ignore[arg-type]
                connection,
                api_key_id="9",
                run_id=41,
                requested_tokens=2048,
            )
        )


def test_settlement_records_input_output_and_model_breakdown() -> None:
    """单次请求结算同时写入总账和两个本地模型的分项明细。"""
    connection = FakeApiKeyConnection(inserted=1, reserved_tokens=80)
    usage = {
        "prompt_tokens": 30,
        "completion_tokens": 12,
        "total_tokens": 42,
        "usage_source": "gateway",
    }
    model_usage = {
        "embedding": {"model": "embed", "prompt_tokens": 5, "total_tokens": 5},
        "generation": {"model": "chat", "prompt_tokens": 25, "total_tokens": 37},
    }

    inserted = asyncio.run(
        settle_api_key_usage(  # type: ignore[arg-type]
            connection,
            api_key_id="9",
            run_id=41,
            tenant_id=3,
            request_id="11111111-1111-4111-8111-111111111111",
            model_name="embed + chat",
            usage=usage,
            model_usage=model_usage,
        )
    )

    assert inserted is True
    insert_args = connection.fetchval_calls[1]
    assert insert_args[5:8] == (30, 12, 42)
    assert any("token_used = token_used + $2" in call[0] for call in connection.execute_calls)


def test_duplicate_settlement_releases_reservation_without_double_charge() -> None:
    """同一 request_id 重复结算不增加 token_used，并释放重复执行产生的预扣。"""
    connection = FakeApiKeyConnection(inserted=None, reserved_tokens=20)

    inserted = asyncio.run(
        settle_api_key_usage(  # type: ignore[arg-type]
            connection,
            api_key_id="9",
            run_id=41,
            tenant_id=3,
            request_id="11111111-1111-4111-8111-111111111111",
            model_name="chat",
            usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        )
    )

    assert inserted is False
    assert len(connection.execute_calls) == 1
    assert "token_reserved = GREATEST" in connection.execute_calls[0][0]
    assert "ON CONFLICT (api_key_id, request_id)" in connection.fetchval_calls[1][0]


def test_stale_running_reservation_is_recovered_as_interrupted_failure() -> None:
    """进程中断遗留的超时运行必须释放额度，并形成可查询的失败终态。"""
    connection = FakeApiKeyConnection(
        recovery_rows=[
            {
                "run_id": 41,
                "api_key_id": 9,
                "reserved_tokens": 2048,
                "tenant_id": 3,
                "assistant_message_id": 22,
                "state": "running",
                "request_id": "11111111-1111-4111-8111-111111111111",
                "reservation_usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 3,
                    "total_tokens": 15,
                    "usage_source": "estimate",
                    "model_usage": {"generation": {"model": "chat"}},
                },
                "message_usage": {},
            }
        ]
    )

    recovered = asyncio.run(
        recover_stale_api_key_reservations(  # type: ignore[arg-type]
            connection,
            api_key_id=9,
        )
    )

    assert recovered == 1
    assert "make_interval(mins => $1)" in connection.fetch_calls[0][0]
    assert any("DELETE FROM api_key_reservations" in call[0] for call in connection.execute_calls)
    assert any("token_reserved = GREATEST" in call[0] for call in connection.execute_calls)
    assert any("token_used = token_used + $2" in call[0] for call in connection.execute_calls)
    assert any("PROCESS_INTERRUPTED" in str(call) for call in connection.execute_calls)
    assert any(
        "UPDATE retrieval_traces SET state = 'failed'" in call[0]
        for call in connection.execute_calls
    )


def test_fresh_reservations_are_not_recovered() -> None:
    """恢复查询没有返回未超时运行时，不得释放任何仍有效的额度预留。"""
    connection = FakeApiKeyConnection()

    recovered = asyncio.run(
        recover_stale_api_key_reservations(  # type: ignore[arg-type]
            connection,
            api_key_id=9,
        )
    )

    assert recovered == 0
    assert connection.execute_calls == []


def test_missing_persisted_reservation_never_releases_other_running_quota() -> None:
    """恢复已删除本运行预留时，迟到结算只能记实际用量，不能再减聚合预留。"""
    connection = FakeApiKeyConnection(inserted=1, reserved_tokens=None)

    inserted = asyncio.run(
        settle_api_key_usage(  # type: ignore[arg-type]
            connection,
            api_key_id="9",
            run_id=41,
            tenant_id=3,
            request_id="11111111-1111-4111-8111-111111111111",
            model_name="chat",
            usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        )
    )

    assert inserted is True
    quota_update = next(
        call for call in connection.execute_calls if "token_used = token_used + $2" in call[0]
    )
    assert quota_update[1:] == (9, 7, 0)


def test_completed_run_recovery_uses_message_usage_for_final_charge() -> None:
    """回答已完成但结算前崩溃时，恢复必须用消息中的最终 usage 补记真实消费。"""
    connection = FakeApiKeyConnection(
        inserted=73,
        recovery_rows=[
            {
                "run_id": 41,
                "api_key_id": 9,
                "reserved_tokens": 80,
                "tenant_id": 3,
                "assistant_message_id": 22,
                "state": "completed",
                "request_id": "11111111-1111-4111-8111-111111111111",
                "reservation_usage": {},
                "message_usage": {
                    "prompt_tokens": 30,
                    "completion_tokens": 12,
                    "total_tokens": 42,
                    "usage_source": "gateway",
                    "model_usage": {"generation": {"model": "chat"}},
                },
            }
        ],
    )

    recovered = asyncio.run(
        recover_stale_api_key_reservations(  # type: ignore[arg-type]
            connection,
            api_key_id=9,
        )
    )

    assert recovered == 1
    usage_insert = next(
        call for call in connection.fetchval_calls if "INSERT INTO api_key_usage" in call[0]
    )
    assert usage_insert[5:8] == (30, 12, 42)
    assert usage_insert[-1] == "completed"
    assert not any("PROCESS_INTERRUPTED" in str(call) for call in connection.execute_calls)


def test_combined_usage_counts_embedding_as_input_and_generation_as_output() -> None:
    """额度口径把嵌入与生成输入相加，输出只来自生成模型。"""
    usage, breakdown, names = _combined_usage(
        embedding_usage={
            "prompt_tokens": 6,
            "completion_tokens": 0,
            "total_tokens": 6,
            "usage_source": "gateway",
        },
        embedding_model="embed",
        generation_usage={
            "prompt_tokens": 20,
            "completion_tokens": 8,
            "total_tokens": 28,
            "usage_source": "gateway",
        },
        generation_model="chat",
    )

    assert usage == {
        "prompt_tokens": 26,
        "completion_tokens": 8,
        "total_tokens": 34,
        "usage_source": "gateway",
        "model_usage": breakdown,
    }
    assert names == "embed + chat"


def test_bearer_key_cannot_call_admin_model_configuration(monkeypatch: Any) -> None:
    """API Key 即使由超级管理员创建，也不能继承模型管理接口权限。"""
    context = {
        "user": {"id": "7", "platform_role": None},
        "api_key_id": "9",
        "api_key_tenant_id": "3",
    }
    monkeypatch.setattr("app.main.load_user_from_token", AsyncMock(return_value=None))
    monkeypatch.setattr("app.main.load_user_from_api_key", AsyncMock(return_value=context))

    with TestClient(create_app(Settings(database_url="postgresql://unused"))) as client:
        response = client.get(
            "/api/v1/model-endpoints",
            headers={"Authorization": "Bearer rmk_test"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "API Key 只能调用知识问答接口"


def test_explicit_bearer_key_takes_precedence_over_admin_cookie(monkeypatch: Any) -> None:
    """显式 Bearer 必须决定调用身份，不能被浏览器管理员 Cookie 绕过 Key 限制。"""
    cookie_loader = AsyncMock(
        return_value={"user": {"id": "1", "platform_role": "platform_admin"}}
    )
    key_loader = AsyncMock(
        return_value={
            "user": {"id": "7", "platform_role": None},
            "api_key_id": "9",
            "api_key_tenant_id": "3",
        }
    )
    monkeypatch.setattr("app.main.load_user_from_token", cookie_loader)
    monkeypatch.setattr("app.main.load_user_from_api_key", key_loader)

    with TestClient(create_app(Settings(database_url="postgresql://unused"))) as client:
        client.cookies.set(SESSION_COOKIE, "admin-cookie")
        response = client.get(
            "/api/v1/model-endpoints",
            headers={"Authorization": "Bearer rmk_customer"},
        )

    assert response.status_code == 403
    key_loader.assert_awaited_once()
    cookie_loader.assert_not_awaited()


def test_platform_admin_creates_one_time_key_without_persisting_plaintext(monkeypatch: Any) -> None:
    """创建接口仅在响应中返回明文，数据库插入和审计参数均不得包含明文。"""
    connection = FakeManagementConnection()
    context = {"user": {"id": "7", "platform_role": "platform_admin"}}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/api-keys",
            json={"tenant_id": 3, "name": "生产 Key", "token_limit": 1000},
        )

    assert response.status_code == 201
    raw_key = response.json()["raw_key"]
    assert raw_key.startswith("sk-")
    assert response.json()["token_remaining"] == 1000
    tenant_lookup_index = next(
        index
        for index, call in enumerate(connection.calls)
        if "SELECT name FROM tenants" in call[0]
    )
    insert_index = next(
        index for index, call in enumerate(connection.calls) if "INSERT INTO api_keys" in call[0]
    )
    assert tenant_lookup_index < insert_index
    assert all(raw_key not in str(call) for call in connection.calls)
    assert connection.closed


def test_api_key_knowledge_base_access_is_strictly_tenant_bound() -> None:
    """Key 访问知识库时只使用绑定租户，不依赖创建者成员关系且不能跨租户。"""
    connection = FakeApiKeyConnection(
        row={"id": 4, "tenant_id": 3, "name": "知识库", "active_release_id": 8}
    )
    context = {"user": {"id": "7"}, "api_key_tenant_id": "3"}

    result = asyncio.run(
        _knowledge_base_access(connection, context, 4)  # type: ignore[arg-type]
    )

    assert result["tenant_id"] == 3
    query, knowledge_base_id, tenant_id = connection.fetchrow_calls[0]
    assert "kb.tenant_id = $2" in query
    assert (knowledge_base_id, tenant_id) == (4, 3)


def test_usage_endpoint_returns_full_aggregate_and_recent_rows(monkeypatch: Any) -> None:
    """超过 200 条流水时，摘要仍使用数据库全量聚合而不是最近列表求和。"""
    connection = FakeUsageConnection()
    monkeypatch.setattr(
        "app.main._authenticated_user",
        AsyncMock(return_value={"user": {"id": "7", "platform_role": "platform_admin"}}),
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/v1/api-keys/9/usage")

    assert response.status_code == 200
    assert response.json()["summary"] == {
        "request_count": 350,
        "prompt_tokens": 2600,
        "completion_tokens": 900,
        "total_tokens": 3500,
    }
    assert len(response.json()["items"]) == 1
    assert response.json()["recent_limit"] == 200
    assert connection.closed
