"""邮件服务：SMTP 发送 + Jinja2 模板渲染 + email_logs 落库。

SMTP 凭据未配置时自动启用"模拟模式"（console + 文件落盘），日志标注 [SIMULATED]，不阻断开发。
调用方（G23/G16）传入 template_name + context，链接由调用方拼装后放入 context。
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.email_log import EmailLog

logger = logging.getLogger(__name__)
_settings = get_settings()

# 模板目录
_TEMPLATE_DIR = Path(__file__).parent / "email_templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)

# 模板名称 → 邮件主题
_TEMPLATE_SUBJECTS: dict[str, str] = {
    "verify_email": "【量化回测助手】请验证您的邮箱",
    "password_reset": "【量化回测助手】重置密码请求",
    "login_alert": "【量化回测助手】异常登录提醒",
    "system_notice": "【量化回测助手】系统通知",
}


def _is_simulation_mode() -> bool:
    """SMTP_HOST 为空 → 模拟模式。"""
    return not _settings.SMTP_HOST


def _render(template_name: str, context: dict) -> tuple[str, str]:
    """渲染 HTML + 纯文本双格式，返回 (html_body, text_body)。"""
    html_tpl = _jinja_env.get_template(f"{template_name}.html")
    txt_tpl = _jinja_env.get_template(f"{template_name}.txt")
    return html_tpl.render(**context), txt_tpl.render(**context)


def _build_message(
    recipient: str, subject: str, html_body: str, text_body: str
) -> MIMEMultipart:
    """构建 MIME 多部分邮件（HTML + 纯文本 fallback）。"""
    from_email = _settings.SMTP_FROM_EMAIL or _settings.SMTP_USER
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{_settings.SMTP_FROM_NAME} <{from_email}>"
    msg["To"] = recipient
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def _send_smtp(msg: MIMEMultipart, recipient: str) -> None:
    """通过 SMTP 发送邮件，支持 STARTTLS / SSL。"""
    timeout = _settings.SMTP_TIMEOUT
    if _settings.SMTP_USE_TLS:
        # STARTTLS（端口 587）
        with smtplib.SMTP(_settings.SMTP_HOST, _settings.SMTP_PORT, timeout=timeout) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if _settings.SMTP_USER:
                server.login(_settings.SMTP_USER, _settings.SMTP_PASS)
            server.send_message(msg)
    else:
        # SSL（端口 465）
        with smtplib.SMTP_SSL(_settings.SMTP_HOST, _settings.SMTP_PORT, timeout=timeout) as server:
            if _settings.SMTP_USER:
                server.login(_settings.SMTP_USER, _settings.SMTP_PASS)
            server.send_message(msg)


def _simulate_send(msg: MIMEMultipart, recipient: str, template_name: str) -> None:
    """模拟模式：console 输出 + 文件落盘。"""
    out_dir = Path(__file__).parent.parent.parent / "data" / "email_outbox"
    out_dir.mkdir(parents=True, exist_ok=True)
    from datetime import UTC, datetime

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    out_file = out_dir / f"{template_name}_{ts}.eml"
    out_file.write_text(msg.as_string(), encoding="utf-8")
    logger.info(
        "[SIMULATED] email to=%s template=%s file=%s",
        recipient,
        template_name,
        out_file,
    )


def _log_email(
    db: Session | None,
    recipient: str,
    template_name: str,
    subject: str,
    status: str,
    error: str | None = None,
) -> None:
    """写入 email_logs 表。db 为 None 时仅记日志（非请求上下文）。"""
    if db is None:
        logger.warning(
            "email log skipped (no db session): recipient=%s template=%s status=%s",
            recipient,
            template_name,
            status,
        )
        return
    try:
        log = EmailLog(
            recipient=recipient,
            template=template_name,
            subject=subject,
            status=status,
            error=error,
        )
        db.add(log)
        db.flush()
    except Exception:  # noqa: BLE001
        logger.exception("failed to write email_log: recipient=%s template=%s", recipient, template_name)


def send_email(
    db: Session | None,
    recipient: str,
    template_name: str,
    context: dict,
    subject: str | None = None,
) -> bool:
    """发送邮件主入口。

    Args:
        db: 数据库会话（用于写 email_logs，可为 None）
        recipient: 收件人邮箱
        template_name: 模板名称（verify_email / password_reset / login_alert / system_notice）
        context: 模板渲染上下文（链接由调用方拼装放入）
        subject: 自定义主题（默认按模板映射）

    Returns:
        True=发送/模拟成功, False=失败
    """
    if template_name not in _TEMPLATE_SUBJECTS:
        logger.error("unknown email template: %s", template_name)
        _log_email(db, recipient, template_name, subject or "", "failed", f"unknown template: {template_name}")
        return False

    subject = subject or _TEMPLATE_SUBJECTS[template_name]

    try:
        html_body, text_body = _render(template_name, context)
    except Exception as exc:  # noqa: BLE001
        logger.exception("template render failed: %s", template_name)
        _log_email(db, recipient, template_name, subject, "failed", f"render error: {exc}")
        return False

    msg = _build_message(recipient, subject, html_body, text_body)

    if _is_simulation_mode():
        _simulate_send(msg, recipient, template_name)
        _log_email(db, recipient, template_name, subject, "simulated")
        return True

    try:
        _send_smtp(msg, recipient)
        _log_email(db, recipient, template_name, subject, "sent")
        logger.info("email sent: to=%s template=%s", recipient, template_name)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("SMTP send failed: to=%s template=%s", recipient, template_name)
        _log_email(db, recipient, template_name, subject, "failed", str(exc))
        return False
