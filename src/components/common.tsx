import { useEffect, useState, type ReactNode } from 'react';
import { CheckCircle2, CircleAlert, LoaderCircle, X } from 'lucide-react';
import { api, pollJob } from '../api';
import type { Job } from '../types';

export function Panel({ title, subtitle, children, action }: { title: string; subtitle?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

export function Pill({ children, tone = 'violet' }: { children: ReactNode; tone?: 'violet' | 'green' | 'amber' | 'muted' }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

export function Progress({ value }: { value: number }) {
  return <div className="progress"><div style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div>;
}

export function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(onClose, 6000);
    return () => window.clearTimeout(timer);
  }, [message, onClose]);
  return (
    <div className="toast">
      <CircleAlert size={18} />
      <span>{message}</span>
      <button onClick={onClose} className="icon-btn"><X size={16} /></button>
    </div>
  );
}

export function JobTracker({ jobId, label, onDone }: { jobId: string | null; label: string; onDone?: (job: Job) => void }) {
  const [job, setJob] = useState<Job | null>(null);
  useEffect(() => {
    if (!jobId) return;
    setJob(null);
    let seen = '';
    return pollJob(jobId, (next) => {
      setJob(next);
      if (next.status !== seen && ['done', 'error', 'cancelled'].includes(next.status)) {
        seen = next.status;
        onDone?.(next);
      }
    });
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!jobId) return null;
  const icon = job?.status === 'done' ? <CheckCircle2 size={16} /> : job?.status === 'error' ? <CircleAlert size={16} /> : <LoaderCircle size={16} className="spin" />;
  return (
    <div className="job-tracker">
      <div className="job-tracker-head">{icon}<strong>{label}</strong><span>{job?.message || 'Starting…'}</span></div>
      <Progress value={job?.progress || 0} />
    </div>
  );
}

export function useJobs() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const refresh = async () => {
    try { setJobs((await api.jobs()).jobs || []); } catch { /* offline */ }
  };
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(refresh, 2500);
    return () => window.clearInterval(timer);
  }, []);
  return { jobs, refresh };
}

export function JobProgressList({ jobs }: { jobs: Job[] }) {
  const recent = [...jobs]
    .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
    .slice(0, 3);
  if (!recent.length) return null;
  return (
    <div className="sidebar-jobs">
      <span className="nav-label">Operations</span>
      {recent.map((job) => (
        <div className={`sidebar-job job-${job.status}`} key={job.id}>
          <div><strong>{job.kind || 'Working'}</strong><small>{job.message || 'Starting…'}</small></div>
          <span>{job.status === 'done' ? 'Done' : job.status === 'error' ? 'Failed' : `${Math.round(job.progress || 0)}%`}</span>
          <Progress value={job.status === 'done' ? 100 : job.progress || 0} />
        </div>
      ))}
    </div>
  );
}

export function formatClock(seconds?: number): string {
  const value = Math.max(0, seconds || 0);
  const mins = Math.floor(value / 60);
  const secs = Math.floor(value % 60);
  return `${mins}:${String(secs).padStart(2, '0')}`;
}

export function EmptyState({ icon, title, detail }: { icon: ReactNode; title: string; detail: string }) {
  return <div className="empty"><div className="empty-icon">{icon}</div><h3>{title}</h3><p>{detail}</p></div>;
}
