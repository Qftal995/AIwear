"""MCP body shape analysis server — in-process tool registration."""

from mcp_servers.tool_registry import mcp_registry


def _get_body_shape_service():
    from services.body_shape_service import BodyShapeService
    return BodyShapeService()


def analyze_body_shape(measurements: dict = None, description: str = "") -> dict:
    """分析用户身材类型并返回穿搭建议。"""
    svc = _get_body_shape_service()
    return svc.analyze(measurements=measurements, description=description)


def list_body_shapes() -> list[dict]:
    """列出所有可识别身材类型及其特征。"""
    svc = _get_body_shape_service()
    return svc.list_shapes()


def analyze_body_shape_from_image(image_url: str = "") -> dict:
    """从照片分析用户身材类型，使用视觉模型识别肩宽、腰线、臀胯比例。"""
    svc = _get_body_shape_service()
    return svc.analyze_from_image(image_url)


def get_styling_advice(shape: str = "") -> dict:
    """获取指定身材类型的穿搭策略和推荐单品。"""
    svc = _get_body_shape_service()
    if shape and shape in svc.SHAPE_RULES:
        return {"shape": shape, **svc.SHAPE_RULES[shape]}
    return {"shapes": svc.list_shapes(), "note": "请指定身材类型获取详细建议"}


def register():
    """Register body shape tools with the MCP tool registry."""
    mcp_registry.register_server("aiwear-body-shape", transport="in-process", description="身材分析 — 5 种身材类型的穿搭策略")

    mcp_registry.register_tool(
        server="aiwear-body-shape",
        name="analyze",
        description="分析用户身材类型（梨形/苹果型/H型/倒三角/沙漏型），输入三围或文字描述",
        schema={
            "type": "object",
            "properties": {
                "measurements": {
                    "type": "object",
                    "properties": {
                        "bust": {"type": "number"},
                        "waist": {"type": "number"},
                        "hip": {"type": "number"},
                    },
                },
                "description": {"type": "string", "description": "身材文字描述"},
            },
        },
        callable_fn=analyze_body_shape,
    )

    mcp_registry.register_tool(
        server="aiwear-body-shape",
        name="list_shapes",
        description="列出所有可识别的身材类型及其特征描述",
        schema={"type": "object", "properties": {}},
        callable_fn=list_body_shapes,
    )

    mcp_registry.register_tool(
        server="aiwear-body-shape",
        name="analyze_from_image",
        description="从用户上传的照片中分析身材类型（梨形/苹果型/H型/倒三角/沙漏型），需要提供图片URL",
        schema={
            "type": "object",
            "properties": {"image_url": {"type": "string", "description": "用户照片的URL"}},
            "required": ["image_url"],
        },
        callable_fn=analyze_body_shape_from_image,
    )

    mcp_registry.register_tool(
        server="aiwear-body-shape",
        name="get_styling_advice",
        description="获取指定身材类型的穿搭策略、推荐单品和避坑建议",
        schema={
            "type": "object",
            "properties": {"shape": {"type": "string", "description": "身材类型"}},
        },
        callable_fn=get_styling_advice,
    )
