export type ServerControlAction = 'start' | 'stop' | 'restart';

export type ServerControlStatusWireResponse = {
  ok: boolean;
  projectRoot: string;
  startScript: string;
  stopScript: string;
  startExists: boolean;
  stopExists: boolean;
  serverState: string;
  message?: string;
  detail?: string;
  action?: ServerControlAction;
};

export type ServerControlNotificationsWireResponse = {
  ok: boolean;
  items: Array<Record<string, unknown>>;
};
