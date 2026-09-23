from fastapi import APIRouter, Query

from ..db import fetch_all
from ..models import SymbolsResponse

router = APIRouter()


@router.get('/symbols', response_model=SymbolsResponse)
async def get_symbols(q: str = Query(None), limit: int = Query(50)):
    query = (q or '').strip().upper()
    like = f"%{query}%" if query else None
    sql = """
        SELECT * FROM (
          SELECT SYMBOL, NAME, EXCHANGE, SECTOR
          FROM SYMBOLS
          WHERE (:query IS NULL OR UPPER(SYMBOL) LIKE :like OR UPPER(NAME) LIKE :like)
          ORDER BY SYMBOL
        )
        WHERE ROWNUM <= :limit
    """
    rows = fetch_all(sql, {
        'query': query if query else None,
        'like': like,
        'limit': limit,
    })
    return SymbolsResponse(q=q, symbols=rows)
