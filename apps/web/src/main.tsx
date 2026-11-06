import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import { Organizations } from './Organizations';
import { Calls } from './Calls';

type Health = 'checking' | 'ready' | 'offline';

function App() {
  const [company, setCompany] = useState<{ id: string; name: string } | null>(null);
  const [workspaceRevision, setWorkspaceRevision] = useState(0);
  const [health, setHealth] = useState<Health>('checking');
  useEffect(() => {
    const controller = new AbortController();
    async function check() {
      try {
        const response = await fetch('/health/ready', {
          signal: controller.signal,
        });
        const result = await response.json();
        if (!controller.signal.aborted) {
          setHealth(response.ok && result.db === 'ok' ? 'ready' : 'offline');
        }
      } catch {
        if (!controller.signal.aborted) setHealth('offline');
      }
    }
    void check();
    const timer = setInterval(() => void check(), 10000);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);

  return (
    <div className="layout">
      <aside>
        <a className="brand" href="/">◉ <span>Voice Analytics</span></a>
        <div className="workspace">ЛОКАЛЬНОЕ ДЕМО</div>
        <div className="nav active">Обзор проекта</div>
        <a className="nav nav-link" href="#calls">Записи звонков</a>
        <a className="nav nav-link" href="#organizations">Компании и сотрудники</a>
        <div className="aside-bottom">Прототип V0 · Только тестовые данные</div>
      </aside>
      <main>
        <header><span>Рабочее пространство</span><span className="badge">LOCAL</span></header>
        <section className="intro">
          <p className="eyebrow">ОТ РАЗГОВОРА К ВЫВОДАМ</p>
          <h1>Каждый звонок.<br /><span>Понятный результат.</span></h1>
          <p className="description">Расшифровка, анализ и оценка разговоров с подтверждением в записи.</p>
        </section>
        <section className="status-card">
          <div><p className="eyebrow">СОСТОЯНИЕ СИСТЕМЫ</p><h2>Основа проекта</h2></div>
          <div className={`connection ${health}`} role="status">
            <i />{health === 'ready' ? 'API и база доступны' : health === 'checking' ? 'Проверяем соединение…' : 'Нет соединения с API или базой'}
          </div>
        </section>
        <Organizations onCompanyChange={setCompany} onDataChange={() => setWorkspaceRevision(previous => previous + 1)} />
        <Calls company={company} workspaceRevision={workspaceRevision} />
        <section className="steps" aria-label="Этапы обработки">
          {[
            ['01', 'Загрузить запись', 'Аудиофайл и сотрудник'],
            ['02', 'Получить транскрипт', 'Реплики с таймкодами'],
            ['03', 'Проверить анализ', 'Итоги и критерии оценки'],
          ].map(([number, title, text]) => <article key={number}><span className="number">{number}</span><h3>{title}</h3><p>{text}</p><span className="planned">{number === '01' ? 'Доступно' : 'Тестовый mock-режим'}</span></article>)}
        </section>
        <div className="notice"><strong>Сейчас: сквозной mock-прототип</strong><p>Доступны вымышленные транскрипт и анализ с пометкой MOCK. Настоящее распознавание речи и AI-анализ ещё не подключены. При неизвестных ролях оценка сотрудника не определяется.</p></div>
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
