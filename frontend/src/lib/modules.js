// Interview format modules (labels match backend app/modules).
export const MODULE_LABELS = {
  behavioral: 'Behavioral',
  resume_deepdive: 'Résumé deep-dive',
  technical: 'Technical Q&A',
  case: 'Case',
  scenario: 'Scenario',
  portfolio: 'Portfolio walkthrough',
  roleplay: 'Role-play',
  coding: 'Coding',
  system_design: 'System design',
}

export function moduleLabel(name) {
  return MODULE_LABELS[name] ?? name
}

// The role-play scenario of a plan section, or null.
export function scenarioFor(plan, sectionName) {
  const section = plan?.sections?.find((s) => s.name === sectionName)
  return section?.module === 'roleplay' ? section.scenario ?? null : null
}

// The module of a plan section ("coding", "technical", …), or null.
export function moduleOf(plan, sectionName) {
  return plan?.sections?.find((s) => s.name === sectionName)?.module ?? null
}

// "Dana, an operations manager who…" → "Dana"
export function characterName(scenario) {
  return scenario.character.split(/[,(—-]/)[0].trim()
}
