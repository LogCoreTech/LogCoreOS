import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    console.error('Unhandled render error:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-charcoal-50 dark:bg-charcoal-900 p-4">
          <div className="card p-6 max-w-sm w-full text-center">
            <p className="text-4xl mb-3">⚠</p>
            <h2 className="font-semibold text-lg mb-2">Something went wrong</h2>
            <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mb-4">
              {this.state.error?.message || 'An unexpected error occurred.'}
            </p>
            <button
              onClick={() => { this.setState({ hasError: false, error: null }); window.location.href = '/' }}
              className="btn-primary"
            >
              Go Home
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
