import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

class RootErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error) {
    console.error('RetailOS dashboard crashed during render:', error)
  }

  render() {
    if (!this.state.error) {
      return this.props.children
    }

    return (
      <div className="min-h-screen bg-[linear-gradient(180deg,#f4efe6_0%,#efe7db_100%)] px-6 py-10 text-stone-900">
        <div className="mx-auto max-w-3xl rounded-[28px] border border-red-200 bg-white/85 p-8 shadow-[0_20px_60px_rgba(0,0,0,0.08)]">
          <div className="text-[11px] font-black uppercase tracking-[0.22em] text-red-600">Dashboard Error</div>
          <h1 className="mt-3 text-3xl font-bold tracking-tight">The frontend hit a runtime error.</h1>
          <p className="mt-3 text-sm leading-relaxed text-stone-600">
            Open the browser console for the full stack trace. The error message is shown below so the page does not fail silently.
          </p>
          <pre className="mt-6 overflow-x-auto rounded-2xl bg-stone-900 p-4 text-xs text-stone-100">
            {String(this.state.error?.stack || this.state.error?.message || this.state.error)}
          </pre>
        </div>
      </div>
    )
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>
  </React.StrictMode>
)
