from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Bar(BaseModel):
    t: int
    o: float
    h: float
    l: float
    c: float
    v: float


class BarsResponse(BaseModel):
    version: str = 'v1'
    symbol: str
    tf: str
    nextCursor: Optional[str] = None
    bars: List[Bar]


class IndicatorPoint(BaseModel):
    t: int
    v: float


class IndicatorsResponse(BaseModel):
    version: str = 'v1'
    symbol: str
    tf: str
    series: Dict[str, List[IndicatorPoint]]


class OverlaysResponse(BaseModel):
    version: str = 'v1'
    symbol: str
    tf: str
    annotations: List[Dict[str, Any]]


class UserAnnotationsResponse(BaseModel):
    version: str = 'v1'
    userId: int = Field(..., alias='userId')
    symbol: str
    tf: str
    annotations: List[Dict[str, Any]]


class UserAnnotationUpsert(BaseModel):
    userId: int
    symbol: str
    tf: str
    annotations: List[Dict[str, Any]]


class SymbolsResponse(BaseModel):
    version: str = 'v1'
    q: Optional[str]
    symbols: List[Dict[str, Any]]
