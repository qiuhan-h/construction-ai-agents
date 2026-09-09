"""全局配置（Pydantic Settings）。

优先级（从高到低）：
1. 进程环境变量 / .env 文件
2. 分环境 YAML 覆盖（config/environments/{app_env}.yaml）
3. 代码内默认值

使用方式：
    from config import get_settings
    settings = get_settings()

⚠️ 安全说明：所有外部地址 / 凭据占位统一为 "需要补充实际链接"。
  - 涉及真实 IP / 端口 / 用户名 / 密码 / Token / Key 的位置均不得直接提交；
  - 占位说明仅描述填写格式与示例，不含真实凭据；
  - 生产环境应通过 K8s Secret / Vault 等外部注入，不写进 .env 或本文件。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CONFIG_DIR.parent

logger = logging.getLogger(__name__)

# 已知占位密钥常量：用于检测 api_jwt_secret 仍为代码默认值（fail-fast 警告）
_DEFAULT_JWT_SECRET_PLACEHOLDER = "需要补充实际链接"


# =====================================================
# 占位说明速查（所有占位均为字符串 "需要补充实际链接"）
# =====================================================
# API_HOST      API 监听地址，例 "0.0.0.0"（监听所有网卡）或具体内网 IP
# DATABASE_URL  PostgreSQL SQLAlchemy 连接串
#               格式: postgresql+psycopg://<user>:<password>@<host>:<port>/<database>
#               例:   postgresql+psycopg://app:YourPwd@10.0.0.10:5432/construction_agents
# REDIS_URL     Redis 缓存地址
#               格式: redis://[:<password>@]<host>:<port>/<db>
#               例:   redis://:YourPwd@10.0.0.20:6379/0
# CELERY_BROKER_URL        Celery Broker（一般指向 Redis db 1）
# CELERY_RESULT_BACKEND    Celery 结果后端（一般指向 Redis db 2）
# TSDB_URL        InfluxDB 2.x HTTP 地址
#                 格式: http://<host>:<port>  或  https://<host>:<port>
#                 例:   http://10.0.0.30:8086
# TSDB_TOKEN      InfluxDB API Token（需含读/写目标 bucket 的权限）
# TSDB_ORG        InfluxDB 组织名（创建时确定）
# TSDB_BUCKET     InfluxDB 桶名（建议按租户/环境分桶）
# LLM_API_KEY     任意 OpenAI 兼容服务的 API Key（dashscope / openai / 自建）
# LLM_BASE_URL    OpenAI 兼容服务基址（不含 /chat/completions）
#                 格式: https://<host>/<path-prefix>  或  http://<host>:<port>/v1
# LLM_DEFAULT_MODEL
#                 默认模型名，例 "qwen-plus" / "gpt-4o-mini" / "your-model"
# API_JWT_SECRET  JWT 签名密钥（HS256），建议 32 字节以上随机串
# =====================================================


class Settings(BaseSettings):
    """平台全局配置。字段名与环境变量一一对应（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- 应用 ----------
    app_env: Literal["dev", "staging", "prod"] = Field(default="dev", description="运行环境")
    # 占位：API 监听地址。填写内容：内网 IP / 0.0.0.0；示例 "0.0.0.0"
    api_host: str = Field(default="需要补充实际链接", description="API 监听地址")
    api_port: int = Field(default=8000, ge=1, le=65535, description="API 监听端口")
    log_level: str = Field(default="INFO", description="根日志级别")

    # ---------- 存储（所有连接串/凭据均需在 .env 中填写实际值） ----------
    # 占位：PostgreSQL SQLAlchemy 连接串。格式 postgresql+psycopg://<user>:<password>@<host>:<port>/<db>
    database_url: str = Field(
        default="需要补充实际链接",
        description="PostgreSQL 连接串（SQLAlchemy 格式），例如 postgresql+psycopg://user:pass@host:5432/db",
    )
    # 占位：Redis 地址。格式 redis://[:<password>@]<host>:<port>/<db>
    redis_url: str = Field(default="需要补充实际链接", description="Redis 缓存地址")
    # 占位：Celery Broker，建议与 REDIS_URL 共享实例但用不同 db
    celery_broker_url: str = Field(default="需要补充实际链接", description="Celery Broker")
    # 占位：Celery 结果后端，建议 db 2
    celery_result_backend: str = Field(default="需要补充实际链接", description="Celery 结果后端")

    # ---------- 时序库（传感器高频数据） ----------
    # 占位：InfluxDB 2.x HTTP 地址。格式 http://<host>:<port> 或 https://<host>:<port>
    tsdb_url: str = Field(default="需要补充实际链接", description="InfluxDB 2.x 地址")
    # 占位：InfluxDB API Token（写入 / 读取目标 bucket 的权限），示例形如 "AbCdEf...=="
    tsdb_token: SecretStr = Field(default=SecretStr(""), description="InfluxDB Token（需在 .env 填写）")
    # 占位：InfluxDB 组织名（创建时确定），示例 "construction"
    tsdb_org: str = Field(default="需要补充实际链接", description="InfluxDB 组织")
    # 占位：InfluxDB 桶名，建议按租户/环境分桶，示例 "sensor_data_dev"
    tsdb_bucket: str = Field(default="需要补充实际链接", description="InfluxDB 桶")

    # ---------- LLM 接入（OpenAI 兼容接口） ----------
    # 占位：LLM API Key（dashscope / openai / 自建 等的访问密钥）
    llm_api_key: SecretStr = Field(default=SecretStr(""), description="LLM API Key（需在 .env 填写，禁止入库）")
    # 占位：OpenAI 兼容服务基址（不含 /chat/completions）。格式 https://<host>/<prefix> 或 http://<host>:<port>/v1
    llm_base_url: str = Field(
        default="需要补充实际链接",
        description="OpenAI 兼容服务地址（需在 .env 填写）",
    )
    # 占位：默认模型名，示例 "qwen-plus" / "gpt-4o-mini" / "your-fine-tuned-model"
    llm_default_model: str = Field(default="需要补充实际链接", description="默认模型")
    llm_timeout: float = Field(default=120.0, gt=0, description="单次请求超时（秒）")
    llm_max_retries: int = Field(default=3, ge=0, description="失败重试次数")
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0, description="默认采样温度")
    llm_max_tokens: int = Field(default=4096, gt=0, description="单次输出最大 token")
    # LLM 提供方：mock（默认，FakeListLLM 占位）/ openai / anthropic / vllm
    # mock 不产生真实调用；openai/vllm 走 OpenAI 兼容接口，anthropic 走 Anthropic 接口
    llm_provider: Literal["mock", "openai", "anthropic", "vllm"] = Field(
        default="mock", description="LLM 提供方，mock=本地占位不产生真实调用"
    )

    # ---------- 认证 ----------
    # 占位：JWT HS256 签名密钥。建议 32 字节以上随机串，例 `python -c "import secrets;print(secrets.token_urlsafe(48))"`
    api_jwt_secret: SecretStr = Field(default=SecretStr("需要补充实际链接"), description="JWT 签名密钥（需在 .env 填写）")

    # ---------- BIM (Autodesk Platform Services) ----------
    # 7a-1: APS 凭据，缺省降级 mock；生产须在 .env 填写真实值
    aps_client_id: str = Field(default="", description="APS 应用 Client ID")
    aps_client_secret: SecretStr = Field(default=SecretStr(""), description="APS Client Secret")
    aps_hub_id: str = Field(default="", description="APS Hub ID")
    aps_project_id: str = Field(default="", description="APS Project ID")

    # ---------- IoT (MQTT) ----------
    mqtt_broker: str = Field(default="", description="MQTT Broker 地址；空则降级 mock")
    mqtt_port: int = Field(default=1883, ge=1, le=65535, description="MQTT Broker 端口")

    @field_validator("mqtt_port", mode="before")
    @classmethod
    def _empty_mqtt_port_default(cls, v: Any) -> Any:
        """空字符串（.env 中 MQTT_PORT= 留空）回退默认 1883，避免 int 解析失败。"""
        if v is None or (isinstance(v, str) and not v.strip()):
            return 1883
        return v

    # ---------- 内嵌应用（钉钉 ISV / 企微自建应用） ----------
    dingtalk_corp_id: str = Field(default="", description="钉钉企业 CorpId")
    dingtalk_app_key: str = Field(default="", description="钉钉应用 AppKey")
    dingtalk_app_secret: SecretStr = Field(default=SecretStr(""), description="钉钉应用 AppSecret")
    dingtalk_agent_id: str = Field(default="", description="钉钉应用 AgentId")
    wecom_corp_id: str = Field(default="", description="企微企业 CorpID")
    wecom_secret: SecretStr = Field(default=SecretStr(""), description="企微自建应用 Secret")
    wecom_agent_id: str = Field(default="", description="企微自建应用 AgentId")

    # ---------- 通知渠道（群机器人 webhook + 短信；空则自动降级 mock） ----------
    # 7b 接线：NotificationService 默认渠道工厂按这些字段自动选择 Real / Mock 通道
    dingtalk_webhook: str = Field(default="", description="钉钉机器人 Webhook URL")
    dingtalk_secret: SecretStr = Field(default=SecretStr(""), description="钉钉机器人加签密钥（SEC 开头，可选）")
    wecom_webhook: str = Field(default="", description="企微机器人 Webhook URL")
    # 阿里云短信（5 项齐全才启用真实通道）
    aliyun_sms_access_key_id: str = Field(default="", description="阿里云短信 AccessKey ID")
    aliyun_sms_access_key_secret: SecretStr = Field(default=SecretStr(""), description="阿里云短信 AccessKey Secret")
    aliyun_sms_sign_name: str = Field(default="", description="阿里云短信签名")
    aliyun_sms_template_code: str = Field(default="", description="阿里云短信模板 ID（SMS_ 开头）")
    aliyun_sms_phone: str = Field(default="", description="阿里云短信默认接收手机号（11 位）")
    # 腾讯云短信（6 项齐全才启用真实通道）
    tencent_sms_secret_id: str = Field(default="", description="腾讯云短信 SecretId")
    tencent_sms_secret_key: SecretStr = Field(default=SecretStr(""), description="腾讯云短信 SecretKey")
    tencent_sms_app_id: str = Field(default="", description="腾讯云短信 AppId（1400 开头）")
    tencent_sms_sign_name: str = Field(default="", description="腾讯云短信签名")
    tencent_sms_template_id: str = Field(default="", description="腾讯云短信模板 ID")
    tencent_sms_phone: str = Field(default="", description="腾讯云短信默认接收手机号（11 位）")

    # ---------- 安全加固（7a-5）----------
    # CORS 白名单：逗号分隔域名，如 "https://app.example.com,https://admin.example.com"
    # 空字符串表示禁止跨域；"*" 表示允许全部（仅 dev 使用）
    cors_origins: str = Field(default="", description="CORS 白名单（逗号分隔域名）")

    @model_validator(mode="after")
    def _warn_default_jwt_secret(self) -> Settings:
        # fail-fast 警告：api_jwt_secret 仍为代码默认占位值时仅记日志（不抛错，
        # 避免阻塞本地开发 / 测试）。生产环境应通过 .env / K8s Secret 注入真实密钥。
        try:
            secret_val = self.api_jwt_secret.get_secret_value()
        except Exception:  # noqa: BLE001
            secret_val = ""
        if not secret_val or secret_val == _DEFAULT_JWT_SECRET_PLACEHOLDER:
            logger.warning(
                "api_jwt_secret 仍为默认占位值（%r），生产环境存在签名密钥泄露风险；"
                "请在 .env 设置 API_JWT_SECRET 为 32 字节以上随机串。",
                _DEFAULT_JWT_SECRET_PLACEHOLDER,
            )
        return self

    # ---------- 派生路径 ----------
    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    @property
    def data_dir(self) -> Path:
        return PROJECT_ROOT / "data"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"


def load_env_overrides(app_env: str) -> dict[str, Any]:
    """读取分环境 YAML 覆盖；文件不存在时返回空字典。"""
    path = CONFIG_DIR / "environments" / f"{app_env}.yaml"
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"环境配置格式错误（应为映射）: {path}")
    # 只保留 Settings 中已定义的字段，忽略未知键
    known = set(Settings.model_fields)
    return {k: v for k, v in data.items() if k in known}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取全局配置单例。

    环境变量 / .env 优先于分环境 YAML：仅当字段未被环境变量显式设置时，
    才应用 YAML 中的覆盖值。
    """
    base = Settings()
    overrides = load_env_overrides(base.app_env)
    env_provided = base.model_fields_set
    apply = {k: v for k, v in overrides.items() if k not in env_provided}
    return base.model_copy(update=apply) if apply else base


def reload_settings() -> Settings:
    """清空缓存并重新加载（测试与配置热更新使用）。"""
    get_settings.cache_clear()
    return get_settings()
