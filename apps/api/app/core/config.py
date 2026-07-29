from functools import lru_cache
from urllib.parse import urlparse

from pydantic import AliasChoices, EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_MARKERS = ("change_me", "dev_only")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        extra="ignore",
        populate_by_name=True,
    )

    app_env: str = "development"
    web_origin: str = "http://localhost:5173"
    web_extra_origins: str = Field(default="", validation_alias="WEB_EXTRA_ORIGINS")
    api_origin: str = "http://localhost:8000"

    database_url: str = "postgresql+asyncpg://nur_app:change_me@localhost:5432/nur"
    alembic_database_url: str | None = None  # schema-owner role; migrations only
    redis_url: str = "redis://localhost:6379/0"
    # Prefix for every Redis key this process owns. Empty in production, where the
    # instance is not shared. Test runs set a unique namespace so two concurrent
    # invocations cannot read, increment, or delete each other's limiter state.
    redis_key_namespace: str = Field(default="", validation_alias="NUR_REDIS_KEY_NAMESPACE")

    session_secret: str = "dev_only_change_me"
    csrf_secret: str = "dev_only_change_me"

    session_cookie_name: str = "nur_session"
    csrf_cookie_name: str = "nur_csrf"
    session_ttl_seconds: int = 60 * 60 * 24 * 14  # 14 days

    login_rate_limit_max: int = 10
    login_rate_limit_window_seconds: int = 300
    register_rate_limit_max: int = 10
    register_rate_limit_window_seconds: int = 300
    password_forgot_rate_limit_max: int = 5
    password_forgot_rate_limit_window_seconds: int = 900
    password_reset_rate_limit_max: int = 10
    password_reset_rate_limit_window_seconds: int = 900
    password_change_rate_limit_max: int = 5
    password_change_rate_limit_window_seconds: int = 900

    # Account recovery. Local capture writes a mode-0600 development artifact;
    # production must use the SMTP adapter and an HTTPS reset origin.
    password_reset_ttl_seconds: int = Field(default=900, ge=300, le=3600)
    password_reset_delivery: str = "local_capture"
    password_reset_public_origin: str = ""
    password_reset_local_capture_dir: str = ".nur-runtime/mail"
    password_reset_from_email: EmailStr | None = None
    password_reset_smtp_host: str = ""
    password_reset_smtp_port: int = Field(default=587, ge=1, le=65535)
    password_reset_smtp_starttls: bool = True
    password_reset_smtp_username: str = ""
    password_reset_smtp_password: SecretStr | None = None

    # AI gateway: server-side only. Keys never cross to the web client.
    ai_provider: str = Field(default="disabled", validation_alias=AliasChoices("NUR_AI_PROVIDER", "AI_PROVIDER"))
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="", validation_alias=AliasChoices("NUR_OPENAI_MODEL", "OPENAI_MODEL"))
    openai_embedding_model: str = Field(default="", validation_alias=AliasChoices("NUR_OPENAI_EMBEDDING_MODEL", "OPENAI_EMBEDDING_MODEL"))
    openai_reasoning_effort: str = Field(default="high", validation_alias="NUR_OPENAI_REASONING_EFFORT")
    openai_critical_reasoning_effort: str = Field(default="high", validation_alias="NUR_OPENAI_CRITICAL_REASONING_EFFORT")
    openai_request_timeout_seconds: int = Field(default=45, validation_alias="NUR_OPENAI_REQUEST_TIMEOUT_SECONDS")
    ai_per_user_daily_limit: int = Field(default=50, validation_alias="NUR_AI_PER_USER_DAILY_LIMIT")
    ai_daily_budget_cents: int = Field(default=500, validation_alias="NUR_AI_DAILY_BUDGET_CENTS")
    ai_allow_external_web_research: bool = Field(default=False, validation_alias="NUR_AI_ALLOW_EXTERNAL_WEB_RESEARCH")
    ai_log_prompts: bool = Field(default=False, validation_alias="NUR_AI_LOG_PROMPTS")
    demo_mode: bool = Field(default=False, validation_alias="DEMO_MODE")

    # Billing is server-side and disabled by default. `test` is a deterministic
    # local adapter; Lemon Squeezy is the first merchant-of-record boundary.
    billing_provider: str = Field(default="disabled", validation_alias="NUR_BILLING_PROVIDER")
    billing_test_mode: bool = Field(default=True, validation_alias="NUR_BILLING_TEST_MODE")
    billing_live_enabled: bool = Field(default=False, validation_alias="NUR_BILLING_LIVE_ENABLED")
    billing_webhook_secret: SecretStr | None = Field(
        default=None, validation_alias="NUR_BILLING_WEBHOOK_SECRET"
    )
    billing_checkout_reservation_minutes: int = Field(
        default=30,
        ge=5,
        le=120,
        validation_alias="NUR_BILLING_CHECKOUT_RESERVATION_MINUTES",
    )
    billing_past_due_grace_days: int = Field(
        default=3, ge=0, le=30, validation_alias="NUR_BILLING_PAST_DUE_GRACE_DAYS"
    )
    billing_terms_url: str = Field(default="", validation_alias="NUR_BILLING_TERMS_URL")
    billing_privacy_url: str = Field(default="", validation_alias="NUR_BILLING_PRIVACY_URL")
    billing_refund_policy_url: str = Field(
        default="", validation_alias="NUR_BILLING_REFUND_POLICY_URL"
    )
    lemon_squeezy_api_key: SecretStr | None = Field(
        default=None, validation_alias="LEMON_SQUEEZY_API_KEY"
    )
    lemon_squeezy_store_id: str = Field(default="", validation_alias="LEMON_SQUEEZY_STORE_ID")
    lemon_squeezy_founding_orbit_variant_id: str = Field(
        default="", validation_alias="LEMON_SQUEEZY_FOUNDING_ORBIT_VARIANT_ID"
    )
    lemon_squeezy_plus_monthly_variant_id: str = Field(
        default="", validation_alias="LEMON_SQUEEZY_PLUS_MONTHLY_VARIANT_ID"
    )
    lemon_squeezy_plus_annual_variant_id: str = Field(
        default="", validation_alias="LEMON_SQUEEZY_PLUS_ANNUAL_VARIANT_ID"
    )

    # AM Projects execution + storage (G14). The object store is local-first and
    # owner-scoped; bytes live outside the web root and are never client-addressed.
    # An external object-cloud backend can be added behind the same adapter later.
    project_object_root: str = Field(
        default=".nur-runtime/project-objects", validation_alias="NUR_PROJECT_OBJECT_ROOT"
    )
    project_upload_max_bytes: int = Field(
        default=25 * 1024 * 1024, ge=1, validation_alias="NUR_PROJECT_UPLOAD_MAX_BYTES"
    )
    # Per-owner total stored bytes across all projects. A per-file cap alone lets
    # an owner grow storage without bound one small file at a time; this bounds
    # the sum. Enforced at upload against the owner's real stored total.
    project_storage_quota_bytes: int = Field(
        default=1024 * 1024 * 1024, ge=1, validation_alias="NUR_PROJECT_STORAGE_QUOTA_BYTES"
    )
    # Per-owner upload rate limit (a hot, expensive write path beyond auth).
    upload_rate_limit_max: int = Field(
        default=60, ge=1, validation_alias="NUR_UPLOAD_RATE_LIMIT_MAX"
    )
    upload_rate_limit_window_seconds: int = Field(
        default=60, ge=1, validation_alias="NUR_UPLOAD_RATE_LIMIT_WINDOW_SECONDS"
    )
    project_run_timeout_seconds: int = Field(
        default=120, ge=1, le=1800, validation_alias="NUR_PROJECT_RUN_TIMEOUT_SECONDS"
    )
    # Queue recovery. A run left RUNNING longer than this — a worker that crashed
    # mid-run — is stale and gets requeued, or dead-lettered once it has burned
    # through its attempts so it cannot retry forever.
    run_stale_after_seconds: int = Field(
        default=900, ge=1, validation_alias="NUR_PROJECT_RUN_STALE_AFTER_SECONDS"
    )
    run_max_attempts: int = Field(
        default=5, ge=1, validation_alias="NUR_PROJECT_RUN_MAX_ATTEMPTS"
    )
    # Deterministic adapters run in-process during tests and local smoke; production
    # dispatches them onto the Celery queue. This never enables provider-backed AI runs.
    project_run_inline: bool = Field(default=False, validation_alias="NUR_PROJECT_RUN_INLINE")

    # Omega research layer: owner-only, disabled for public UI unless the web
    # bundle flag is also enabled. The scheduler carries owner IDs only.
    omega_enabled: bool = Field(default=True, validation_alias="NUR_OMEGA_ENABLED")
    omega_scheduled_consolidation: bool = Field(default=True, validation_alias="NUR_OMEGA_SCHEDULED_CONSOLIDATION")
    omega_consolidation_interval_hours: int = Field(default=24, validation_alias="NUR_OMEGA_CONSOLIDATION_INTERVAL_HOURS")
    omega_max_experiences_per_run: int = Field(default=100, validation_alias="NUR_OMEGA_MAX_EXPERIENCES_PER_RUN")

    # Agency Plane background loops. The dispatcher drains committed outbox
    # intents onto the queue; recovery reclaims abandoned step leases. Both are
    # Celery Beat entries rather than manual invocations, and both are safe to
    # run at any interval because each claim is a fenced conditional UPDATE.
    agentic_dispatch_enabled: bool = Field(default=True, validation_alias="NUR_AGENTIC_DISPATCH_ENABLED")
    agentic_dispatch_interval_seconds: int = Field(default=5, validation_alias="NUR_AGENTIC_DISPATCH_INTERVAL_SECONDS")
    agentic_recovery_interval_seconds: int = Field(default=60, validation_alias="NUR_AGENTIC_RECOVERY_INTERVAL_SECONDS")
    agentic_dispatch_batch: int = Field(default=20, validation_alias="NUR_AGENTIC_DISPATCH_BATCH")
    # Hard ceiling on one handler's execution, strictly shorter than the step
    # lease so a hung handler fails and becomes recoverable rather than holding
    # a lease that recovery would then reclaim underneath a live worker.
    agentic_step_timeout_seconds: int = Field(default=120, validation_alias="NUR_AGENTIC_STEP_TIMEOUT_SECONDS")

    @field_validator("ai_provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        v = value.lower().strip()
        if v not in {"disabled", "openai"}:
            raise ValueError("NUR_AI_PROVIDER must be 'disabled' or 'openai'.")
        return v

    @field_validator("billing_provider")
    @classmethod
    def _known_billing_provider(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"disabled", "test", "lemon_squeezy"}:
            raise ValueError(
                "NUR_BILLING_PROVIDER must be 'disabled', 'test', or 'lemon_squeezy'."
            )
        return normalized

    @field_validator("password_reset_delivery")
    @classmethod
    def _known_password_reset_delivery(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"disabled", "local_capture", "smtp"}:
            raise ValueError("PASSWORD_RESET_DELIVERY must be 'disabled', 'local_capture', or 'smtp'.")
        return normalized

    @model_validator(mode="after")
    def _no_decorative_secrets_in_production(self) -> "Settings":
        """SESSION_SECRET keys session-token HMACs; CSRF_SECRET keys CSRF tokens.
        They are load-bearing, so production refuses placeholders outright."""
        if self.app_env == "production":
            for name in ("session_secret", "csrf_secret"):
                value = getattr(self, name)
                if len(value) < 32 or any(m in value for m in _PLACEHOLDER_MARKERS):
                    raise ValueError(
                        f"{name.upper()} must be a real secret (>=32 chars, no placeholder text) "
                        "when APP_ENV=production."
                    )
        if self.ai_provider == "openai":
            if self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip():
                raise ValueError("NUR_AI_PROVIDER=openai requires OPENAI_API_KEY in the server environment.")
            if not self.openai_model.strip():
                raise ValueError("NUR_AI_PROVIDER=openai requires NUR_OPENAI_MODEL in the server environment.")
        if self.ai_allow_external_web_research:
            raise ValueError("NUR_AI_ALLOW_EXTERNAL_WEB_RESEARCH must remain false for this readiness gate.")
        if self.billing_provider == "test":
            if self.app_env == "production":
                raise ValueError("The deterministic billing test provider cannot run in production.")
            if not self.billing_test_mode:
                raise ValueError("The deterministic billing provider requires NUR_BILLING_TEST_MODE=true.")
        if self.billing_provider != "disabled":
            if (
                self.billing_webhook_secret is None
                or len(self.billing_webhook_secret.get_secret_value().strip()) < 24
            ):
                raise ValueError(
                    "Enabled billing requires NUR_BILLING_WEBHOOK_SECRET with at least 24 characters."
                )
            webhook_secret = self.billing_webhook_secret.get_secret_value().lower()
            if any(marker in webhook_secret for marker in _PLACEHOLDER_MARKERS):
                raise ValueError("NUR_BILLING_WEBHOOK_SECRET cannot be a placeholder.")
        if self.billing_provider == "lemon_squeezy":
            if (
                self.lemon_squeezy_api_key is None
                or not self.lemon_squeezy_api_key.get_secret_value().strip()
            ):
                raise ValueError("Lemon Squeezy billing requires LEMON_SQUEEZY_API_KEY.")
            required_values = {
                "LEMON_SQUEEZY_STORE_ID": self.lemon_squeezy_store_id,
                "LEMON_SQUEEZY_FOUNDING_ORBIT_VARIANT_ID": (
                    self.lemon_squeezy_founding_orbit_variant_id
                ),
                "LEMON_SQUEEZY_PLUS_MONTHLY_VARIANT_ID": (
                    self.lemon_squeezy_plus_monthly_variant_id
                ),
                "LEMON_SQUEEZY_PLUS_ANNUAL_VARIANT_ID": (
                    self.lemon_squeezy_plus_annual_variant_id
                ),
                "NUR_BILLING_TERMS_URL": self.billing_terms_url,
                "NUR_BILLING_PRIVACY_URL": self.billing_privacy_url,
                "NUR_BILLING_REFUND_POLICY_URL": self.billing_refund_policy_url,
            }
            missing = [name for name, value in required_values.items() if not value.strip()]
            if missing:
                raise ValueError(
                    "Lemon Squeezy billing is missing required server configuration: "
                    + ", ".join(missing)
                )
            variant_ids = self.lemon_squeezy_variants.values()
            if any(not value.isdigit() for value in variant_ids):
                raise ValueError("Lemon Squeezy variant IDs must be numeric.")
            legal_urls = (
                self.billing_terms_url,
                self.billing_privacy_url,
                self.billing_refund_policy_url,
            )
            parsed_legal_urls = [urlparse(value) for value in legal_urls]
            if any(
                parsed.scheme != "https"
                or not parsed.netloc
                or parsed.username
                or parsed.password
                for parsed in parsed_legal_urls
            ):
                raise ValueError("Billing legal URLs must use HTTPS.")
        if (
            self.billing_provider != "disabled"
            and not self.billing_test_mode
            and not self.billing_live_enabled
        ):
            raise ValueError(
                "Live billing requires the explicit NUR_BILLING_LIVE_ENABLED=true gate."
            )
        if self.password_reset_origin not in self.cors_origins:
            raise ValueError("PASSWORD_RESET_PUBLIC_ORIGIN must be one of the configured web origins.")
        if self.password_reset_delivery == "smtp":
            if not self.password_reset_smtp_host.strip() or self.password_reset_from_email is None:
                raise ValueError("SMTP password reset delivery requires SMTP_HOST and PASSWORD_RESET_FROM_EMAIL.")
            has_username = bool(self.password_reset_smtp_username.strip())
            has_password = bool(
                self.password_reset_smtp_password
                and self.password_reset_smtp_password.get_secret_value().strip()
            )
            if has_username != has_password:
                raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must either both be set or both be absent.")
        if self.app_env == "production":
            if self.password_reset_delivery != "smtp":
                raise ValueError("Production requires PASSWORD_RESET_DELIVERY=smtp.")
            if not self.password_reset_origin.startswith("https://"):
                raise ValueError("Production password reset links require an HTTPS origin.")
        return self

    @property
    def cookies_secure(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins(self) -> list[str]:
        origins = {self.web_origin.rstrip("/")}
        for value in self.web_extra_origins.split(","):
            origin = value.strip().rstrip("/")
            if origin:
                origins.add(origin)
        if self.app_env != "production":
            origins.update({"http://localhost:4173", "http://127.0.0.1:4173"})
        return sorted(origins)

    @property
    def password_reset_origin(self) -> str:
        return (self.password_reset_public_origin or self.web_origin).rstrip("/")

    @property
    def lemon_squeezy_variants(self) -> dict[str, str]:
        return {
            "founding_orbit": self.lemon_squeezy_founding_orbit_variant_id,
            "nur_plus_monthly": self.lemon_squeezy_plus_monthly_variant_id,
            "nur_plus_annual": self.lemon_squeezy_plus_annual_variant_id,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
