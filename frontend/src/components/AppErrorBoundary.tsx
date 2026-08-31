import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props { children: ReactNode; }
interface State { failed: boolean; }

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };
  static getDerivedStateFromError(): State { return { failed: true }; }
  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // A private monitoring hook can be attached later. Never render exception details.
  }
  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return <main className="fatal-page" role="alert"><section className="card fatal-card">
      <p className="eyebrow">AlgoProfitX</p><h1>We couldn’t display this page.</h1>
      <p>Your session data was not shown or exposed. Reload the application to try again.</p>
      <button className="button" type="button" onClick={() => window.location.reload()}>Reload AlgoProfitX</button>
    </section></main>;
  }
}
