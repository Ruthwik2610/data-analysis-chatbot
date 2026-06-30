import { api, GENERIC_API_ERROR_MESSAGE, streamQuery } from "../api";

describe("api.listChats", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("requests project scoped recents", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [],
    } as Response);

    await api.listChats("proj_1");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/chats?project_id=proj_1",
      expect.any(Object),
    );
  });

  it("requests unscoped recents when no project is active", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [],
    } as Response);

    await api.listChats(null);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/chats?project_id=none",
      expect.any(Object),
    );
  });
});

describe("streamQuery", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("serializes auto model mode in the query request", async () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("event: done\ndata: {\"chat_id\":\"chat_1\"}\n\n"));
        controller.close();
      },
    });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      body: stream,
    } as Response);

    const events = [];
    for await (const event of streamQuery({ chat_id: null, question: "total sales", model_mode: "auto" })) {
      events.push(event);
    }

    const requestInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(requestInit.body)).model_mode).toBe("auto");
    expect(events).toEqual([{ event: "done", data: { chat_id: "chat_1" } }]);
  });

  it("serializes the business logic toggle in the query request", async () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("event: done\ndata: {\"chat_id\":\"chat_1\"}\n\n"));
        controller.close();
      },
    });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      body: stream,
    } as Response);

    const events = [];
    for await (const event of streamQuery({ chat_id: null, question: "total sales", business_logic_enabled: true })) {
      events.push(event);
    }

    const requestInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(requestInit.body)).business_logic_enabled).toBe(true);
    expect(events).toEqual([{ event: "done", data: { chat_id: "chat_1" } }]);
  });

  it("sanitizes internal thinking steps before exposing stream events", async () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("event: thinking\ndata: {\"step\":\"Querying workspace: SELECT * FROM orders WHERE api_key = 'secret'\"}\n\n"));
        controller.close();
      },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      body: stream,
    } as Response);

    const events = [];
    for await (const event of streamQuery({ chat_id: null, question: "total sales" })) {
      events.push(event);
    }

    expect(events).toEqual([{ event: "thinking", data: { step: "Working on your answer" } }]);
  });

  it("hides raw backend text when the query request fails before streaming", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      body: null,
      status: 500,
      text: async () => "Traceback: database password leaked",
    } as Response);

    let error: Error | undefined;
    try {
      await streamQuery({ chat_id: null, question: "total sales" }).next();
    } catch (err) {
      error = err as Error;
    }

    expect(error?.message).toBe(GENERIC_API_ERROR_MESSAGE);
    expect(error?.message).not.toContain("database password");
  });
});

describe("api error handling", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("hides raw response bodies from user-facing API errors", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 500,
      text: async () => "{\"detail\":\"Traceback: token abc123\"}",
    } as Response);

    let error: Error | undefined;
    try {
      await api.clearCache();
    } catch (err) {
      error = err as Error;
    }

    expect(error?.message).toBe(GENERIC_API_ERROR_MESSAGE);
    expect(error?.message).not.toContain("Traceback");
  });
});
