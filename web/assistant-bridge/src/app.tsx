import {
  AuiIf,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
} from "@assistant-ui/react";
import { RefitRuntimeProvider } from "./runtime";

/**
 * Bridge test surface, NOT the final Refit UI. Reuse the provider and adapter
 * with any React layout (including the separately-built frontend).
 */
function Chat() {
  return (
    <ThreadPrimitive.Root className="thread">
      <ThreadPrimitive.Viewport className="messages">
        <AuiIf condition={(s) => s.thread.isEmpty}>
          <div className="empty">
            <h2>Test a migration</h2>
            <p>Ask Refit about a recorded evaluation. It will only report results the backend has verified.</p>
            <p className="examples">Try “show refund example”, “show deployment example”, or “examples”.</p>
          </div>
        </AuiIf>
        <ThreadPrimitive.Messages>
          {({ message }) => (
            <MessagePrimitive.Root className={message.role === "user" ? "message user" : "message assistant"}>
              <div className="message-label">{message.role === "user" ? "You" : "Refit"}</div>
              <div className="message-body"><MessagePrimitive.Parts /></div>
            </MessagePrimitive.Root>
          )}
        </ThreadPrimitive.Messages>
        <ThreadPrimitive.ViewportFooter className="composer-container">
          <ComposerPrimitive.Root className="composer">
            <ComposerPrimitive.Input placeholder="Describe a migration or request an example…" className="composer-input" />
            <AuiIf condition={(s) => !s.thread.isRunning}>
              <ComposerPrimitive.Send className="send">Send</ComposerPrimitive.Send>
            </AuiIf>
            <AuiIf condition={(s) => s.thread.isRunning}>
              <ComposerPrimitive.Cancel className="send">Cancel</ComposerPrimitive.Cancel>
            </AuiIf>
          </ComposerPrimitive.Root>
          <p className="footnote">Official assistant-ui runtime · read-only Refit API · no paid calls</p>
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
}
export function App() {
  return <RefitRuntimeProvider><main className="app">
    <header><span className="mark">r.</span><span>refit</span><a href="/" className="external">Product demo</a></header>
    <div className="intro"><span>Integration preview</span><h1>The agent and the interface, connected.</h1><p>One established chat runtime. One typed adapter. Real migration evidence—never invented model outcomes.</p></div>
    <Chat />
  </main></RefitRuntimeProvider>;
}
