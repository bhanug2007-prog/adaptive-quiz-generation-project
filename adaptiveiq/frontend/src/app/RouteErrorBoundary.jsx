import { Component } from 'react'
import { ErrorState } from '../components/ui'

/** Keeps one broken page from blanking the whole app. A failed lazy chunk (after a redeploy) offers a reload. */
export default class RouteErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Page error', error, info)
  }

  render() {
    if (!this.state.error) return this.props.children
    const chunk = /dynamically imported module|Loading chunk/i.test(this.state.error.message || '')
    return (
      <div style={{ padding: 'var(--space-7) 0' }}>
        <ErrorState title={chunk ? 'A new version is available' : 'This page could not be shown'}
          error={chunk ? { message: 'Reload to get the latest version of AdaptiveIQ.' } : this.state.error}
          onRetry={() => (chunk ? window.location.reload() : this.setState({ error: null }))} />
      </div>
    )
  }
}
