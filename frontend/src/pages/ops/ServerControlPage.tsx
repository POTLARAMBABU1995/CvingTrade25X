import { useEffect, useState } from 'react';
import { AppToolbar } from '../../components/app/AppToolbar';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { fetchServerControlStatus, runServerControlAction } from '../../services/ops/serverControlApi';
import type { ServerControlAction, ServerControlStatus } from '../../types';
import { OpsPageShell } from './OpsPageShell';
import { ActionButton, KpiGrid, PageHero } from './opsPageHelpers';

type LoadStatus = 'error' | 'loading' | 'online';

export function ServerControlPage() {
  const [error, setError] = useState('');
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [serverStatus, setServerStatus] = useState<ServerControlStatus | null>(null);
  const [status, setStatus] = useState<LoadStatus>('loading');

  useEffect(() => {
    setStatus('loading');
    setError('');
    fetchServerControlStatus().then((payload) => {
      setServerStatus(payload);
      setStatus('online');
    }).catch((loadError) => {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
      setStatus('error');
    });
  }, [refreshVersion]);

  async function runAction(action: ServerControlAction) {
    setStatus('loading');
    setError('');
    try {
      const payload = await runServerControlAction(action);
      setServerStatus(payload);
      setStatus('online');
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : String(actionError));
      setStatus('error');
    }
  }

  const state = String(serverStatus?.serverState || 'CHECKING').toUpperCase();
  return (
    <OpsPageShell activeDatabasePage="/app/database/server" className="server-control-react-page">
      <PageHero title="Server Control" />

      <AppToolbar aria-label="Server control actions">
        <ActionButton disabled={status === 'loading'} onClick={() => runAction('restart')}>Auto Restart</ActionButton>
        <ActionButton disabled={status === 'loading'} onClick={() => setRefreshVersion((current) => current + 1)}>Refresh Status</ActionButton>
        <ActionButton disabled={status === 'loading' || !serverStatus?.startExists} onClick={() => runAction('start')}>StartUp</ActionButton>
        <ActionButton disabled={status === 'loading' || !serverStatus?.stopExists} onClick={() => runAction('stop')}>ShutDown</ActionButton>
      </AppToolbar>

      {error ? <ErrorAlertCard message={error} /> : null}

      <KpiGrid items={[
        { label: 'Server State', value: state },
        { label: 'Start Script', value: serverStatus?.startExists ? 'Available' : 'Missing' },
        { label: 'Stop Script', value: serverStatus?.stopExists ? 'Available' : 'Missing' },
        { label: 'Project Root', value: serverStatus?.projectRoot || '-' },
        { label: 'Last Action', value: serverStatus?.action || '-' },
      ]} />

      <section className="card">
        <div className="table-title">
          <h3>Important</h3>
        </div>
        <p className="database-react-warning">
          <code>stop_cvingtrade25x.bat</code> force-kills local <code>python.exe</code> and <code>pythonw.exe</code> processes. Use the shutdown button only when you intend to stop the backend and related Python workers.
        </p>
        <p>{serverStatus?.message || 'Checking server control scripts...'}</p>
        {serverStatus?.detail ? <p>{serverStatus.detail}</p> : null}
      </section>
    </OpsPageShell>
  );
}


