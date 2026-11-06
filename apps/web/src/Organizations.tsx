import { useEffect, useRef, useState } from 'react';

type Company = { id: string; name: string; created_at: string };
type Employee = { id: string; company_id: string; display_name: string; created_at: string };
const PAGE_SIZE = 10;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, init);
  if (!response.ok) {
    let message = 'Не удалось выполнить запрос. Попробуйте ещё раз.';
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') message = body.detail;
      else if (response.status === 422) message = 'Введите имя длиной от 1 до 200 символов.';
    } catch { /* HTTP error without JSON. */ }
    throw new Error(message);
  }
  return response.status === 204 ? undefined as T : response.json();
}

function json(method: string, body?: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined };
}

export function Organizations({ onCompanyChange, onDataChange }: { onCompanyChange: (company: Company | null) => void; onDataChange: () => void }) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [companyLoading, setCompanyLoading] = useState(true);
  const [companyError, setCompanyError] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [newCompany, setNewCompany] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [employeeName, setEmployeeName] = useState('');
  const [editingId, setEditingId] = useState('');
  const [editingName, setEditingName] = useState('');
  const [confirmDelete, setConfirmDelete] = useState('');
  const [page, setPage] = useState(0);
  const [revision, setRevision] = useState(0);
  const [employeeError, setEmployeeError] = useState('');
  const [employeeData, setEmployeeData] = useState<{ companyId: string; page: number; revision: number; items: Employee[]; hasNext: boolean } | null>(null);
  const companyRequest = useRef<AbortController | null>(null);
  const selected = companies.find(company => company.id === selectedId);
  useEffect(() => onCompanyChange(selected ?? null), [selected, onCompanyChange]);
  const currentData = employeeData?.companyId === selectedId && employeeData.page === page && employeeData.revision === revision ? employeeData : null;

  async function loadCompanies(preferredId?: string) {
    companyRequest.current?.abort();
    const controller = new AbortController();
    companyRequest.current = controller;
    setCompanyLoading(true);
    setCompanyError('');
    try {
      const result: Company[] = [];
      for (let offset = 0; ; offset += 100) {
        const batch = await request<Company[]>(`/companies?limit=100&offset=${offset}`, { signal: controller.signal });
        result.push(...batch);
        if (batch.length < 100) break;
      }
      if (controller.signal.aborted) return;
      setCompanies(result);
      setSelectedId(previous => {
        const candidate = preferredId ?? previous;
        return result.some(item => item.id === candidate) ? candidate : result[0]?.id ?? '';
      });
    } catch (cause) {
      if (!controller.signal.aborted) setCompanyError(cause instanceof Error ? cause.message : 'Ошибка загрузки компаний');
    } finally {
      if (!controller.signal.aborted) setCompanyLoading(false);
    }
  }

  useEffect(() => {
    void loadCompanies();
    return () => companyRequest.current?.abort();
  }, []);

  useEffect(() => {
    setPage(0);
    setEmployeeName('');
    setEditingId('');
    setError('');
    setConfirmDelete('');
  }, [selectedId]);

  useEffect(() => setCompanyName(selected?.name ?? ''), [selected?.id, selected?.name]);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    setEmployeeError('');
    request<Employee[]>(`/companies/${selectedId}/employees?limit=${PAGE_SIZE + 1}&offset=${page * PAGE_SIZE}`, { signal: controller.signal })
      .then(items => {
        if (controller.signal.aborted) return;
        if (!items.length && page > 0) { setPage(previous => previous - 1); return; }
        setEmployeeData({ companyId: selectedId, page, revision, items: items.slice(0, PAGE_SIZE), hasNext: items.length > PAGE_SIZE });
      })
      .catch(cause => { if (!controller.signal.aborted) setEmployeeError(cause instanceof Error ? cause.message : 'Ошибка загрузки сотрудников'); });
    return () => controller.abort();
  }, [selectedId, page, revision]);

  async function mutate(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError('');
    try { await action(); onDataChange(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось сохранить изменения'); }
    finally { setBusy(false); }
  }

  function switchCompany(id: string) {
    setPage(0);
    setEmployeeData(null);
    setSelectedId(id);
  }

  return <section className="organizations" id="organizations" aria-label="Компании и сотрудники">
    <div className="section-heading"><div><p className="eyebrow">РАБОЧЕЕ ПРОСТРАНСТВО</p><h2>Компании и сотрудники</h2></div><span className="badge">ДЕМО</span></div>
    {error && <div className="form-error" role="alert">{error}</div>}
    <div className="org-grid">
      <div className="org-panel">
        <h3>Компания</h3>
        {companyError ? <div role="alert" className="form-error">{companyError}<button className="text-button" onClick={() => void loadCompanies()}>Повторить</button></div> : null}
        <label htmlFor="company-select">Выбранная компания</label>
        <select id="company-select" value={selectedId} disabled={busy || companyLoading || !companies.length} onChange={event => switchCompany(event.target.value)}>
          {!companies.length && <option value="">{companyLoading ? 'Загружаем…' : 'Создайте первую компанию'}</option>}
          {companies.map(company => <option key={company.id} value={company.id}>{company.name}</option>)}
        </select>
        <form onSubmit={event => { event.preventDefault(); void mutate(async () => {
          const company = await request<Company>('/companies', json('POST', { name: newCompany.trim() }));
          setNewCompany(''); setPage(0); await loadCompanies(company.id);
        }); }}>
          <label htmlFor="new-company">Новая компания</label>
          <div className="input-row"><input id="new-company" value={newCompany} onChange={event => setNewCompany(event.target.value)} required maxLength={200} placeholder="Например, ООО Альфа" disabled={busy} /><button disabled={busy || companyLoading || !newCompany.trim()}>Создать</button></div>
        </form>
        {selected && <details className="company-settings" key={selected.id}>
          <summary>Настройки компании</summary>
          <form onSubmit={event => { event.preventDefault(); void mutate(async () => {
            await request(`/companies/${selectedId}`, json('PUT', { name: companyName.trim() }));
            await loadCompanies(selectedId);
          }); }}>
            <label htmlFor="company-name">Название компании</label>
            <div className="input-row"><input id="company-name" value={companyName} onChange={event => setCompanyName(event.target.value)} required maxLength={200} disabled={busy} /><button disabled={busy || !companyName.trim()}>Сохранить</button></div>
          </form>
          {confirmDelete === 'company' ? <div className="delete-confirm"><p>Удалить «{selected.name}»? Компания с сотрудниками не будет удалена.</p><button className="danger" disabled={busy} onClick={() => void mutate(async () => { await request(`/companies/${selectedId}`, json('DELETE')); setConfirmDelete(''); await loadCompanies(); })}>Да, удалить компанию</button><button className="text-button" disabled={busy} onClick={() => setConfirmDelete('')}>Отмена</button></div> : <button className="text-button danger" disabled={busy} onClick={() => setConfirmDelete('company')}>Удалить компанию</button>}
        </details>}
        <p className="helper">Используйте вымышленные компании и имена для локального демо.</p>
      </div>
      <div className="org-panel employee-panel" aria-busy={Boolean(selectedId && !currentData && !employeeError)}>
        <h3>Сотрудники {selected ? <span>· {selected.name}</span> : ''}</h3>
        {!selectedId ? <p className="empty-state">Выберите или создайте компанию.</p> : <>
          <form onSubmit={event => { event.preventDefault(); void mutate(async () => {
            await request(`/companies/${selectedId}/employees`, json('POST', { display_name: employeeName.trim() }));
            setEmployeeName(''); setRevision(previous => previous + 1);
          }); }}>
            <label htmlFor="employee-name">Новый сотрудник</label>
            <div className="input-row"><input id="employee-name" value={employeeName} onChange={event => setEmployeeName(event.target.value)} required maxLength={200} placeholder="Имя или псевдоним" disabled={busy || companyLoading} /><button disabled={busy || companyLoading || !employeeName.trim()}>Добавить</button></div>
          </form>
          {employeeError ? <div className="form-error" role="alert">{employeeError}<button className="text-button" onClick={() => setRevision(previous => previous + 1)}>Повторить</button></div> : !currentData ? <p className="empty-state" role="status">Загружаем сотрудников…</p> : currentData.items.length === 0 ? <p className="empty-state">Пока нет сотрудников. Добавьте первого.</p> : <ul className="employee-list">
            {currentData.items.map(employee => <li key={employee.id}>
              {editingId === employee.id ? <form className="edit-row" onSubmit={event => { event.preventDefault(); void mutate(async () => {
                await request(`/companies/${selectedId}/employees/${employee.id}`, json('PUT', { display_name: editingName.trim() }));
                setEditingId(''); setRevision(previous => previous + 1);
              }); }}><input aria-label="Новое имя сотрудника" value={editingName} onChange={event => setEditingName(event.target.value)} required maxLength={200} disabled={busy} autoFocus /><button disabled={busy || !editingName.trim()}>Сохранить</button><button type="button" className="text-button" disabled={busy} onClick={() => setEditingId('')}>Отмена</button></form> : <><div className="employee-person"><span className="avatar">{employee.display_name.slice(0, 1).toUpperCase()}</span><span>{employee.display_name}</span></div><div className="employee-actions"><button className="text-button" aria-label={`Изменить ${employee.display_name}`} disabled={busy} onClick={() => { setEditingId(employee.id); setEditingName(employee.display_name); setConfirmDelete(''); }}>Изменить</button><button className="text-button danger" aria-label={`Удалить ${employee.display_name}`} disabled={busy} onClick={() => setConfirmDelete(employee.id)}>Удалить</button></div></>}
              {confirmDelete === employee.id && <div className="delete-confirm"><p>Удалить сотрудника «{employee.display_name}»?</p><button className="danger" disabled={busy} onClick={() => void mutate(async () => { await request(`/companies/${selectedId}/employees/${employee.id}`, json('DELETE')); setConfirmDelete(''); setRevision(previous => previous + 1); })}>Да, удалить сотрудника</button><button className="text-button" disabled={busy} onClick={() => setConfirmDelete('')}>Отмена</button></div>}
            </li>)}
          </ul>}
          {(page > 0 || currentData?.hasNext) && <div className="pagination"><button className="secondary" disabled={busy || page === 0 || !currentData} onClick={() => { setEditingId(''); setConfirmDelete(''); setPage(previous => previous - 1); }}>Назад</button><span>Страница {page + 1}</span><button className="secondary" disabled={busy || !currentData?.hasNext} onClick={() => { setEditingId(''); setConfirmDelete(''); setPage(previous => previous + 1); }}>Далее</button></div>}
        </>}
      </div>
    </div>
  </section>;
}
