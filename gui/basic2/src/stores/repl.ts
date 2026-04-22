import { defineStore } from 'pinia';
import { ref } from 'vue';

export interface ReplOutput {
  stream: 'stdout' | 'stderr' | 'stdin';
  data: string;
  timestamp: number;
}

export const useReplStore = defineStore('repl', () => {
  const clientId = ref<string | null>(null);
  const sessionId = ref<string | null>(null);
  const connected = ref(false);
  const connecting = ref(false);
  const output = ref<ReplOutput[]>([]);
  const ws = ref<WebSocket | null>(null);

  // Get or create client ID (persisted in localStorage)
  function getClientId(): string {
    let id = localStorage.getItem('labhub_repl_client_id');
    if (!id) {
      id = `client_${Date.now()}_${Math.random().toString(36).substring(7)}`;
      localStorage.setItem('labhub_repl_client_id', id);
    }
    return id;
  }

  // Initialize client ID
  clientId.value = getClientId();

  // Connect to REPL session
  async function connect() {
    if (connecting.value || connected.value) {
      return;
    }

    connecting.value = true;

    try {
      // Start or reconnect to session
      const response = await fetch('/api/v2/repl/session/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: clientId.value }),
      });

      if (!response.ok) {
        throw new Error(`Failed to start session: ${response.statusText}`);
      }

      const data = await response.json();
      sessionId.value = data.session_id;

      // Connect WebSocket
      await connectWebSocket();
    } catch (err) {
      console.error('Failed to connect to REPL:', err);
      connecting.value = false;
    }
  }

  // Connect WebSocket
  async function connectWebSocket() {
    if (!sessionId.value) {
      throw new Error('No session ID');
    }

    return new Promise<void>((resolve, reject) => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/api/v2/repl/session/${sessionId.value}/ws?offset=${output.value.length}`;

      const socket = new WebSocket(wsUrl);

      socket.onopen = () => {
        console.log('REPL WebSocket connected');
        ws.value = socket;
        connected.value = true;
        connecting.value = false;
        resolve();
      };

      socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);

        if (msg.type === 'output') {
          output.value.push({
            stream: msg.stream,
            data: msg.data,
            timestamp: Date.now(),
          });
        } else if (msg.type === 'error') {
          console.error('REPL error:', msg.message);
        }
      };

      socket.onerror = (error) => {
        console.error('WebSocket error:', error);
        reject(new Error('WebSocket connection failed'));
      };

      socket.onclose = () => {
        console.log('REPL WebSocket closed');
        connected.value = false;
        ws.value = null;

        // Auto-reconnect after 2 seconds
        setTimeout(() => {
          if (sessionId.value) {
            connectWebSocket().catch(console.error);
          }
        }, 2000);
      };
    });
  }

  // Disconnect from REPL
  async function disconnect() {
    if (ws.value) {
      ws.value.close();
      ws.value = null;
    }

    if (sessionId.value) {
      try {
        await fetch(`/api/v2/repl/session/${sessionId.value}`, {
          method: 'DELETE',
        });
      } catch (err) {
        console.error('Failed to close session:', err);
      }
    }

    sessionId.value = null;
    connected.value = false;
  }

  // Execute code
  function executeCode(code: string) {
    if (!ws.value || !connected.value) {
      throw new Error('Not connected to REPL');
    }

    ws.value.send(
      JSON.stringify({
        type: 'execute',
        code,
      })
    );
  }

  // Send interrupt signal (Ctrl+C)
  function sendInterrupt() {
    if (!ws.value || !connected.value) {
      throw new Error('Not connected to REPL');
    }

    ws.value.send(
      JSON.stringify({
        type: 'interrupt',
      })
    );
  }

  // Ensure REPL is connected (connect if not already)
  async function ensureConnected() {
    if (connected.value) return;
    if (connecting.value) {
      // Wait for ongoing connection
      return new Promise<void>((resolve) => {
        const check = setInterval(() => {
          if (connected.value || !connecting.value) {
            clearInterval(check);
            resolve();
          }
        }, 100);
      });
    }
    await connect();
  }

  // Echo an input line to the output (so the user sees what they typed)
  function addEchoLine(code: string) {
    output.value.push({
      stream: 'stdin',
      data: `>>> ${code}\n`,
      timestamp: Date.now(),
    });
  }

  // Clear output
  function clearOutput() {
    output.value = [];
  }

  return {
    clientId,
    sessionId,
    connected,
    connecting,
    output,
    connect,
    disconnect,
    ensureConnected,
    executeCode,
    sendInterrupt,
    addEchoLine,
    clearOutput,
  };
});
