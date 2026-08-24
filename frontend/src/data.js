export const emptyResume = {
  personal: {
    name: '',
    age: null,
    birth_date: '',
    phone: '',
    email: '',
    location: '',
    job_status: '',
    target_role: '',
    availability: '',
  },
  education: [],
  projects: [],
  internships: [],
  skills: [],
  awards: [],
  summary: '',
  self_evaluation: '',
  other: {},
  photo_base64: '',
  source_filename: '',
  warnings: [],
}

export const emptyEducation = {
  period: '',
  school: '',
  major: '',
  degree: '',
}

export const emptyExperience = {
  period: '',
  organization: '',
  role: '',
  name: '',
  technologies: '',
  background: '',
  highlights: [],
  results: [],
}

export const emptySkill = {
  category: '',
  description: '',
}

export function resumeHasContent(resume) {
  return Boolean(
    resume.personal.name
      || resume.personal.phone
      || resume.personal.email
      || resume.education.length
      || resume.projects.length
      || resume.internships.length
      || resume.skills.length
      || resume.awards.length,
  )
}

function uniqueItems(items, keyFor) {
  const seen = new Set()
  return items.filter((item) => {
    const key = keyFor(item)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export function mergeResumes(current, incoming) {
  const keepCurrent = (value, fallback) => (
    value !== '' && value !== null && value !== undefined ? value : fallback
  )
  const personal = Object.fromEntries(
    Object.keys(incoming.personal).map((key) => [
      key,
      keepCurrent(current.personal[key], incoming.personal[key]),
    ]),
  )
  return {
    ...incoming,
    personal,
    education: uniqueItems(
      [...current.education, ...incoming.education],
      (item) => `${item.period}|${item.school}|${item.major}|${item.degree}`,
    ),
    projects: uniqueItems(
      [...current.projects, ...incoming.projects],
      (item) => `${item.period}|${item.organization}|${item.name}`,
    ),
    internships: uniqueItems(
      [...current.internships, ...incoming.internships],
      (item) => `${item.period}|${item.organization}|${item.role}|${item.name}`,
    ),
    skills: uniqueItems(
      [...current.skills, ...incoming.skills],
      (item) => `${item.category}|${item.description}`,
    ),
    awards: [...new Set([...current.awards, ...incoming.awards])],
    summary: keepCurrent(current.summary, incoming.summary),
    self_evaluation: keepCurrent(current.self_evaluation, incoming.self_evaluation),
    other: { ...current.other, ...incoming.other },
    photo_base64: current.photo_base64 || incoming.photo_base64,
    source_filename: current.source_filename
      ? `${current.source_filename} + 粘贴文本`
      : incoming.source_filename,
    warnings: [...new Set([...current.warnings, ...incoming.warnings])],
  }
}
