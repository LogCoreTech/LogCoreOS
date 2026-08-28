import { fmtMoney } from '../../../components/finance/money'

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function FinanceBookReportBlock({ data }) {
  const r = data?.report
  if (!r) return <Empty text="No report data." />
  return (
    <div className="space-y-1 text-sm">
      <p className="font-medium">{data.book_name}</p>
      <div className="flex justify-between"><span>Income</span><span className="text-green-600 dark:text-green-400">{fmtMoney(r.income_cents)}</span></div>
      <div className="flex justify-between"><span>Expenses</span><span>{fmtMoney(r.expense_cents)}</span></div>
      <div className="flex justify-between font-semibold border-t border-charcoal-100 dark:border-charcoal-700 pt-1"><span>Net</span><span>{fmtMoney(r.net_cents)}</span></div>
    </div>
  )
}
