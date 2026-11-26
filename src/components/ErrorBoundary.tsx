import { Component, type ErrorInfo, type ReactNode } from 'react';
import { CircleAlert, RefreshCw } from 'lucide-react';

type State = { error: Error | null };

export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('AI Clipper Pro UI error:', error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="crash-card">
        <CircleAlert size={28} />
        <h2>This view hit a snag</h2>
        <p>{this.state.error.message || 'An unexpected error occurred.'}</p>
        <button className="primary" onClick={() => this.setState({ error: null })}>
          <RefreshCw size={15} /> Try again
        </button>
        <button className="ghost-btn" onClick={() => window.location.reload()}>Reload app</button>
      </div>
    );
  }
}
