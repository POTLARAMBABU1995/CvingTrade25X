import { chartApiGet, chartApiPost } from './client';
import type { OverlayAnnotation, Timeframe, UserAnnotationsResponse } from '../types';

export type UserAnnotationsParams = {
  userId: number;
  symbol: string;
  tf: Timeframe;
};

export function fetchUserAnnotations(params: UserAnnotationsParams): Promise<UserAnnotationsResponse> {
  return chartApiGet<UserAnnotationsResponse>('/api/user-annotations', {
    userId: params.userId,
    symbol: params.symbol,
    tf: params.tf,
  });
}

export type UpsertAnnotationsPayload = {
  userId: number;
  symbol: string;
  tf: Timeframe;
  annotations: OverlayAnnotation[];
};

export function upsertUserAnnotations(payload: UpsertAnnotationsPayload): Promise<UserAnnotationsResponse> {
  return chartApiPost<UserAnnotationsResponse>('/api/user-annotations', payload);
}
