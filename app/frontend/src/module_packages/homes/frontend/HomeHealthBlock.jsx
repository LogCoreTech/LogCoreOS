import { fmtMoney } from '../../../components/finance/money'

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

// Duplicated locally rather than shared with HomeDetail.jsx's own copy —
// matches this file's own small-local-duplication convention already.
function daysUntil(dateStr) {
  if (!dateStr) return null
  return Math.ceil((new Date(dateStr) - new Date()) / (1000 * 60 * 60 * 24))
}

export default function HomeHealthBlock({ data }) {
  if (!data) return <Empty text="No data." />

  const lease = data.ownership_type === 'rent'
    ? (data.lease_end
        ? (daysUntil(data.lease_end) >= 0 ? `${daysUntil(data.lease_end)}d left on lease` : 'Lease expired')
        : 'Month-to-month')
    : (data.purchase_date ? `Owned since ${data.purchase_date}` : null)

  return (
    <div className="space-y-1 text-sm">
      <p className="font-medium">{data.home_name}</p>
      {lease && <p className="text-charcoal-500 dark:text-charcoal-400">{lease}</p>}
      <div className="flex justify-between"><span>Open tasks</span><span>{data.open_task_count}</span></div>
      <div className="flex justify-between">
        <span>Overdue</span>
        <span className={data.overdue_task_count > 0 ? 'text-red-500 font-semibold' : ''}>
          {data.overdue_task_count}
        </span>
      </div>
      <div className="flex justify-between"><span>Upcoming events</span><span>{data.upcoming_event_count}</span></div>
      <div className="flex justify-between font-semibold border-t border-charcoal-100 dark:border-charcoal-700 pt-1">
        <span>Due this month</span><span>{fmtMoney(data.amount_due_cents)}</span>
      </div>
    </div>
  )
}
