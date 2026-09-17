"""G02 邮件服务测试：模板渲染、模拟发送、日志落库、SMTP 发送（mock）。"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("APP_ENV", "test")
os.environ["EMBEDDING_MODEL"] = "hash"

import pytest  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.email_log import EmailLog  # noqa: E402
from app.services import email_service  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


@pytest.fixture
def db_session():
    """内存 SQLite 测试会话。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


class TestTemplateRendering:
    """模板渲染测试。"""

    def test_render_verify_email(self):
        """验证邮件模板渲染包含用户名和链接。"""
        html, text = email_service._render(
            "verify_email",
            {"username": "testuser", "verify_url": "https://example.com/verify?token=abc123"},
        )
        assert "testuser" in html
        assert "https://example.com/verify?token=abc123" in html
        assert "testuser" in text
        assert "https://example.com/verify?token=abc123" in text

    def test_render_password_reset(self):
        """密码重置模板渲染包含重置链接。"""
        html, text = email_service._render(
            "password_reset",
            {"username": "testuser", "reset_url": "https://example.com/reset?token=xyz789"},
        )
        assert "testuser" in html
        assert "https://example.com/reset?token=xyz789" in html
        assert "1 小时" in text

    def test_render_login_alert(self):
        """异常登录提醒模板渲染包含详情。"""
        html, text = email_service._render(
            "login_alert",
            {
                "username": "testuser",
                "alert_detail": "连续 5 次密码错误",
                "alert_time": "2026-09-17 10:00:00",
                "ip_address": "192.168.1.1",
            },
        )
        assert "testuser" in html
        assert "连续 5 次密码错误" in html
        assert "192.168.1.1" in text

    def test_render_system_notice(self):
        """系统通知模板渲染包含标题和内容。"""
        html, text = email_service._render(
            "system_notice",
            {
                "username": "testuser",
                "notice_title": "系统维护通知",
                "notice_content": "系统将于今晚 22:00 维护",
                "action_url": "https://example.com/notice",
                "action_text": "查看详情",
            },
        )
        assert "系统维护通知" in html
        assert "系统将于今晚 22:00 维护" in html
        assert "https://example.com/notice" in html

    def test_render_system_notice_without_action(self):
        """系统通知无 action_url 时不渲染按钮。"""
        html, text = email_service._render(
            "system_notice",
            {
                "username": "testuser",
                "notice_title": "通知",
                "notice_content": "这是一条通知",
            },
        )
        assert "通知" in html
        assert "这是一条通知" in text

    def test_all_templates_render_html_and_text(self):
        """四种模板均能渲染 HTML + 纯文本双格式。"""
        templates = [
            ("verify_email", {"username": "u", "verify_url": "http://x"}),
            ("password_reset", {"username": "u", "reset_url": "http://x"}),
            ("login_alert", {"username": "u", "alert_detail": "d", "alert_time": "t", "ip_address": "i"}),
            ("system_notice", {"username": "u", "notice_title": "t", "notice_content": "c"}),
        ]
        for tpl_name, ctx in templates:
            html, text = email_service._render(tpl_name, ctx)
            assert len(html) > 100, f"{tpl_name} HTML too short"
            assert len(text) > 50, f"{tpl_name} text too short"
            assert "<html" in html, f"{tpl_name} missing HTML tags"


class TestSimulationMode:
    """模拟模式测试（SMTP_HOST 为空时）。"""

    def test_is_simulation_mode_when_no_host(self):
        """SMTP_HOST 为空时启用模拟模式。"""
        with patch.object(email_service._settings, "SMTP_HOST", ""):
            assert email_service._is_simulation_mode() is True

    def test_is_not_simulation_mode_with_host(self):
        """SMTP_HOST 非空时不启用模拟模式。"""
        with patch.object(email_service._settings, "SMTP_HOST", "smtp.example.com"):
            assert email_service._is_simulation_mode() is False

    def test_simulate_send_creates_file(self, db_session, tmp_path):
        """模拟模式落盘生成 .eml 文件。"""
        with (
            patch.object(email_service._settings, "SMTP_HOST", ""),
            patch.object(email_service, "_TEMPLATE_DIR", Path(__file__).parent.parent / "app" / "services" / "email_templates"),
        ):
            # 重新初始化 jinja env
            from jinja2 import Environment, FileSystemLoader, select_autoescape

            template_dir = Path(__file__).parent.parent / "app" / "services" / "email_templates"
            email_service._jinja_env = Environment(
                loader=FileSystemLoader(str(template_dir)),
                autoescape=select_autoescape(["html"]),
            )

            result = email_service.send_email(
                db=db_session,
                recipient="test@example.com",
                template_name="verify_email",
                context={"username": "testuser", "verify_url": "http://localhost/verify?token=abc"},
            )
            assert result is True

            # 验证 email_logs 记录
            db_session.commit()
            logs = db_session.query(EmailLog).all()
            assert len(logs) == 1
            assert logs[0].recipient == "test@example.com"
            assert logs[0].template == "verify_email"
            assert logs[0].status == "simulated"
            assert logs[0].error is None

    def test_simulate_send_all_templates(self, db_session):
        """模拟模式下四种模板均可成功发送。"""
        template_dir = Path(__file__).parent.parent / "app" / "services" / "email_templates"
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        email_service._jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html"]),
        )

        templates_and_contexts = [
            ("verify_email", {"username": "u", "verify_url": "http://x"}),
            ("password_reset", {"username": "u", "reset_url": "http://x"}),
            ("login_alert", {"username": "u", "alert_detail": "d", "alert_time": "t", "ip_address": "i"}),
            ("system_notice", {"username": "u", "notice_title": "t", "notice_content": "c"}),
        ]
        with patch.object(email_service._settings, "SMTP_HOST", ""):
            for tpl_name, ctx in templates_and_contexts:
                result = email_service.send_email(
                    db=db_session,
                    recipient=f"test_{tpl_name}@example.com",
                    template_name=tpl_name,
                    context=ctx,
                )
                assert result is True, f"{tpl_name} send failed"

        db_session.commit()
        logs = db_session.query(EmailLog).all()
        assert len(logs) == 4
        assert all(log.status == "simulated" for log in logs)


class TestEmailLogPersistence:
    """email_logs 持久化测试。"""

    def test_successful_send_logs_sent(self, db_session):
        """SMTP 发送成功后记录 status=sent。"""
        template_dir = Path(__file__).parent.parent / "app" / "services" / "email_templates"
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        email_service._jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html"]),
        )

        with (
            patch.object(email_service._settings, "SMTP_HOST", "smtp.example.com"),
            patch.object(email_service, "_send_smtp"),
        ):
            result = email_service.send_email(
                db=db_session,
                recipient="user@example.com",
                template_name="verify_email",
                context={"username": "u", "verify_url": "http://x"},
            )
        assert result is True
        db_session.commit()
        log = db_session.query(EmailLog).first()
        assert log is not None
        assert log.status == "sent"
        assert log.error is None

    def test_failed_send_logs_error(self, db_session):
        """SMTP 发送失败记录 status=failed 和错误信息。"""
        template_dir = Path(__file__).parent.parent / "app" / "services" / "email_templates"
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        email_service._jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html"]),
        )

        with (
            patch.object(email_service._settings, "SMTP_HOST", "smtp.example.com"),
            patch.object(email_service, "_send_smtp", side_effect=Exception("Connection refused")),
        ):
            result = email_service.send_email(
                db=db_session,
                recipient="user@example.com",
                template_name="verify_email",
                context={"username": "u", "verify_url": "http://x"},
            )
        assert result is False
        db_session.commit()
        log = db_session.query(EmailLog).first()
        assert log is not None
        assert log.status == "failed"
        assert "Connection refused" in log.error

    def test_unknown_template_logs_failure(self, db_session):
        """未知模板记录失败日志。"""
        result = email_service.send_email(
            db=db_session,
            recipient="user@example.com",
            template_name="nonexistent_template",
            context={},
        )
        assert result is False
        db_session.commit()
        log = db_session.query(EmailLog).first()
        assert log is not None
        assert log.status == "failed"
        assert "unknown template" in log.error


class TestSMTPSending:
    """SMTP 发送测试（mock smtplib）。"""

    def test_smtp_starttls_send(self, db_session):
        """STARTTLS 模式下正确发送邮件。"""
        template_dir = Path(__file__).parent.parent / "app" / "services" / "email_templates"
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        email_service._jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html"]),
        )

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(email_service._settings, "SMTP_HOST", "smtp.example.com"),
            patch.object(email_service._settings, "SMTP_PORT", 587),
            patch.object(email_service._settings, "SMTP_USER", "sender@example.com"),
            patch.object(email_service._settings, "SMTP_PASS", "password123"),
            patch.object(email_service._settings, "SMTP_USE_TLS", True),
            patch.object(email_service._settings, "SMTP_FROM_EMAIL", "sender@example.com"),
            patch.object(email_service._settings, "SMTP_FROM_NAME", "Test"),
            patch("app.services.email_service.smtplib.SMTP", return_value=mock_smtp),
        ):
            result = email_service.send_email(
                db=db_session,
                recipient="user@example.com",
                template_name="verify_email",
                context={"username": "u", "verify_url": "http://x"},
            )
        assert result is True
        mock_smtp.ehlo.assert_called()
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("sender@example.com", "password123")
        mock_smtp.send_message.assert_called_once()

    def test_smtp_ssl_send(self, db_session):
        """SSL 模式下正确发送邮件。"""
        template_dir = Path(__file__).parent.parent / "app" / "services" / "email_templates"
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        email_service._jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html"]),
        )

        mock_smtp_ssl = MagicMock()
        mock_smtp_ssl.__enter__ = MagicMock(return_value=mock_smtp_ssl)
        mock_smtp_ssl.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(email_service._settings, "SMTP_HOST", "smtp.example.com"),
            patch.object(email_service._settings, "SMTP_PORT", 465),
            patch.object(email_service._settings, "SMTP_USER", "sender@example.com"),
            patch.object(email_service._settings, "SMTP_PASS", "password123"),
            patch.object(email_service._settings, "SMTP_USE_TLS", False),
            patch.object(email_service._settings, "SMTP_FROM_EMAIL", "sender@example.com"),
            patch.object(email_service._settings, "SMTP_FROM_NAME", "Test"),
            patch("app.services.email_service.smtplib.SMTP_SSL", return_value=mock_smtp_ssl),
        ):
            result = email_service.send_email(
                db=db_session,
                recipient="user@example.com",
                template_name="password_reset",
                context={"username": "u", "reset_url": "http://x"},
            )
        assert result is True
        mock_smtp_ssl.login.assert_called_once()
        mock_smtp_ssl.send_message.assert_called_once()


class TestCustomSubject:
    """自定义主题测试。"""

    def test_custom_subject_overrides_default(self, db_session):
        """传入 subject 参数时覆盖默认主题。"""
        template_dir = Path(__file__).parent.parent / "app" / "services" / "email_templates"
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        email_service._jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html"]),
        )

        with (
            patch.object(email_service._settings, "SMTP_HOST", "smtp.example.com"),
            patch.object(email_service, "_send_smtp"),
        ):
            email_service.send_email(
                db=db_session,
                recipient="user@example.com",
                template_name="system_notice",
                context={"username": "u", "notice_title": "t", "notice_content": "c"},
                subject="自定义主题",
            )
        db_session.commit()
        log = db_session.query(EmailLog).first()
        assert log.subject == "自定义主题"
