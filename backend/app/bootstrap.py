from __future__ import annotations

import argparse
import asyncio
import getpass

from app.core.auth import ensure_bootstrap_admin
from app.core.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="创建 RAGManage 首个平台管理员")
    parser.add_argument("--login", default=None, help="管理员登录名")
    args = parser.parse_args()
    settings = Settings()
    settings.bootstrap_admin_login = (
        args.login or input("管理员登录名 [admin]: ").strip() or "admin"
    )
    settings.bootstrap_admin_display_name = input("显示名称 [平台管理员]: ").strip() or "平台管理员"
    settings.bootstrap_admin_password = getpass.getpass("管理员密码（不会回显）: ")
    if len(settings.bootstrap_admin_password) < 12:
        raise SystemExit("密码至少需要 12 个字符")
    asyncio.run(ensure_bootstrap_admin(settings))
    print("管理员账号已创建或已存在；已有账号不会被覆盖。")


if __name__ == "__main__":
    main()
