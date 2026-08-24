import { useEffect, useRef, useState, useTransition } from 'react'
import { Download, FileJson, FileOutput, HelpCircle, Settings2 } from 'lucide-react'
import EducationEditor from './components/EducationEditor.jsx'
import ExperienceEditor from './components/ExperienceEditor.jsx'
import Inspector from './components/Inspector.jsx'
import PersonalEditor from './components/PersonalEditor.jsx'
import ParseResultNotice from './components/ParseResultNotice.jsx'
import SkillsEditor from './components/SkillsEditor.jsx'
import SummaryEditor from './components/SummaryEditor.jsx'
import UploadRail from './components/UploadRail.jsx'
import { emptyResume, mergeResumes, resumeHasContent } from './data.js'

async function apiError(response) {
  try {
    const payload = await response.json()
    return payload.detail || '请求失败'
  } catch {
    return `请求失败（${response.status}）`
  }
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export default function App() {
  const [resume, setResume] = useState(() => structuredClone(emptyResume))
  const [profile, setProfile] = useState(null)
  const [aiStatus, setAiStatus] = useState(null)
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState('')
  const parseController = useRef(null)
  const [isPending, startTransition] = useTransition()

  useEffect(() => {
    let active = true
    Promise.all([
      fetch('/api/template-profile').then((response) => response.ok ? response.json() : null),
      fetch('/api/ai-status').then((response) => response.ok ? response.json() : null),
    ])
      .then(([nextProfile, nextAiStatus]) => {
        if (!active) return
        setProfile(nextProfile)
        setAiStatus(nextAiStatus)
      })
      .catch(() => {
        if (!active) return
        setProfile(null)
        setAiStatus(null)
      })
    return () => { active = false }
  }, [])

  const valid = Boolean(
    resume.personal.name
      && (resume.personal.phone || resume.personal.email)
      && resume.education.length,
  )
  const hasContent = resumeHasContent(resume)

  const parseFile = async (file) => {
    setStatus('loading')
    setError('')
    const body = new FormData()
    body.append('file', file)
    try {
      const response = await fetch('/api/parse', { method: 'POST', body })
      if (!response.ok) throw new Error(await apiError(response))
      const parsed = await response.json()
      startTransition(() => {
        setResume(parsed)
        setStatus('ready')
      })
    } catch (requestError) {
      setError(requestError.message)
      setStatus('error')
    }
  }

  const parseText = async (text, importMode, engine) => {
    setStatus('loading')
    setError('')
    const controller = new AbortController()
    parseController.current = controller
    try {
      const response = await fetch('/api/parse-text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, engine }),
        signal: controller.signal,
      })
      if (!response.ok) throw new Error(await apiError(response))
      const parsed = await response.json()
      startTransition(() => {
        setResume((current) => importMode === 'merge' ? mergeResumes(current, parsed) : parsed)
        setStatus('ready')
      })
      return true
    } catch (requestError) {
      if (requestError.name === 'AbortError') {
        setError('已取消本次文本解析。')
        setStatus('idle')
      } else {
        setError(requestError.message)
        setStatus('error')
      }
      return false
    } finally {
      parseController.current = null
    }
  }

  const cancelTextParse = () => parseController.current?.abort()

  const generate = async () => {
    if (!valid) return
    setStatus('generating')
    setError('')
    try {
      const response = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume, output_format: 'docx' }),
      })
      if (!response.ok) throw new Error(await apiError(response))
      const blob = await response.blob()
      downloadBlob(blob, `${resume.personal.name}-格式化简历.docx`)
      setStatus('ready')
    } catch (requestError) {
      setError(requestError.message)
      setStatus('error')
    }
  }

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(resume, null, 2)], { type: 'application/json;charset=utf-8' })
    downloadBlob(blob, `${resume.personal.name || 'resume'}-parsed.json`)
  }

  const updateResume = (key, value) => setResume((current) => ({ ...current, [key]: value }))

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <strong>简历工坊</strong>
          <span className="template-status">当前模板：v7.3-27届表格版 · 已解析</span>
        </div>
        <nav aria-label="工具导航">
          <button type="button"><HelpCircle size={17} />使用说明</button>
          <button type="button"><Settings2 size={17} />设置</button>
        </nav>
      </header>

      <div className="workspace">
        <UploadRail
          fileName={resume.source_filename}
          status={isPending ? 'loading' : status}
          error={error}
          onFile={parseFile}
          onText={parseText}
          onCancelText={cancelTextParse}
          hasContent={hasContent}
          aiStatus={aiStatus}
          parseMetadata={resume.other?.文本解析}
        />
        <main className="editor" aria-busy={status === 'loading'}>
          <h1 className="sr-only">简历信息校对</h1>
          <ParseResultNotice metadata={resume.other?.文本解析} />
          <PersonalEditor value={resume.personal} onChange={(value) => updateResume('personal', value)} />
          <SummaryEditor
            summary={resume.summary}
            selfEvaluation={resume.self_evaluation}
            onSummaryChange={(value) => updateResume('summary', value)}
            onSelfEvaluationChange={(value) => updateResume('self_evaluation', value)}
          />
          <EducationEditor items={resume.education} onChange={(value) => updateResume('education', value)} />
          <ExperienceEditor title="项目经历" kind="project" items={resume.projects} onChange={(value) => updateResume('projects', value)} />
          <ExperienceEditor title="实习经历" kind="internship" items={resume.internships} onChange={(value) => updateResume('internships', value)} />
          <SkillsEditor
            items={resume.skills}
            awards={resume.awards}
            onItemsChange={(value) => updateResume('skills', value)}
            onAwardsChange={(value) => updateResume('awards', value)}
          />
          <footer className="action-bar">
            <button className="secondary-button" type="button" onClick={downloadJson}>
              <FileJson size={18} />下载解析结果 JSON
            </button>
            <button className="primary-button" type="button" disabled={!valid || status === 'generating'} onClick={generate}>
              {status === 'generating' ? <Download className="spin" size={18} /> : <FileOutput size={18} />}
              {status === 'generating' ? '正在生成…' : '生成新简历'}
            </button>
          </footer>
        </main>
        <Inspector resume={resume} profile={profile} />
      </div>
    </div>
  )
}
