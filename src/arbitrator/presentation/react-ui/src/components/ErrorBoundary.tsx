import { Component, type ReactNode, type ErrorInfo } from "react";

interface Props {
  children: ReactNode;
  label?: string;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[ErrorBoundary:${this.props.label}]`, error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="m-4 p-4 bg-red-50 border border-red-300 rounded text-red-800 text-sm">
          <strong>Помилка сторінки {this.props.label && `(${this.props.label})`}</strong>
          <pre className="mt-2 text-xs whitespace-pre-wrap">{this.state.error.message}</pre>
          <button
            className="mt-2 px-3 py-1 bg-red-100 hover:bg-red-200 rounded text-xs"
            onClick={() => this.setState({ error: null })}
          >
            Спробувати знову
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
