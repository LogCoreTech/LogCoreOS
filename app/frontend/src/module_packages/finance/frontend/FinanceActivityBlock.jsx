import { fmtMoney } from '../../../components/finance/money'

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function FinanceActivityBlock({ data }) {
  const txs = data?.transactions || []
  if (!txs.length) return <Empty text="No transactions." />
  return (
    <div className="space-y-1.5">
      {txs.map(tx => (
        <div key={tx.id} className="flex items-center justify-between text-sm">
          <span className="truncate">{tx.payee || tx.category || '(uncategorized)'}</span>
          <span className={`shrink-0 ml-2 font-medium ${tx.amount_cents < 0 ? 'text-charcoal-600 dark:text-charcoal-300' : 'text-green-600 dark:text-green-400'}`}>
            {fmtMoney(tx.amount_cents)}
          </span>
        </div>
      ))}
    </div>
  )
}
