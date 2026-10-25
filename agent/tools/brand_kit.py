"""Tool đọc brand kit: chỉ cho phép đọc các file nằm trong thư mục data/brand/."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from agent.tools import Tool

BRAND_DIR = (Path(__file__).resolve().parent.parent.parent / "data" / "brand").resolve()


class LoadBrandKitArgs(BaseModel):
    path: str = Field(
        ...,
        description=(
            "Đường dẫn tới file brand kit trong data/brand/ "
            "(ví dụ 'data/brand/brand_kit.yaml')"
        ),
    )


def read_brand_kit(args: LoadBrandKitArgs) -> dict[str, Any]:
    raw_path = Path(args.path)
    if raw_path.is_absolute():
        target = raw_path.resolve()
    else:
        candidate_root = (BRAND_DIR.parent.parent / raw_path).resolve()
        candidate_brand = (BRAND_DIR / raw_path).resolve()
        target = candidate_root if candidate_root.exists() else candidate_brand

    try:
        target.relative_to(BRAND_DIR)
    except ValueError as e:
        raise ValueError(f"Đường dẫn nằm ngoài thư mục cho phép (data/brand/): {args.path}") from e

    if not target.is_file():
        raise FileNotFoundError(f"Không tìm thấy file: {args.path}")

    text = target.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Nội dung brand kit không phải dạng mapping/dict: {args.path}")

    return data


load_brand_kit = Tool(
    name="load_brand_kit",
    description=(
        "Đọc file cấu hình thương hiệu (brand kit) trong thư mục data/brand/. "
        "Trả về thông tin chi tiết về thương hiệu, sản phẩm, đối thủ và quy chuẩn giọng văn."
    ),
    args_model=LoadBrandKitArgs,
    fn=read_brand_kit,
)
