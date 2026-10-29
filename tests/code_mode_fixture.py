"""Module mẫu cho test `run_code`: các hàm code của model được (hoặc không được) gọi."""

import os


def double(x: int) -> int:
    """Nhân đôi x."""
    return 2 * x


def env_keys() -> list[str]:
    """Tên các biến môi trường mà tiến trình con nhìn thấy."""
    return sorted(os.environ)


def secret() -> str:
    """Không nằm trong danh sách cho phép của test."""
    return "bí mật"
