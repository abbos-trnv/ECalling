import { useEffect, useState } from 'react';

type Segment = {segment_id: string; start_ms: number; end_ms: number; text: string; speaker_role: string};
type Transcript = {id: string; run_id: string; is_mock: boolean; asr_provider: string; model_id: string; diarization_available: boolean; segments: Segment[]};
type CriterionResult = {criterion_key: string; status: string; evidence_segment_ids: string[]; explanation: string};
type Analysis = {is_mock: boolean; llm_provider: string; model_id: string; score: number | null; coverage: number | null; scorecard_version: string; summary: string; topic_code: string; outcome_code: string; objections: {code: string; evidence_segment_ids: string[]}[]; criterion_results: CriterionResult[]; scorecard: {version: string; criteria: {key: string; title: string; weight: number}[]}};
type Run = {id: string; pipeline_profile: string; status: string; created_at: string};
const statuses: Record<string, string> = { pass: 'Выполнено', fail: 'Не выполнено', unknown: 'Не определено', not_applicable: 'Не применимо' };

export function timecode(ms: number) {
  return `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}`;
}

async function fetchResult<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Не удалось загрузить результат');
  }
  return response.json();
}

export function CallResult({ companyId, callId, runId, status, onSeek }: {
  companyId: string; callId: string; runId: string; status: string; onSeek: (ms: number) => void;
}) {
  const [history, setHistory] = useState<Run[]>([]);
  const [selectedRun, setSelectedRun] = useState('');
  const [result, setResult] = useState<{runId: string; transcript: Transcript; analysis: Analysis} | null>(null);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const effectiveRun = selectedRun || runId;
  const base = `/api/v1/companies/${companyId}/calls/${callId}`;
  const visible = result?.runId === effectiveRun ? result : null;

  useEffect(() => setSelectedRun(''), [runId, companyId, callId]);
  useEffect(() => {
    const controller = new AbortController();
    void fetchResult<Run[]>(`${base}/runs`, controller.signal).then(items => { if (!controller.signal.aborted) setHistory(items); }).catch(() => {});
    return () => controller.abort();
  }, [base, runId, status, reload]);

  useEffect(() => {
    const controller = new AbortController();
    setError('');
    setResult(null);
    void Promise.all([
      fetchResult<Transcript>(`${base}/transcript?run_id=${effectiveRun}`, controller.signal),
      fetchResult<Analysis>(`${base}/analysis?run_id=${effectiveRun}`, controller.signal),
    ]).then(([transcript, analysis]) => {
      if (!controller.signal.aborted) setResult({runId: effectiveRun, transcript, analysis});
    }).catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Ошибка результата'); });
    return () => controller.abort();
  }, [base, effectiveRun, status, reload]);

  function evidence(ids: string[]) {
    return ids.map(id => {
      const segment = visible?.transcript.segments.find(item => item.segment_id === id);
      return segment ? <button type="button" className="evidence-link" key={id} onClick={() => onSeek(segment.start_ms)} aria-label={`Слушать фрагмент ${timecode(segment.start_ms)}`}>{timecode(segment.start_ms)} ↗</button> : null;
    });
  }

  return <div className="call-result">
    <div className="mock-warning" role="note"><strong>Тестовый результат · MOCK</strong><p>Реплики, выводы и таймкоды вымышлены. Они не описывают содержание записи и не оценивают сотрудника. Аудио в плеере — исходное.</p></div>
    <label htmlFor={`run-${callId}`}>Версия обработки</label>
    <select id={`run-${callId}`} value={selectedRun} onChange={event => setSelectedRun(event.target.value)}><option value="">Последний запуск</option>{history.filter(run => run.id !== runId).map(run => <option key={run.id} value={run.id}>{new Date(run.created_at).toLocaleString('ru-RU')} · {run.pipeline_profile} · {run.status}</option>)}</select>
    {error ? <div className="form-error" role="alert">{error}<button className="text-button" onClick={() => setReload(previous => previous + 1)}>Повторить загрузку результата</button></div> : !visible ? <p className="empty-state">Загружаем результат…</p> : <>
      <div className="result-metrics"><div><span>Оценка</span><strong>{visible.analysis.score === null ? 'Не определена' : `${visible.analysis.score} / 100`}</strong><small>Неизвестные и неприменимые критерии не считаются провалом.</small></div><div><span>Покрытие чек-листа</span><strong>{visible.analysis.coverage === null ? '—' : `${Math.round(visible.analysis.coverage * 100)}%`}</strong><small>Доля оценённых весов среди применимых и неопределённых критериев.</small></div></div>
      <div className="result-columns"><section className="transcript-pane" aria-label="Тестовый транскрипт"><h4>Тестовый транскрипт</h4>{!visible.transcript.diarization_available && <p className="helper">Роли говорящих не установлены.</p>}<div className="segments">{visible.transcript.segments.map(segment => <div className="segment" key={segment.segment_id}><button className="timecode" onClick={() => onSeek(segment.start_ms)} aria-label={`Перейти к ${timecode(segment.start_ms)}`}>{timecode(segment.start_ms)}</button><div><small>{segment.speaker_role === 'unknown' ? 'Говорящий не определён' : segment.speaker_role}</small><p>{segment.text}</p></div></div>)}</div></section>
      <section className="analysis-pane" aria-label="Тестовый анализ"><h4>Тестовый анализ</h4><p className="analysis-summary">{visible.analysis.summary}</p><div className="analysis-tags"><span>Тема: {visible.analysis.topic_code === 'sales' ? 'Продажи' : 'Другое'}</span><span>Итог: {visible.analysis.outcome_code === 'next_step' ? 'Следующий контакт' : 'Не определён'}</span></div><h4>Возражения</h4>{visible.analysis.objections.length ? visible.analysis.objections.map((item, index) => <p key={index} className="objection">{item.code === 'price' ? 'Цена' : item.code} {evidence(item.evidence_segment_ids)}</p>) : <p className="helper">В тестовом примере не отмечены.</p>}
      <h4>Чек-лист · {visible.analysis.scorecard_version}</h4><div className="criteria">{visible.analysis.scorecard.criteria.map(criterion => {
        const item = visible.analysis.criterion_results.find(result => result.criterion_key === criterion.key);
        return item ? <article className="criterion" key={criterion.key}><div><strong>{criterion.title}</strong><span className={`criterion-status criterion-${item.status}`}>{statuses[item.status] ?? item.status}</span></div><small>Вес {criterion.weight}</small><p>{item.explanation}</p>{evidence(item.evidence_segment_ids)}</article> : null;
      })}</div></section></div>
      <p className="provider-info">ASR: {visible.transcript.asr_provider} / {visible.transcript.model_id} · LLM: {visible.analysis.llm_provider} / {visible.analysis.model_id} · Чек-лист: {visible.analysis.scorecard_version}</p>
    </>}
  </div>;
}
