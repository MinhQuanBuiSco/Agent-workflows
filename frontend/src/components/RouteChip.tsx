import type { RouteName } from '../types'

const LABEL: Record<RouteName, string> = {
  green: 'Green',
  yellow: 'Yellow',
  red: 'Red',
  out_of_playbook: 'Out of playbook',
}

export function RouteChip({ route }: { route: RouteName }) {
  const tone = route === 'out_of_playbook' ? 'out_of_playbook' : route
  return <span className={`route ${tone}`}>{LABEL[route]}</span>
}
