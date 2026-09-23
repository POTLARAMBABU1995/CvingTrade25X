import type { ServerControlAction } from '../api/serverControl';

export type ServerControlStatus = {
  projectRoot: string;
  startScript: string;
  stopScript: string;
  startExists: boolean;
  stopExists: boolean;
  serverState: string;
  message: string | null;
  detail: string | null;
  action: ServerControlAction | null;
};
