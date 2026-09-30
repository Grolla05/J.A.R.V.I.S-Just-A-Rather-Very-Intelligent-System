import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act, screen, cleanup } from "@testing-library/react";
import ChatPanel from "../ChatPanel";
import MessageList from "../CHAT/MessageList";

vi.mock("../../hooks/BridgeAPI", () => ({
  default: () => ({ isReady: false, callApi: vi.fn().mockResolvedValue([]) }),
}));

// Sidebar/Input não são o alvo: stub para isolar o fluxo de stream
vi.mock("../CHAT/ChatSidebar", () => ({ default: () => null }));
vi.mock("../CHAT/ChatInput", () => ({ default: () => null }));

const flushFrames = () =>
  act(async () => {
    await new Promise((r) => requestAnimationFrame(() => r()));
  });

describe("streaming do chat", () => {
  beforeEach(() => {
    window.matchMedia = window.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {} }));
    Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(cleanup);

  it("agrupa rajada de chunks em poucos setMessages", async () => {
    const setMessages = vi.fn();
    render(
      <ChatPanel
        messages={[]}
        setMessages={setMessages}
        currentSessionId="s1"
        setCurrentSessionId={vi.fn()}
      />,
    );

    act(() => window.receiveChatStream("a ", true, false));
    const afterFirst = setMessages.mock.calls.length;

    act(() => {
      for (let i = 0; i < 50; i++) window.receiveChatStream("x ", false, false);
    });
    // Nada aplicado antes do frame
    expect(setMessages.mock.calls.length).toBe(afterFirst);

    await flushFrames();
    // 50 chunks -> 1 update
    expect(setMessages.mock.calls.length - afterFirst).toBe(1);

    // O updater concatena todos os chunks acumulados
    const updater = setMessages.mock.calls.at(-1)[0];
    const next = updater([{ id: "streaming-msg", sender: "jarvis", text: "a " }]);
    expect(next[0].text).toBe("a " + "x ".repeat(50));
  });

  it("isDone aplica chunks pendentes sem esperar o frame", () => {
    const setMessages = vi.fn();
    render(
      <ChatPanel
        messages={[]}
        setMessages={setMessages}
        currentSessionId="s1"
        setCurrentSessionId={vi.fn()}
      />,
    );
    act(() => {
      window.receiveChatStream("a ", true, false);
      window.receiveChatStream("b", false, false);
      window.receiveChatStream("", false, true);
    });
    const updaters = setMessages.mock.calls.map((c) => c[0]).filter((u) => typeof u === "function");
    let state = [];
    for (const u of updaters) state = u(state);
    expect(state[0].text).toBe("a b");
    expect(state[0].id).not.toBe("streaming-msg");
  });
});

describe("MessageList", () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(cleanup);

  const base = { isThinking: false, onEditMessage: vi.fn() };

  it("renderiza markdown de mensagem do Jarvis e texto do usuário", () => {
    render(
      <MessageList
        {...base}
        messages={[
          { id: 1, sender: "user", text: "oi", time: "10:00" },
          { id: 2, sender: "jarvis", text: "**negrito**", time: "10:00" },
        ]}
      />,
    );
    expect(screen.getByText("oi")).toBeTruthy();
    expect(screen.getByText("negrito").tagName).toBe("STRONG");
  });

  it("usa scroll auto durante streaming e smooth fora dele", () => {
    const spy = vi.fn();
    Element.prototype.scrollIntoView = spy;
    const { rerender } = render(
      <MessageList {...base} messages={[{ id: "streaming-msg", sender: "jarvis", text: "a", time: "1" }]} />,
    );
    expect(spy).toHaveBeenLastCalledWith({ behavior: "auto" });
    rerender(<MessageList {...base} messages={[{ id: 5, sender: "jarvis", text: "a", time: "1" }]} />);
    expect(spy).toHaveBeenLastCalledWith({ behavior: "smooth" });
  });
});
