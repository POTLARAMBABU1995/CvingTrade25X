import json
from fastapi import APIRouter, HTTPException, Query

from ..db import execute, fetch_one
from ..models import UserAnnotationUpsert, UserAnnotationsResponse
from ..utils.time import normalize_tf

router = APIRouter()


def _annotation_id(user_id: int, symbol: str, tf: str) -> str:
    return f"{user_id}:{symbol}:{tf}"


@router.get('/user-annotations', response_model=UserAnnotationsResponse)
async def get_user_annotations(
    userId: int = Query(...),
    symbol: str = Query(...),
    tf: str = Query('1D'),
):
    tf_norm = normalize_tf(tf)
    row = fetch_one(
        """
        SELECT PAYLOAD_JSON
        FROM USER_ANNOTATIONS
        WHERE USER_ID = :user_id AND SYMBOL = :symbol AND TF = :tf
        """,
        {'user_id': userId, 'symbol': symbol, 'tf': tf_norm},
    )
    annotations = []
    if row and row.get('payload_json'):
        payload = row['payload_json']
        try:
            annotations = json.loads(payload.read() if hasattr(payload, 'read') else payload)
        except (ValueError, TypeError):
            annotations = []
    return UserAnnotationsResponse(userId=userId, symbol=symbol, tf=tf_norm, annotations=annotations)


@router.post('/user-annotations', response_model=UserAnnotationsResponse)
async def upsert_user_annotations(payload: UserAnnotationUpsert):
    tf_norm = normalize_tf(payload.tf)
    annotation_id = _annotation_id(payload.userId, payload.symbol, tf_norm)
    json_payload = json.dumps(payload.annotations, ensure_ascii=True)
    sql = """
        MERGE INTO USER_ANNOTATIONS dst
        USING (
          SELECT :annotation_id AS ANNOTATION_ID,
                 :user_id AS USER_ID,
                 :symbol AS SYMBOL,
                 :tf AS TF,
                 :payload AS PAYLOAD_JSON
          FROM dual
        ) src
        ON (dst.ANNOTATION_ID = src.ANNOTATION_ID)
        WHEN MATCHED THEN UPDATE SET
          dst.PAYLOAD_JSON = src.PAYLOAD_JSON,
          dst.UPDATED_AT = SYSTIMESTAMP
        WHEN NOT MATCHED THEN INSERT (
          ANNOTATION_ID, USER_ID, SYMBOL, TF, PAYLOAD_JSON
        ) VALUES (
          src.ANNOTATION_ID, src.USER_ID, src.SYMBOL, src.TF, src.PAYLOAD_JSON
        )
    """
    execute(sql, {
        'annotation_id': annotation_id,
        'user_id': payload.userId,
        'symbol': payload.symbol,
        'tf': tf_norm,
        'payload': json_payload,
    })
    return UserAnnotationsResponse(userId=payload.userId, symbol=payload.symbol, tf=tf_norm, annotations=payload.annotations)
