"""FastAPI 接口（可选）。

启动：
    uvicorn hotspot_analysis.api:app --reload --port 8000

调用：
    POST /analyze
    body: {"keyword": "...", "raw_text": "..."}   # raw_text 可选
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from hotspot_analysis.analyzer import AnalyzerError, HotspotAnalyzer
from hotspot_analysis.config import ConfigError, load_settings
from hotspot_analysis.renderers import render_markdown, to_dict

app = FastAPI(
    title="抖音热点分析 API",
    version="0.1.0",
    description="输入热点词条与评论，输出四步结构化分析报告。",
)


class AnalyzeRequest(BaseModel):
    keyword: str = Field(..., description="热点词条", min_length=1)
    raw_text: Optional[str] = Field(
        default="", description="相关内容 / 高赞评论原文"
    )


class AnalyzeResponse(BaseModel):
    report: dict
    markdown: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    try:
        settings = load_settings()
        analyzer = HotspotAnalyzer(settings)
        report = analyzer.analyze(req.keyword, req.raw_text or "")
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=f"配置错误：{exc}") from exc
    except AnalyzerError as exc:
        raise HTTPException(status_code=502, detail=f"分析失败：{exc}") from exc

    return AnalyzeResponse(
        report=to_dict(report),
        markdown=render_markdown(report),
    )
