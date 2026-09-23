import { legacyApiGet, legacyApiPost } from '../../api/client';
import type {
  ServerControlAction,
  ServerControlNotificationsWireResponse,
  ServerControlStatus,
  ServerControlStatusWireResponse,
} from '../../types';

function adaptServerControlStatus(payload: ServerControlStatusWireResponse): ServerControlStatus {
  return {
    projectRoot: payload.projectRoot,
    startScript: payload.startScript,
    stopScript: payload.stopScript,
    startExists: payload.startExists,
    stopExists: payload.stopExists,
    serverState: String(payload.serverState || '').trim().toUpperCase(),
    message: payload.message ?? null,
    detail: payload.detail ?? null,
    action: payload.action ?? null,
  };
}

export async function fetchServerControlStatus(): Promise<ServerControlStatus> {
  const payload = await legacyApiGet<ServerControlStatusWireResponse>('/api/server-control/status', undefined, {
    timeoutMs: 10000,
  });
  return adaptServerControlStatus(payload);
}

export async function runServerControlAction(action: ServerControlAction): Promise<ServerControlStatus> {
  const payload = await legacyApiPost<ServerControlStatusWireResponse>(`/api/server-control/${action}`, {}, {
    timeoutMs: 20000,
  });
  return adaptServerControlStatus(payload);
}

export function fetchServerControlNotifications(sinceTs = 0, limit = 20): Promise<ServerControlNotificationsWireResponse> {
  return legacyApiGet<ServerControlNotificationsWireResponse>('/api/server-control/notifications', { sinceTs, limit }, {
    timeoutMs: 10000,
  });
}
