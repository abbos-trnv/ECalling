import { type FormEvent, useEffect, useRef, useState } from 'react';
import { CallResult, timecode } from './CallResult';

type Company = { id: string; name: string };
type Employee = { id: string; display_name: string };
type Call = { id: string; run_id: string; company_id: string; employee_id: string | null; filename_safe: string; duration_ms: number; size_bytes: number; status: string; stage: string; failure_code: string | null; attempt: number; created_at: string; is_mock: boolean; score: number | null; coverage: number | null };
const labels: Record<string, string> = { queued: 'В очереди', processing: 'Обрабатываем', awaiting_analysis: 'Запись проверена', failed: 'Ошибка обработки', completed: 'Обработано' };
const stages: Record<string, string> = { preprocess: 'Проверка аудио', transcribe: 'Тестовый транскрипт', analyze: 'Тестовый анализ', validate: 'Проверка результата', publish: 'Результат сохранён' };
const failures: Record<string, string> = { WORKER_INTERRUPTED: 'Обработка прерывалась несколько раз', DECODE_FAILED: 'Аудио повреждено или проверка заняла слишком долго', VALIDATOR_UNAVAILABLE: 'Проверка аудио временно недоступна', STORAGE_UNAVAILABLE: 'Хранилище аудио недоступно', INVALID_ANALYSIS: 'Результат не прошёл проверку структуры или доказательств' };

async function get<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Не удалось выполнить запрос');
  }
  return response.json();
}

export function Calls({ company, workspaceRevision }: { company: Company | null; workspaceRevision: number }) {
  const [file, setFile] = useState<File | null>(null);
  const [employeeId, setEmployeeId] = useState('');
  const [employees, setEmployees] = useState<{companyId: string; items: Employee[]} | null>(null);
  const [data, setData] = useState<{companyId: string; page: number; items: Call[]; hasNext: boolean} | null>(null);
  const [page, setPage] = useState(0);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [employeeError, setEmployeeError] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const key = useRef(crypto.randomUUID());
  const companyRef = useRef(company?.id);
  companyRef.current = company?.id;
  const current = data?.companyId === company?.id && data?.page === page ? data : null;
  const currentEmployees = employees && employees.companyId === company?.id ? employees.items : [];

  useEffect(() => {
    setPage(0); setFile(null); setEmployeeId(''); setError(''); setLoadError('');
    key.current = crypto.randomUUID();
    if (input.current) input.current.value = '';
  }, [company?.id]);

  useEffect(() => {
    if (!company) return;
    const controller = new AbortController();
    setEmployeeError('');
    async function load() {
      const items: Employee[] = [];
      for (let offset = 0; ; offset += 100) {
        const batch = await get<Employee[]>(`/api/v1/companies/${company!.id}/employees?limit=100&offset=${offset}`, { signal: controller.signal });
        items.push(...batch);
        if (batch.length < 100) break;
      }
      if (!controller.signal.aborted) setEmployees({companyId: company!.id, items});
    }
    void load().catch(() => { if (!controller.signal.aborted) setEmployeeError('Не удалось загрузить сотрудников. Обновите страницу.'); });
    return () => controller.abort();
  }, [company?.id, revision, workspaceRevision]);

  useEffect(() => {
    if (!company) return;
    const controller = new AbortController();
    let loading = false;
    async function load() {
      if (loading) return;
      loading = true;
      try {
        const items = await get<Call[]>(`/api/v1/companies/${company!.id}/calls?limit=11&offset=${page * 10}`, { signal: controller.signal });
        if (!controller.signal.aborted) { setData({companyId: company!.id, page, items: items.slice(0, 10), hasNext: items.length > 10}); setLoadError(''); }
      } catch (cause) { if (!controller.signal.aborted) setLoadError(cause instanceof Error ? cause.message : 'Ошибка загрузки'); }
      finally { loading = false; }
    }
    void load();
    const timer = setInterval(() => void load(), 3000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [company?.id, page, revision]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file || !company || busy) return;
    const target = company.id;
    setBusy(true); setError('');
    const form = new FormData();
    form.append('file', file);
    if (employeeId) form.append('employee_id', employeeId);
    try {
      await get(`/api/v1/companies/${target}/calls`, { method: 'POST', body: form, headers: { 'Idempotency-Key': key.current } });
      if (companyRef.current === target) {
        setFile(null); if (input.current) input.current.value = '';
        key.current = crypto.randomUUID(); setPage(0); setRevision(previous => previous + 1);
      }
    } catch (cause) {
      if (companyRef.current === target) setError(cause instanceof Error ? cause.message : 'Ошибка загрузки');
    } finally { setBusy(false); }
  }

  return <section id="calls" className="organizations" aria-label="Записи звонков">
    <div className="section-heading"><div><p className="eyebrow">АУДИО И ОБРАБОТКА</p><h2>Записи звонков {company ? `· ${company.name}` : ''}</h2></div></div>
    {!company ? <div className="org-panel"><p>Сначала выберите компанию выше.</p></div> : <>
      <form className="org-panel upload-form" onSubmit={event => void upload(event)}>
        <div><label htmlFor="audio-file">Аудиозапись</label><input ref={input} id="audio-file" type="file" accept=".wav,.mp3,.m4a,audio/wav,audio/mpeg,audio/mp4" disabled={busy} required onChange={event => { setFile(event.target.files?.[0] ?? null); key.current = crypto.randomUUID(); setError(''); }} /></div>
        <div><label htmlFor="call-employee">Сотрудник</label><select id="call-employee" value={employeeId} disabled={busy || Boolean(employeeError)} onChange={event => { setEmployeeId(event.target.value); key.current = crypto.randomUUID(); }}><option value="">Без сотрудника</option>{currentEmployees.map(employee => <option key={employee.id} value={employee.id}>{employee.display_name}</option>)}</select></div>
        <button disabled={busy || !file}>{busy ? 'Загружаем…' : 'Загрузить запись'}</button>
        <p className="upload-hint">WAV, MP3, M4A · До 50 МБ и 30 минут по умолчанию. Только синтетические записи или записи с разрешением.</p>
        <p className="upload-hint">Сейчас транскрипт и анализ создаются в тестовом mock-режиме. Содержимое записи не распознаётся.</p>
        {error && <div className="form-error" role="alert">{error}</div>}
        {employeeError && <div className="form-error" role="alert">{employeeError}</div>}
      </form>
      {loadError && <div className="form-error" role="alert">{loadError} · Повторяем запрос автоматически.</div>}
      {!current ? <p className="empty-state">Загружаем записи…</p> : current.items.length === 0 ? <div className="org-panel empty-state">Записей пока нет. Загрузите первую.</div> : <div className="call-list">
        {current.items.map(call => <CallCard key={call.id} call={call} company={company} employeeName={currentEmployees.find(item => item.id === call.employee_id)?.display_name} onChanged={() => setRevision(previous => previous + 1)} />)}
      </div>}
      {(page > 0 || current?.hasNext) && <div className="pagination"><button className="secondary" disabled={!current || page === 0} onClick={() => setPage(previous => previous - 1)}>Назад</button><span>Страница {page + 1}</span><button className="secondary" disabled={!current?.hasNext} onClick={() => setPage(previous => previous + 1)}>Далее</button></div>}
    </>}
  </section>;
}

function CallCard({ call, company, employeeName, onChanged }: {call: Call; company: Company; employeeName?: string; onChanged: () => void}) {
  const player = useRef<HTMLAudioElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [pendingRun, setPendingRun] = useState('');
  const active = ['queued', 'processing'].includes(call.status) || Boolean(pendingRun && pendingRun !== call.run_id);

  async function retry() {
    if (busy || active) return;
    setBusy(true); setError('');
    try {
      const result = await get<{run_id: string}>(`/api/v1/companies/${company.id}/calls/${call.id}/retry`, {method:'POST'});
      setPendingRun(result.run_id); setExpanded(true); onChanged();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось запустить обработку'); }
    finally { setBusy(false); }
  }

  function seek(ms: number) {
    if (!player.current) return;
    player.current.currentTime = ms / 1000;
    void player.current.play().catch(() => setError('Нажмите воспроизведение в плеере, чтобы открыть аудио.'));
  }

  return <article className="org-panel call-card">
    <div className="call-title"><h3>{call.filename_safe}</h3><div className="call-badges">{call.is_mock && <span className="mock-badge">MOCK</span>}<span className={`call-status status-${call.status}`} role="status">{call.status === 'completed' && call.is_mock ? 'Тестовый результат' : labels[call.status] ?? call.status}</span></div></div>
    <p className="helper">{new Date(call.created_at).toLocaleString('ru-RU')} · {timecode(call.duration_ms)} · {(call.size_bytes / 1024 / 1024).toFixed(2)} МБ · {call.employee_id ? employeeName ?? 'Сотрудник' : 'Без сотрудника'}</p>
    <audio ref={player} controls preload="none" src={`/api/v1/companies/${company.id}/calls/${call.id}/audio`} aria-label={`Запись ${call.filename_safe}`} />
    {call.status === 'awaiting_analysis' && <p className="helper">Аудио проверено. Можно создать вымышленный пример транскрипта и анализа.</p>}
    {call.status === 'processing' && <p className="helper">{stages[call.stage] ?? call.stage} · Попытка {call.attempt}</p>}
    {call.failure_code && <p className="form-error">{failures[call.failure_code] ?? 'Не удалось обработать запись'}{call.status === 'queued' ? ' · Повторим автоматически' : ''}</p>}
    {error && <div className="form-error" role="alert">{error}</div>}
    <div className="call-actions">{call.status === 'completed' && <button className="secondary" onClick={() => setExpanded(previous => !previous)}>{expanded ? 'Скрыть результат' : 'Открыть тестовый результат'}</button>}<button disabled={active || busy} onClick={() => void retry()}>{busy || active ? 'Обработка в очереди…' : call.status === 'completed' ? 'Повторить mock' : 'Создать тестовый результат (mock)'}</button></div>
    {expanded && (active ? <p className="helper" role="status">Готовим тестовый результат. Список обновляется автоматически.</p> : <CallResult companyId={company.id} callId={call.id} runId={call.run_id} status={call.status} onSeek={seek} />)}
  </article>;
}
