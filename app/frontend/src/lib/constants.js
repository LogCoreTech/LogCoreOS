export const CATEGORY_COLORS = {
  God:              'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
  Family:           'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  Job:              'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
  LogCore:          'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
  'Personal Growth':'bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300',
  Hobbies:          'bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300',
}

export const DEFAULT_CAT_COLOR =
  'bg-charcoal-100 text-charcoal-700 dark:bg-charcoal-700 dark:text-charcoal-300'

export function catColor(cat) {
  return CATEGORY_COLORS[cat] || DEFAULT_CAT_COLOR
}
